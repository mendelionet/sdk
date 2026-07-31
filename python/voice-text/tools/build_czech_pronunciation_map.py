#!/usr/bin/env python3
"""Build the runtime Czech respelling corpus from Wiktionary IPA.

The source is the Czech Wiktionary Wiktextract export served by Kaikki. Source
JSONL is downloaded only while building and is never shipped with a runtime.
The generated data is an adaptation licensed under CC BY-SA 4.0; see the
adjacent data notice in ``mendelio_voice_text/data``.

ONE map ships: ``czech_ipa_transliteration_map.json``. It is built in two steps
over the same dump:

1. ``extract_candidates`` resolves each documented di/ti/ni site (kupodivu ->
   "kupoďivu"). It works per FORM, so it reaches stem-changing forms whose lemma
   carries no IPA — which suffix grafting (plan 4e) cannot.
2. ``extract_ipa_candidates`` transliterates each word from its own IPA and
   OVERRIDES step 1 wherever it has better evidence, adding the foreign spelling
   a di/ti/ni-only corpus never could (notebook -> "noutbuk").

Step 1 used to ship as a second map behind an env switch. The switch is gone
(2026-07-17): only IPA respellings are used, so step 1 is now purely internal
and its output lands in build-reports/ as an intermediate, not in package data.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ipa_transliteration import (  # noqa: E402
    Verdict,
    _spurious_softening,
    decide_respelling,
    is_unambiguous,
    reads_as,
    similarity,
)

SOURCE_URL = "https://kaikki.org/cswiktionary/raw-wiktextract-data.jsonl.gz"
SOURCE_PAGE = "https://kaikki.org/cswiktionary/rawdata.html"
LICENSE = "CC-BY-SA-4.0"
FORMAT_VERSION = 1
SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IPA_OUTPUT = SERVICE_ROOT / "mendelio_voice_text/data/czech_ipa_transliteration_map.json"
# Everything below is a build report for human eyes, not runtime data: it must
# stay out of package data, which ships with the wheel. The di/ti/ni map
# is kept as an intermediate so a build can be diffed against what it started
# from, but nothing reads it at runtime.
DEFAULT_OUTPUT = SERVICE_ROOT / "build-reports/czech_di_ti_ni_intermediate.json"
DEFAULT_REVIEW_OUTPUT = SERVICE_ROOT / "build-reports/czech_ipa_transliteration_review.json"
DEFAULT_DIFF_OUTPUT = SERVICE_ROOT / "build-reports/czech_ipa_transliteration_diff.json"

ORTH_TARGET = re.compile(r"([dtn])(i|í)", re.IGNORECASE)
IPA_TARGET = re.compile(r"(d|ɟ|t|c|n|ɲ)(?:ɪ|iː)")
IPA_BASE = {"d": "d", "ɟ": "d", "t": "t", "c": "t", "n": "n", "ɲ": "n"}
IPA_SOFT = {"ɟ", "c", "ɲ"}
SOFT_SPELLING = {"d": "ď", "t": "ť", "n": "ň"}
RUNTIME_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
PRODUCTIVE_PREFIXES = {
    "do", "na", "nad", "od", "po", "pod", "pro", "pře", "před", "při",
    "roz", "s", "se", "u", "v", "ve", "vy", "vz", "z", "za",
}


def decisions_from_ipa(word: str, ipa: str) -> tuple[tuple[str, bool], ...] | None:
    """Align orthographic di/ti/ni sites with their IPA hard/soft consonants."""
    written = [match.group(1).lower() for match in ORTH_TARGET.finditer(word)]
    if not written:
        return None
    spoken_tokens = [match.group(1) for match in IPA_TARGET.finditer(ipa)]
    spoken = [IPA_BASE[token] for token in spoken_tokens]
    if written != spoken:
        return None
    return tuple((base, token in IPA_SOFT) for base, token in zip(spoken, spoken_tokens))


def respell(word: str, decisions: tuple[tuple[str, bool], ...]) -> str | None:
    matches = list(ORTH_TARGET.finditer(word))
    if [match.group(1).lower() for match in matches] != [base for base, _ in decisions]:
        return None
    parts: list[str] = []
    cursor = 0
    for match, (base, is_soft) in zip(matches, decisions):
        parts.append(word[cursor : match.start()])
        vowel = match.group(2).lower()
        if is_soft:
            consonant = SOFT_SPELLING[base]
            replacement = consonant + vowel
        else:
            replacement = base + ("ý" if vowel == "í" else "y")
        if match.group(1).isupper():
            replacement = replacement[0].upper() + replacement[1:]
        parts.append(replacement)
        cursor = match.end()
    parts.append(word[cursor:])
    result = "".join(parts)
    return result if result != word else None


def iter_jsonl(path: Path) -> Iterator[dict]:
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def extract_candidates(path: Path) -> tuple[dict[str, str], dict[str, int]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    stats = defaultdict(int)
    for entry in iter_jsonl(path):
        if entry.get("lang_code") != "cs":
            continue
        stats["czech_entries"] += 1
        word = entry.get("word")
        if not isinstance(word, str):
            continue
        if not RUNTIME_WORD.fullmatch(word) or not ORTH_TARGET.search(word):
            continue
        ipas = {
            sound.get("ipa")
            for sound in entry.get("sounds", [])
            if isinstance(sound, dict) and isinstance(sound.get("ipa"), str)
        }
        for ipa in ipas:
            decisions = decisions_from_ipa(word, ipa)
            if not decisions:
                continue
            hint = respell(word, decisions)
            if hint:
                candidates[word.casefold()].add(hint.casefold())
                stats["entries_with_aligned_ipa"] += 1
            for form in entry.get("forms", []):
                form_word = form.get("form") if isinstance(form, dict) else None
                if not isinstance(form_word, str) or not RUNTIME_WORD.fullmatch(form_word):
                    continue
                form_hint = respell(form_word, decisions)
                if form_hint:
                    candidates[form_word.casefold()].add(form_hint.casefold())
                    stats["derived_forms"] += 1
            # Wiktionary links prefixed derivatives (diktovat -> nadiktovat)
            # even when the derivative has no standalone IPA entry. The prefix
            # does not change the base's di/ti/ni pronunciation, so propagate
            # the decision through the base paradigm.
            base_forms = [word, *(
                form.get("form")
                for form in entry.get("forms", [])
                if isinstance(form, dict) and isinstance(form.get("form"), str)
            )]
            for related in entry.get("related", []):
                related_word = related.get("word") if isinstance(related, dict) else None
                if (
                    not isinstance(related_word, str)
                    or not RUNTIME_WORD.fullmatch(related_word)
                    or not related_word.endswith(word)
                ):
                    continue
                prefix = related_word[: -len(word)]
                if prefix.casefold() not in PRODUCTIVE_PREFIXES:
                    continue
                for base_form in base_forms:
                    if not RUNTIME_WORD.fullmatch(base_form):
                        continue
                    base_hint = respell(base_form, decisions)
                    if not base_hint:
                        continue
                    derived_word = (prefix + base_form).casefold()
                    candidates[derived_word].add((prefix + base_hint).casefold())
                    stats["related_prefix_forms"] += 1
    ambiguous = {word for word, values in candidates.items() if len(values) != 1}
    entries = {
        word: next(iter(values))
        for word, values in candidates.items()
        if word not in ambiguous
    }
    stats["ambiguous_words_excluded"] = len(ambiguous)
    stats["runtime_entries"] = len(entries)
    return entries, dict(stats)


# Words that must keep a genuine English reading and never be pulled toward a
# Czech-accented one. Step 1 hardens di/ti/ni blindly from Wiktionary, which
# turns "meeting" into "meetyng" and destroys the English word; step 2 cannot
# override it, because the dump files "meeting" as a spelling variant of the
# lemma "mítink" and grafting refuses (the respelled stem "mítynk" no longer
# contains the form's). So the entry can only ever be INHERITED from step 1 —
# and this is what stops it.
#
# Build-time only. It used to live in spoken_text.py as a runtime guard for the
# di/ti/ni pipeline; with that pipeline gone from the server, the damage it
# patches only exists here.
CORPUS_EXCLUSIONS: frozenset[str] = frozenset({
    "meeting",  # must stay English, not "meetyng"
})


# Wiktionary IPA garbles that the general `_spurious_phoneme_swap` guard cannot
# catch because they live in an AMBIGUOUS substitution class (see that guard's
# note). c->č has both a correct member (cembalo -> "čembalo", Italian [tʃ]) and
# wrong ones, so it is not rule-blocked; the wrong ones are named here by written
# form. "akcelerometr" is [aktselerometr] — the c is [ts], never [tʃ] — so its
# documented respelling "akčelerometr" is noise. Grafted forms share the lemma's
# fate, so listing the whole paradigm is only defensive.
AMBIGUOUS_CLASS_DROP: frozenset[str] = frozenset(
    {
        "akcelerometr",
        "akcelerometre",
        "akcelerometrech",
        "akcelerometrem",
        "akcelerometru",
        "akcelerometry",
        "akcelerometrů",
        "akcelerometrům",
    }
)


# The respelling's own alphabet: ď/ť/ň before i/í are what the repair PRODUCES,
# so written Czech never contains them and they must not count as anomalies.
_RESPELL_ALPHABET = str.maketrans({"ď": "d", "ť": "t", "ň": "n"})


def _bigrams(word: str) -> list[str]:
    text = "^" + word.casefold().translate(_RESPELL_ALPHABET) + "$"
    return [text[i : i + 2] for i in range(len(text) - 1)]


# Below this many written forms the sample is not an authority on Czech
# orthography, and "never seen" stops meaning "impossible".
MIN_ORTHOGRAPHY_CORPUS = 5_000


def learn_czech_bigrams(path: Path) -> frozenset[str] | None:
    """Which letter pairs Czech actually writes, learned from the dump itself.

    Every headword and inflected form is a sample of real Czech orthography —
    ~850k of them — which is a far better authority on what the model has seen
    than any rule I could write down.

    Returns None when the sample is too small to judge anything (a test fixture,
    a truncated dump): an anomaly detector trained on three words calls
    everything an anomaly, and silently emptying the map is worse than shipping
    the odd stray bigram.
    """
    seen: set[str] = set()
    words = 0
    for entry in iter_jsonl(path):
        if entry.get("lang_code") != "cs":
            continue
        candidates = [entry.get("word"), *(
            form.get("form") for form in entry.get("forms", []) or []
            if isinstance(form, dict)
        )]
        for word in candidates:
            if isinstance(word, str) and RUNTIME_WORD.fullmatch(word):
                seen.update(_bigrams(word))
                words += 1
    return frozenset(seen) if words >= MIN_ORTHOGRAPHY_CORPUS else None


def unwritable_bigrams(
    written: str, spelling: str, known: frozenset[str] | None
) -> list[str]:
    """Letter pairs the respelling invents that Czech never writes.

    The point of the whole layer is to hand the model a spelling it can READ.
    A pair that occurs in none of ~850k Czech forms is one the model has never
    seen, so a respelling containing it fails on its own terms — whatever the
    IPA says. This is what catches the dump's stray characters: "čtyřka" is
    typed [tˈt͡ʃtɪr̝ka] and respells to "tčtyřka", and Czech has no "tč".
    Pairs the WRITTEN form already has are exempt: the word arrived that way.
    """
    if known is None:
        return []
    already = set(_bigrams(written))
    return [g for g in _bigrams(spelling) if g not in already and g not in known]


_SITE = re.compile(r"[dtnďťň][iíyý]")
# How much of the lemma an inflected form must share before the lemma is allowed
# to vouch for it.
MIN_SHARED_STEM = 0.6


def contradicts_its_lemma(written: str, spelling: str, lemma_ipas: list[str], lemma: str) -> bool:
    """True when a form's own IPA disagrees with its lemma's about the stem.

    Wiktionary transcribes lemma and forms as separate entries, so a typo can
    hit one and not the other: "šlehačka" is [ʃlɛɦat͡ʃka] (right) while the form
    "šlehačku" carries [ʃlɛɦaat͡ʃkʊ] (a doubled a) and respells to "šlehaačku".
    The paradigm is the cross-check the single entry lacks — if the lemma needs
    no repair, no form of it that merely re-endings it needs a STRUCTURAL one.

    Two things a lemma may NOT vouch for:

    - a form that does not share its stem. forms[] also carries SPELLING
      VARIANTS, and those legitimately need different repairs: "judo" is filed
      under the lemma "džudo", which of course reads correctly — and concluding
      "so judo does too" throws away the entry this layer exists to make. Same
      for meeting under mítink.
    - a di/ti/ni site, which an ending legitimately opens where the lemma has
      none ("hrad" is clean, "hradní" is not). That is the corpus's day job.
    """
    shared = len(os.path.commonprefix([lemma.casefold(), written.casefold()]))
    if shared < MIN_SHARED_STEM * len(lemma):
        return False
    if not any(reads_as(lemma, ipa) for ipa in lemma_ipas):
        return False  # the lemma needs repair itself; it cannot vouch for a form
    return _SITE.sub("#", spelling.casefold()) != _SITE.sub("#", written.casefold())


def _ipa_variants(entry: dict) -> list[str]:
    """Documented pronunciations, in the order Wiktionary lists them."""
    variants: list[str] = []
    for sound in entry.get("sounds", []) or []:
        if not isinstance(sound, dict):
            continue
        ipa = sound.get("ipa")
        if isinstance(ipa, str) and ipa not in variants:
            variants.append(ipa)
    return variants


def _linked_words(entry: dict, field: str, key: str) -> list[str]:
    out: list[str] = []
    for item in entry.get(field, []) or []:
        word = item.get(key) if isinstance(item, dict) else None
        if isinstance(word, str) and RUNTIME_WORD.fullmatch(word) and word not in out:
            out.append(word)
    return out


def graft_suffix(lemma: str, spelling: str, form: str) -> str | None:
    """Carry a lemma's respelling onto an inflected form (plan 4e).

    IPA is documented for the lemma only, so "screeningová" borrows
    "skrínyng" + "ová" from "screeningový". The shared stem must survive the
    respelling untouched, and the grafted result must still pin its reading
    down — an ending can open a di/ti/ni site the lemma's IPA never covered.
    """
    lemma_cf, form_cf = lemma.casefold(), form.casefold()
    shared = os.path.commonprefix([lemma_cf, form_cf])
    if not shared:
        return None
    lemma_tail, form_tail = lemma_cf[len(shared) :], form_cf[len(shared) :]
    if lemma_tail and not spelling.endswith(lemma_tail):
        return None  # the respelling reshaped the very part we would cut off
    stem = spelling[: len(spelling) - len(lemma_tail)] if lemma_tail else spelling
    grafted = stem + form_tail
    if grafted == form_cf or not is_unambiguous(grafted):
        return None
    return grafted


def extract_ipa_candidates(
    path: Path, di_ti_ni: dict[str, str]
) -> tuple[dict[str, str], list[dict], dict[str, int]]:
    """Build the shipped map, its review queue and its stats.

    It STARTS from step 1's di/ti/ni entries and overrides them wherever the IPA
    knows better, because step 1 buys coverage this pass cannot derive on its
    own: it resolves di/ti/ni per FORM, so it reaches stem-changing forms whose
    lemma carries no IPA (agonie -> agónie), which suffix grafting (plan 4e)
    explicitly skips. Building on it rather than beside it is worth ~3.9k
    entries that would otherwise silently regress.
    """
    variants: dict[str, list[str]] = defaultdict(list)
    forms: dict[str, list[str]] = defaultdict(list)
    related: dict[str, list[str]] = defaultdict(list)
    stats: dict[str, int] = defaultdict(int)

    for entry in iter_jsonl(path):
        if entry.get("lang_code") != "cs":
            continue
        word = entry.get("word")
        if not isinstance(word, str) or not RUNTIME_WORD.fullmatch(word):
            continue
        for ipa in _ipa_variants(entry):
            if ipa not in variants[word]:
                variants[word].append(ipa)
        for form in _linked_words(entry, "forms", "form"):
            if form not in forms[word]:
                forms[word].append(form)
        for word_related in _linked_words(entry, "related", "word"):
            if word_related not in related[word]:
                related[word].append(word_related)

    # Which lemma each form belongs to, for the paradigm cross-check below.
    lemma_of: dict[str, str] = {}
    for lemma in sorted(forms):
        for form in forms[lemma]:
            if form != lemma and form not in lemma_of and variants.get(lemma):
                lemma_of[form] = lemma

    known_bigrams = learn_czech_bigrams(path)
    stats["czech_word_entries"] = len(variants)
    candidates: dict[str, set[str]] = defaultdict(set)
    review: list[dict] = []
    lemma_spelling: dict[str, str] = {}

    for word in sorted(variants):
        ipas = variants[word]
        if not ipas:
            # A word Wiktionary lists with no pronunciation at all; it can still
            # pick up an entry later as a form or a prefixed derivative.
            stats["no_ipa"] += 1
            continue
        verdict, spelling, considered = decide_respelling(word, ipas)
        stats[verdict] += 1
        if verdict in (
            Verdict.REVIEW_CONFLICTING,
            Verdict.REVIEW_DISSIMILAR,
            Verdict.REVIEW_SPURIOUS_PHONEME,
            Verdict.REVIEW_SPURIOUS_SOFTENING,
        ):
            review.append(
                {
                    "word": word,
                    "reason": verdict,
                    "ipa": ipas,
                    "transliterations": considered,
                    "similarity": round(similarity(word, considered[0]), 3)
                    if considered
                    else None,
                }
            )
            continue
        if verdict != Verdict.IN_MAP or spelling is None:
            continue
        # Only step 2 can be blamed for INVENTING a pair. When step 1 ships the
        # identical string anyway (odiózní -> "odyózňí", whose "yó" is odd only
        # because ó is rare), the pair comes from the ear-tested di/ti/ni device
        # and the word goes out unchanged either way — asking a human about it
        # is noise in a queue whose whole value is that everything in it matters.
        unwritable = (
            []
            if di_ti_ni.get(word.casefold()) == spelling
            else unwritable_bigrams(word, spelling, known_bigrams)
        )
        if unwritable:
            stats["review_unwritable"] += 1
            review.append(
                {
                    "word": word,
                    "reason": "review_unwritable",
                    "ipa": ipas,
                    "transliterations": [spelling],
                    "unwritable_bigrams": unwritable,
                    "similarity": round(similarity(word, spelling), 3),
                }
            )
            continue
        lemma = lemma_of.get(word)
        if lemma and contradicts_its_lemma(word, spelling, variants[lemma], lemma):
            stats["review_paradigm_conflict"] += 1
            review.append(
                {
                    "word": word,
                    "reason": "review_paradigm_conflict",
                    "ipa": ipas,
                    "transliterations": [spelling],
                    "lemma": lemma,
                    "lemma_ipa": variants[lemma],
                    "similarity": round(similarity(word, spelling), 3),
                }
            )
            continue
        lemma_spelling[word] = spelling
        candidates[word.casefold()].add(spelling)

    # 4e: inflected forms borrow the lemma's decision...
    for lemma in sorted(lemma_spelling):
        for form in forms.get(lemma, []):
            if form in variants and variants[form]:
                continue  # the form documents its own IPA; it was decided above
            grafted = graft_suffix(lemma, lemma_spelling[lemma], form)
            if grafted:
                candidates[form.casefold()].add(grafted)
                stats["derived_forms"] += 1

    # ...and so do prefixed derivatives, which Wiktionary links but rarely
    # transcribes (diktovat -> nadiktovat). Same mechanism as step 1's.
    for lemma in sorted(lemma_spelling):
        for derived in related.get(lemma, []):
            if not derived.endswith(lemma):
                continue
            prefix = derived[: -len(lemma)]
            if prefix.casefold() not in PRODUCTIVE_PREFIXES:
                continue
            for base in [lemma, *forms.get(lemma, [])]:
                base_spelling = (
                    lemma_spelling[lemma]
                    if base == lemma
                    else graft_suffix(lemma, lemma_spelling[lemma], base)
                )
                if not base_spelling:
                    continue
                spelling = prefix.casefold() + base_spelling
                if not is_unambiguous(spelling):
                    continue
                candidates[(prefix + base).casefold()].add(spelling)
                stats["related_prefix_forms"] += 1

    ambiguous = {word for word, values in candidates.items() if len(values) != 1}
    transliterated = {
        word: next(iter(values))
        for word, values in candidates.items()
        if word not in ambiguous
    }
    # Inheriting step 1's entries means inheriting its guard with them: nothing
    # downstream will catch "meetyng" any more. A word step 2 decides ITSELF is
    # unaffected — that respelling comes from the word's own documented
    # pronunciation ("mítyng"), which is the outcome we want.
    inherited = {
        word: spelling
        for word, spelling in di_ti_ni.items()
        if word not in CORPUS_EXCLUSIONS
    }
    # Override, never union: a word the IPA pass decided must not collide with
    # its step-1 entry and get dropped as ambiguous.
    merged = {**inherited, **transliterated}
    # `decide_respelling` already routes spurious softenings to review, but a
    # grafted or di/ti/ni-inherited form never passes through it — filter the
    # merged map once more so an unlicensed ď/ť/ň can never reach the box.
    entries = {
        word: spelling
        for word, spelling in merged.items()
        if word not in AMBIGUOUS_CLASS_DROP and not _spurious_softening(word, spelling)
    }
    stats["ambiguous_class_dropped"] = len(merged) - len(entries)
    stats["ambiguous_words_excluded"] = len(ambiguous)
    stats["review_queue"] = len(review)
    stats["transliterated_entries"] = len(transliterated)
    stats["inherited_from_di_ti_ni"] = len(entries) - len(transliterated)
    stats["runtime_entries"] = len(entries)
    return entries, sorted(review, key=lambda item: item["word"]), dict(stats)


def diff_against_baseline(baseline: dict[str, str], entries: dict[str, str]) -> dict:
    """Report what this map changes against a baseline (plan 4f).

    (a) words the baseline respells that this map drops — regression candidates,
    (b) words both respell differently, (c) words only this map respells. All
    three need ears before the map ships.
    """
    missing = sorted(word for word in baseline if word not in entries)
    changed = sorted(
        word for word in entries if word in baseline and baseline[word] != entries[word]
    )
    # Words the baseline never respelled at all. This is the bucket the foreign
    # class lives in (judo -> "džudo"), so it is the LARGEST behavioural change
    # the map makes — and reporting only missing/changed hid all of it from the
    # ear audit that is supposed to gate the rollout.
    added = sorted(word for word in entries if word not in baseline)
    return {
        "baseline_entries": len(baseline),
        "ipa_entries": len(entries),
        "missing_from_ipa_count": len(missing),
        "changed_count": len(changed),
        "added_count": len(added),
        "missing_from_ipa": {word: baseline[word] for word in missing},
        "changed": {
            word: {"baseline": baseline[word], "ipa": entries[word]} for word in changed
        },
        "added": {word: entries[word] for word in added},
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "mendelio-pronunciation-map-builder/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def fetch_source_metadata(page_url: str = SOURCE_PAGE) -> dict[str, str]:
    request = urllib.request.Request(page_url, headers={"User-Agent": "mendelio-pronunciation-map-builder/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        page = response.read().decode("utf-8")
    patterns = {
        "extraction_date": r"extracted on (\d{4}-\d{2}-\d{2})",
        "wiktionary_dump_date": r"cswiktionary dump dated (\d{4}-\d{2}-\d{2})",
        "wiktextract_commit": r"wiktextract/commit/([0-9a-f]+)",
        "wikitextprocessor_commit": r"wikitextprocessor/commit/([0-9a-f]+)",
    }
    metadata = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, page)
        if not match:
            raise RuntimeError(f"Kaikki source metadata is missing {key}")
        metadata[key] = match.group(1)
    return metadata


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def build(
    source: Path,
    output: Path,
    *,
    ipa_output: Path | None = None,
    review_output: Path | None = None,
    diff_output: Path | None = None,
    diff_baseline: Path | None = None,
    source_url: str = SOURCE_URL,
    source_metadata: dict[str, str],
) -> dict:
    digest = sha256(source)
    header = {
        "format_version": FORMAT_VERSION,
        "license": LICENSE,
        "source_page": SOURCE_PAGE,
        "source_url": source_url,
        "source_sha256": digest,
        "source_metadata": source_metadata,
    }

    entries, stats = extract_candidates(source)
    payload = {**header, "stats": stats, "entries": dict(sorted(entries.items()))}
    _write_json(output, payload)

    if ipa_output is None:
        return payload

    ipa_entries, review, ipa_stats = extract_ipa_candidates(source, entries)
    ipa_payload = {
        **header,
        "stats": ipa_stats,
        "entries": dict(sorted(ipa_entries.items())),
    }
    _write_json(ipa_output, ipa_payload)
    if review_output is not None:
        _write_json(review_output, {**header, "review": review})
    if diff_output is not None:
        # Default baseline is step 1 of this run (apples to apples: what the IPA
        # pass itself changed). Point --diff-baseline at a previously SHIPPED map
        # to answer the question that decides a rollout instead: what changes for
        # production.
        baseline = entries
        if diff_baseline is not None:
            baseline = json.loads(diff_baseline.read_text(encoding="utf-8"))["entries"]
        _write_json(diff_output, {**header, **diff_against_baseline(baseline, ipa_entries)})
    payload["ipa_stats"] = ipa_stats
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="Existing Wiktextract JSONL or JSONL.GZ")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ipa-output", type=Path, default=DEFAULT_IPA_OUTPUT)
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW_OUTPUT)
    parser.add_argument("--diff-output", type=Path, default=DEFAULT_DIFF_OUTPUT)
    parser.add_argument(
        "--diff-baseline",
        type=Path,
        help="Map to diff against (default: this run's own step-1 output)",
    )
    parser.add_argument("--source-url", default=SOURCE_URL)
    parser.add_argument("--extraction-date")
    parser.add_argument("--wiktionary-dump-date")
    parser.add_argument("--wiktextract-commit")
    parser.add_argument("--wikitextprocessor-commit")
    args = parser.parse_args()
    supplied_metadata = {
        "extraction_date": args.extraction_date,
        "wiktionary_dump_date": args.wiktionary_dump_date,
        "wiktextract_commit": args.wiktextract_commit,
        "wikitextprocessor_commit": args.wikitextprocessor_commit,
    }
    if args.input:
        missing = [key for key, value in supplied_metadata.items() if not value]
        if missing:
            parser.error("--input requires source metadata: " + ", ".join(missing))
        payload = build(
            args.input,
            args.output,
            ipa_output=args.ipa_output,
            review_output=args.review_output,
            diff_output=args.diff_output,
            diff_baseline=args.diff_baseline,
            source_url=args.source_url,
            source_metadata={key: value for key, value in supplied_metadata.items() if value},
        )
    else:
        with tempfile.TemporaryDirectory(prefix="czech-pronunciation-") as temporary:
            source = Path(temporary) / "cswiktionary.jsonl.gz"
            download(args.source_url, source)
            payload = build(
                source,
                args.output,
                ipa_output=args.ipa_output,
                review_output=args.review_output,
                diff_output=args.diff_output,
                source_url=args.source_url,
                source_metadata=fetch_source_metadata(),
            )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "ipa_output": str(args.ipa_output),
                "di_ti_ni_stats": payload["stats"],
                "ipa_stats": payload.get("ipa_stats", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
