#!/usr/bin/env python3
"""Deterministic IPA -> Czech-orthography transliteration (build time only).

Czech orthography is nearly phonemic, so a documented IPA pronunciation can be
rewritten as a Czech spelling the TTS model reads letter by letter, without
relying on the model's knowledge of the source language ("meeting" [miːtɪŋk] ->
"mítyng"). This module is the pure-function core of that rewrite; the builder
(build_czech_pronunciation_map.py) applies it across a Wiktextract dump.

Safety rule: an IPA symbol this table does not know makes the WORD get dropped,
never silently mistransliterated. The Czech Wiktionary IPA is crowd-sourced and
contains foreign phonemes, typos and homoglyphs; dropping is the only safe
default (a wrong respelling is worse than no respelling).

Nothing here is imported at runtime — the package only reads the generated
JSON map.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


# --- Source cleanup ---------------------------------------------------------

# Homoglyphs and notation variants that mean an ASCII/standard symbol. Czech
# Wiktionary is hand-edited, so LATIN SMALL LETTER SCRIPT G, a plain colon for
# the length mark and SMALL CAPITAL OPEN O all occur. Normalizing them is safe
# (the intent is unambiguous); anything genuinely foreign is left alone so the
# unknown-symbol rule drops the word.
_HOMOGLYPHS = {
    "ɡ": "g",       # ɡ LATIN SMALL LETTER SCRIPT G -> g
    "ᴐ": "ɔ",  # ᴐ SMALL CAPITAL OPEN O -> ɔ
    "ε": "ɛ",  # ε GREEK SMALL LETTER EPSILON -> ɛ
    "χ": "x",       # χ GREEK SMALL LETTER CHI -> x
    ":": "ː",  # : COLON -> ː length mark
    "ˀ": "ʔ",  # ˀ GLOTTAL STOP MODIFIER -> ʔ
    "ɱ": "m",       # ɱ labiodental nasal: allophone of /m/ before f/v
    "ɫ": "l",       # ɫ velarized l: allophone of /l/
    "’": "'",
}

# Suprasegmentals and boundary marks carry no orthographic content.
_IGNORED = frozenset("ˈˌ.'‿ʔ ̃͡")

_STRIP_OUTER = re.compile(r"^[\[\]/\s]+|[\[\]/\s]+$")


def clean_ipa(ipa: str) -> str:
    """Strip delimiters/whitespace and fold notation variants to one spelling."""
    text = unicodedata.normalize("NFD", ipa)
    text = _STRIP_OUTER.sub("", text)
    return "".join(_HOMOGLYPHS.get(char, char) for char in text)


# --- Phoneme table ----------------------------------------------------------

# Longest-match-first: multi-codepoint sequences (affricates, diphthongs,
# syllabic consonants, ř) must be tried before their leading symbol alone.
_SEQUENCES: tuple[tuple[str, str], ...] = (
    # ř: [r̝] voiced, [r̝̊] voiceless — Czech spells both "ř".
    ("r̝̊", "ř"),
    ("r̝", "ř"),
    # Affricates. ONLY the tie-barred forms: a bare "ts" is [t]+[s] across a
    # morpheme seam (odstranil [ˈɔtstranɪl]), and reading it as [t͡s] shipped
    # "octraňil".
    ("t͡s", "c"),
    ("t͡ʃ", "č"),
    ("d͡z", "dz"),
    ("d͡ʒ", "dž"),
    # Diphthongs. The non-syllabic mark sits on the glide; both ʊ̯/ɪ̯ and the
    # plain-letter u̯/i̯ spellings occur in the dump.
    ("ɔʊ̯", "ou"),
    ("ɔu̯", "ou"),
    ("aʊ̯", "au"),
    ("au̯", "au"),
    ("ɛʊ̯", "eu"),
    ("ɛu̯", "eu"),
    ("aɪ̯", "aj"),
    ("ai̯", "aj"),
    ("ɛɪ̯", "ej"),
    ("ɛi̯", "ej"),
    ("ɔɪ̯", "oj"),
    ("ɔi̯", "oj"),
    # Syllabic consonants: Czech writes them as the bare consonant (vlk, prst).
    ("l̩", "l"),
    ("r̩", "r"),
    ("m̩", "m"),
    ("n̩", "n"),
    # Long vowels.
    ("aː", "á"),
    ("ɛː", "é"),
    ("ɔː", "ó"),
    ("uː", "ú"),
    ("ʊː", "ú"),
    # [iː]/[ɪ] are deliberately absent: they resolve contextually (_vowel_i).
)

# Single symbols. [ɪ] and [iː] are resolved contextually (see _vowel_i).
_SINGLES: dict[str, str] = {
    "a": "a",
    "ɛ": "e",
    "ɔ": "o",
    "ʊ": "u",
    "u": "u",
    "i": "i",
    "e": "e",
    "o": "o",
    "c": "ť",
    "ɟ": "ď",
    "ɲ": "ň",
    "ʃ": "š",
    "ʒ": "ž",
    "x": "ch",
    "ɦ": "h",
    "ŋ": "n",  # Czech reads "n" as [ŋ] before k/g by itself
    "p": "p",
    "b": "b",
    "t": "t",
    "d": "d",
    "k": "k",
    "g": "g",
    "f": "f",
    "v": "v",
    "s": "s",
    "z": "z",
    "m": "m",
    "n": "n",
    "l": "l",
    "r": "r",
    "j": "j",
}

# After a hard d/t/n the vowel must be written y/ý, which is what forces the
# model's hard reading; everywhere else i/í. Soft ď/ť/ň already carry the
# palatalization, so they take i/í.
_HARD_BEFORE_I = frozenset("dtn")


class UnknownSymbol(Exception):
    """An IPA symbol outside the table — the caller must drop the word."""

    def __init__(self, symbol: str) -> None:
        super().__init__(symbol)
        self.symbol = symbol


def _vowel_i(out: list[str], long: bool) -> str:
    previous = out[-1][-1:] if out else ""
    hard = previous in _HARD_BEFORE_I
    if long:
        return "ý" if hard else "í"
    return "y" if hard else "i"


def ipa_to_czech(ipa: str) -> str:
    """Transliterate one IPA word into Czech orthography.

    Raises UnknownSymbol when the table cannot account for a symbol.
    """
    text = clean_ipa(ipa)
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char in _IGNORED:
            index += 1
            continue
        for sequence, spelling in _SEQUENCES:
            if text.startswith(sequence, index):
                out.append(spelling)
                index += len(sequence)
                break
        else:
            if text.startswith("ɪ", index) or text.startswith("iː", index):
                long = text.startswith("iː", index)
                out.append(_vowel_i(out, long=long))
                index += 2 if long else 1
                continue
            spelling = _SINGLES.get(char)
            if spelling is None:
                raise UnknownSymbol(char)
            out.append(spelling)
            index += 1
    return "".join(out)


# --- Final devoicing --------------------------------------------------------

# Czech IPA records word-final devoicing ([miːtɪŋk], [viːkɛnt]). Spelling it out
# would be wrong: Czech devoices finals on its own when reading, and the
# oblique cases need the voiced letter back ("mítyngu" [gʊ], not "mítynku").
# So when the written form ends voiced, restore the voiced letter.
_DEVOICED_TO_VOICED = {
    "k": "g",
    "t": "d",
    "ť": "ď",
    "p": "b",
    "s": "z",
    "š": "ž",
    "f": "v",
    "ch": "h",
}


def restore_final_voicing(written: str, spoken: str) -> str:
    """Undo the IPA's word-final devoicing when the spelling stays voiced."""
    source = written.casefold()
    for devoiced, voiced in _DEVOICED_TO_VOICED.items():
        if not spoken.endswith(devoiced):
            continue
        # "ch" ends in "h", so a naive suffix test re-voices every locative
        # plural: abdikacích -> "abdykacíh". Only a BARE final h is the voiced
        # counterpart of [x] (sníh [sɲiːx] -> "sňíh").
        if voiced == "h" and source.endswith("ch"):
            continue
        if source.endswith(voiced):
            return spoken[: -len(devoiced)] + voiced
    return spoken


# --- Model G2P --------------------------------------------------------------

# How OmniVoice reads a Czech spelling. This models the MODEL, not the norm:
# it applies the regular Czech reading rules, except that written di/ti/ni is
# marked UNREADABLE rather than given a pronunciation.
#
# Marking rather than hardening is deliberate. The model does not merely harden
# di/ti/ni — it is unreliable in BOTH directions: it reads soft "nivu" hard
# ([nɪvʊ]) and hard "tipnout" soft ([cɪpnɔʊ̯t], see _PARADIGM_RESPELLINGS in
# spoken_text.py). So a written di/ti/ni predicts nothing, and every such site
# has to be spelled out explicitly — hard as dy/ty/ny, soft as ďi/ťi/ňi. That is
# exactly what step 1 of the build does, and why entries like audit -> "audyt" that
# look like no-ops are really insurance against a coin-flip.
#
# Anchoring the gate on this function (rather than on textual difference) is
# what keeps the map honest: a word is worth respelling only when the model's
# reading of the WRITTEN form fails to deliver the documented pronunciation.
# Czech spelling choices the reading rules neutralize anyway (i/y, ú/ů, ě,
# voicing assimilation) then never reach the map.
#
# Every rule here asserts "the model gets this right". Only di/ti/ni is claimed
# unreliable, because only di/ti/ni was verified wrong by ear.
AMBIGUOUS = "�"
_MODEL_G2P_SEQUENCES: tuple[tuple[str, str], ...] = (
    ("dě", "ɟɛ"), ("tě", "cɛ"), ("ně", "ɲɛ"), ("mě", "mɲɛ"),
    ("bě", "bjɛ"), ("pě", "pjɛ"), ("vě", "vjɛ"), ("fě", "fjɛ"),
    ("ch", "x"), ("dž", "d͡ʒ"), ("dz", "d͡z"),
    ("ou", "ɔʊ̯"), ("au", "aʊ̯"), ("eu", "ɛʊ̯"),
    # THE BUG: written di/ti/ni does not determine what the model says.
    ("di", AMBIGUOUS), ("ti", AMBIGUOUS), ("ni", AMBIGUOUS),
    ("dí", AMBIGUOUS), ("tí", AMBIGUOUS), ("ní", AMBIGUOUS),
)
_MODEL_G2P_SINGLES = {
    "a": "a", "á": "aː",
    "e": "ɛ", "é": "ɛː",
    "i": "ɪ", "í": "iː",
    "y": "ɪ", "ý": "iː",
    "o": "ɔ", "ó": "ɔː",
    "u": "ʊ", "ú": "uː", "ů": "uː",
    "ď": "ɟ", "ť": "c", "ň": "ɲ",
    "š": "ʃ", "ž": "ʒ", "č": "t͡ʃ", "c": "t͡s",
    "ř": "r̝", "h": "ɦ", "j": "j",
    "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "g",
    "f": "f", "v": "v", "s": "s", "z": "z",
    "m": "m", "n": "n", "l": "l", "r": "r",
}

# Voicing assimilation. Czech neutralizes obstruent voicing regressively (the
# last obstruent of a cluster decides) and devoices word-finally: "odpad" reads
# [ɔtpat], "vsadit" [fsaɟɪt]. Reading applies this by itself, so spelling it out
# would be pure churn.
_VOICING_PAIRS = (
    ("b", "p"), ("d", "t"), ("ɟ", "c"), ("g", "k"),
    ("z", "s"), ("ʒ", "ʃ"), ("d͡z", "t͡s"), ("d͡ʒ", "t͡ʃ"), ("ɦ", "x"),
)
_DEVOICE = {voiced: voiceless for voiced, voiceless in _VOICING_PAIRS}
_VOICE = {voiceless: voiced for voiced, voiceless in _VOICING_PAIRS}
# "v" assimilates but does not trigger assimilation in what precedes it.
_DEVOICE_PASSIVE = {"v": "f"}
_SONORANTS = frozenset({"m", "n", "ɲ", "ŋ", "l", "r", "j"})
_VOWELS = frozenset({"a", "ɛ", "ɔ", "ʊ", "u", "i", "ɪ", "e", "o", "ɔʊ̯", "aʊ̯", "ɛʊ̯"})


def _phonemes(spoken: str) -> list[str]:
    """Split a phoneme string into units, keeping affricates/ř together."""
    units: list[str] = []
    index = 0
    multi = ("t͡s", "t͡ʃ", "d͡z", "d͡ʒ", "r̝̊", "r̝", "ɔʊ̯", "aʊ̯", "ɛʊ̯")
    while index < len(spoken):
        for unit in multi:
            if spoken.startswith(unit, index):
                units.append(unit)
                index += len(unit)
                break
        else:
            unit = spoken[index]
            index += 1
            while index < len(spoken) and unicodedata.combining(spoken[index]):
                unit += spoken[index]
                index += 1
            units.append(unit)
    return units


def _assimilate(units: list[str]) -> list[str]:
    """Apply regressive voicing assimilation and word-final devoicing."""
    out = list(units)
    voiced = set(_DEVOICE) | set(_DEVOICE_PASSIVE)
    voiceless = set(_VOICE)
    obstruents = voiced | voiceless
    # Word-final devoicing seeds the cascade from the right.
    for index in range(len(out) - 1, -1, -1):
        unit = out[index]
        if unit not in obstruents:
            continue
        following = out[index + 1] if index + 1 < len(out) else None
        if following is None:
            out[index] = _DEVOICE.get(unit, _DEVOICE_PASSIVE.get(unit, unit))
            continue
        if following in _SONORANTS or following not in obstruents:
            continue
        # "v" is transparent: it assimilates, but never voices what precedes it.
        if following in _DEVOICE_PASSIVE:
            continue
        if following in voiceless:
            out[index] = _DEVOICE.get(unit, _DEVOICE_PASSIVE.get(unit, unit))
        else:
            out[index] = _VOICE.get(unit, unit)
    # Czech degeminates CONSONANTS: "francouzský" is [frant͡sɔʊ̯skiː], not
    # [...sskiː]. Vowels keep their gemination — "neetický" is [nɛɛcɪt͡skiː] and
    # collapsing it would silently turn the word into "netický".
    degeminated: list[str] = []
    for unit in out:
        if degeminated and degeminated[-1] == unit and unit not in _VOWELS:
            continue
        degeminated.append(unit)
    return degeminated


_NASAL_ASSIM = re.compile(r"n(?=[kg])")


def model_g2p(word: str) -> str | None:
    """What OmniVoice says when handed this Czech spelling (None = can't read).

    None means the spelling contains letters Czech reading rules do not cover
    (English "w", "q", doubled "ee"...) — exactly the words whose reading the
    model resolves through another language, and the words this corpus targets.
    """
    text = unicodedata.normalize("NFC", word.casefold())
    out: list[str] = []
    index = 0
    while index < len(text):
        for sequence, phonemes in _MODEL_G2P_SEQUENCES:
            if text.startswith(sequence, index):
                out.append(phonemes)
                index += len(sequence)
                break
        else:
            phoneme = _MODEL_G2P_SINGLES.get(text[index])
            if phoneme is None:
                return None
            out.append(phoneme)
            index += 1
    spoken = _NASAL_ASSIM.sub("ŋ", "".join(out))
    return "".join(_assimilate(_phonemes(spoken)))


# Folding both sides into one alphabet before comparing. Vowel length goes (the
# respelling may legitimately carry a length the written form lacks), and so
# does obstruent voicing IN THE POSITIONS CZECH NEUTRALIZES IT: word-finally and
# inside an obstruent cluster. There, the last obstruent decides for the whole
# cluster and no spelling can overrule it — "noutbuk" is read [nɔʊ̯dbuk] however
# carefully Wiktionary writes [ˈnɔʊ̯t.buk] across the compound seam.
#
# Only those positions. Voicing stays contrastive between vowels, which is what
# keeps the genuine repair "anisotropní" -> "anyzotropňí" ([z], not [s]) from
# being folded away as noise.
# U+0329 (syllabic) is dropped too: Czech writes a syllabic consonant as the
# bare letter ("vlk", "osm"), so no spelling can mark it and it must not
# decide a comparison. Keeping it made "osm" fail the round-trip against its
# own [ɔsm̩] and left only the colloquial [ɔsʊm] standing -> "osum".
_COMPARISON_DROPPED = frozenset("ːˈˌ.'‿ʔ ̯̩̊̃͡")
_COMPARISON_FOLDED = {"ʊ": "u", "ɪ": "i", "ɡ": "g"}
_FINAL_OBSTRUENT = {
    "g": "k", "d": "t", "ɟ": "c", "b": "p", "z": "s", "ʒ": "ʃ", "v": "f",
    "ɦ": "x", "d͡z": "t͡s", "d͡ʒ": "t͡ʃ",
}
# ř is an OBSTRUENT (a raised fricative trill), not a sonorant: it devoices next
# to voiceless obstruents and devoices what precedes it. Leaving it out made
# "obřad" [ˈɔpr̝̊at] unreachable for any spelling with a b, so the layer
# "repaired" the only thing it could — the letter — and shipped "opřad".
# Czech spells voiced and voiceless ř alike, so its own voicing is not something
# a spelling can control; what matters is that it neutralizes the consonant
# before it, exactly like any other obstruent cluster.
_OBSTRUENTS = (
    frozenset(_FINAL_OBSTRUENT) | frozenset(_FINAL_OBSTRUENT.values()) | {"r̝"}
)


def fold_phonemes(ipa: str) -> str:
    """Reduce a phoneme string to the distinctions a spelling can actually control."""
    text = unicodedata.normalize("NFD", ipa)
    text = "".join(
        _COMPARISON_FOLDED.get(char, char)
        for char in text
        if char not in _COMPARISON_DROPPED
    )
    units = _phonemes(text)
    folded = []
    for index, unit in enumerate(units):
        following = units[index + 1] if index + 1 < len(units) else None
        if unit in _OBSTRUENTS and (following is None or following in _OBSTRUENTS):
            unit = _FINAL_OBSTRUENT.get(unit, unit)
        folded.append(unit)
    return "".join(folded)


def reads_as(spelling: str, ipa: str) -> bool:
    """True when the model, handed this spelling, says what the IPA documents.

    False for any spelling holding an unresolved di/ti/ni site: such a spelling
    does not pin the reading down, whichever way the coin lands.
    """
    spoken = model_g2p(spelling)
    if spoken is None or AMBIGUOUS in spoken:
        return False
    return fold_phonemes(spoken) == fold_phonemes(clean_ipa(ipa))


def is_unambiguous(spelling: str) -> bool:
    """True when this spelling pins the reading down for the model.

    Used to vet grafted forms and prefixed derivatives, whose suffix/prefix
    can open a di/ti/ni site the lemma's IPA never covered.
    """
    spoken = model_g2p(spelling)
    return spoken is not None and AMBIGUOUS not in spoken


# --- Sanity filters against Wiktionary noise --------------------------------

# Czech Wiktionary is crowd-sourced and its IPA field is not always this word's
# pronunciation: "šestnáctipodlažní" carries the IPA of "dvoupodlažní",
# "Moravcovi" the IPA of "panu", and a number of entries hold a truncated stub
# ("[ˈʔa") or nothing at all ("[]"). Unfiltered, "břidlicový" respells to the
# EMPTY STRING.
#
# Note what is deliberately NOT filtered here: the plan's "first phoneme must
# match the first letter" rule would drop judo -> "džudo" and e-mail -> "ímejl",
# i.e. precisely the foreign words this map exists for. Low similarity is no
# good as a drop rule either — "šestnáctipodlažní"/"dvoupodlažňí" (0.48) scores
# HIGHER than the legitimate "bouquet"/"buké" (0.36). Similarity therefore
# routes to the review queue for human ears, never to a silent drop.
MIN_PHONEME_RATIO = 0.6
MAX_PHONEME_RATIO = 1.6
REVIEW_SIMILARITY = 0.6


def ipa_is_usable(written: str, ipa: str) -> str | None:
    """Return the reason this IPA cannot describe this word, or None if it can."""
    cleaned = clean_ipa(ipa)
    stripped = "".join(char for char in cleaned if char not in _IGNORED)
    if not stripped:
        return "empty_ipa"
    if " " in cleaned.strip():
        # A phrase's IPA parked on a single-word entry (H₂O, CIA, Moravcovi).
        return "phrase_ipa"
    # Count PHONEMES: _phonemes keeps affricates and diphthongs together, but
    # only if the tie bar survives, so count on the cleaned form, not the
    # tie-stripped one.
    ratio = len(_phonemes(cleaned.strip())) / len(written)
    if not MIN_PHONEME_RATIO <= ratio <= MAX_PHONEME_RATIO:
        return "length_ratio"
    return None


def similarity(written: str, spoken: str) -> float:
    """How far the respelling strays from the written form (1.0 = identical)."""
    return SequenceMatcher(
        None, _fold_spelling(written), _fold_spelling(spoken), autojunk=False
    ).ratio()


# --- Anchoring the respelling to the written form ---------------------------


# Spelling distinctions Czech reading neutralizes. Folding them makes the
# written form and the IPA-derived candidate line up for alignment, which is
# what lets the written choice win where the sound is indifferent to it.
_SPELLING_FOLD = str.maketrans({"y": "i", "ý": "í", "ů": "ú"})


def _fold_spelling(word: str) -> str:
    return unicodedata.normalize("NFC", word.casefold()).translate(_SPELLING_FOLD)


def anchor_to_written(written: str, candidate: str, ipa: str) -> str:
    """Restore written letters wherever they don't change what the model says.

    The IPA fixes the SOUND, never the spelling: Czech writes [iː] as í or ý and
    [uː] as ú or ů with no phonetic difference, so a spelling rebuilt from IPA
    alone "corrects" být to bít and dům to dúm. Only the model's misreadings
    justify a change, so every departure from the written form must earn itself
    by changing the reading. reads_as is the guard that makes it earn it:
    "vsadit" keeps its v ([fsaɟɪt] either way) and only the di the model cannot
    resolve becomes ď -> "vsaďit".

    Alignment runs on folded spellings so that homophones pair up positionally;
    comparing raw forms makes difflib match cynický's y to the wrong slot.
    """
    source = unicodedata.normalize("NFC", written.casefold())
    best = candidate

    def closeness(word: str) -> float:
        return SequenceMatcher(None, source, word, autojunk=False).ratio()

    improved = True
    while improved:
        improved = False
        score = closeness(best)
        opcodes = SequenceMatcher(
            None, _fold_spelling(source), _fold_spelling(best), autojunk=False
        ).get_opcodes()
        trials: list[str] = []
        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                # Folded-equal still hides raw differences (y vs i) — exactly
                # where the written spelling should win.
                trials += [
                    best[: j1 + offset] + source[i1 + offset] + best[j1 + offset + 1 :]
                    for offset in range(i2 - i1)
                    if source[i1 + offset] != best[j1 + offset]
                ]
                continue
            # Sub-spans matter: restoring "ět" wholesale over "jeť" would drag
            # the ť back to t and re-open the di/ti/ni site, so "květina" would
            # lose to "kvjeťina". Offering "ě" for "je" alone keeps both wins.
            #
            # A replacement must still replace: adopting a written letter
            # WITHOUT dropping the candidate's turns "anyzotropňí" into
            # "anyszotropňí", which survives reads_as only because Czech
            # assimilates and degeminates the "sz" back to [z].
            replacing = i2 > i1 and j2 > j1
            trials += [
                best[:j1] + source[i1 : i1 + take] + best[j1 + drop :]
                for take in range(i2 - i1, 0 if replacing else -1, -1)
                for drop in range(j2 - j1, 0 if replacing else -1, -1)
                if take or drop
            ]
        for trial in sorted(set(trials), key=closeness, reverse=True):
            # Strictly-increasing closeness keeps the hill-climb terminating.
            # The respelling may never GROW while being pulled back toward the
            # written form: Czech degeminates, so "billtén" reads exactly like
            # "biltén" and scores closer to "bulletin" — reads_as would wave it
            # through. Shortest spelling that reads right wins.
            if len(trial) > len(best) or closeness(trial) <= score:
                continue
            if reads_as(trial, ipa):
                best, improved = trial, True
                break
    return best


# --- The decision -----------------------------------------------------------


class Verdict:
    """Why a word did or did not earn a respelling."""

    IN_MAP = "in_map"
    READS_CORRECTLY = "reads_correctly"
    REVIEW_CONFLICTING = "review_conflicting_variants"
    REVIEW_DISSIMILAR = "review_dissimilar"
    REVIEW_LOST_HACEK = "review_lost_hacek"
    REVIEW_SPURIOUS_PHONEME = "review_spurious_phoneme"
    REVIEW_SPURIOUS_SOFTENING = "review_spurious_softening"
    DROP_TRANSPOSED_IPA = "drop_transposed_ipa"
    DROP_UNKNOWN_SYMBOL = "drop_unknown_symbol"
    DROP_ROUND_TRIP = "drop_round_trip"


def decide_respelling(written: str, ipas: list[str]) -> tuple[str, str | None, list[str]]:
    """Decide the model-facing spelling for one word.

    Returns (verdict, spelling, considered) where `considered` lists the
    transliterations that survived, for the review queue to show a human.
    """
    usable = [ipa for ipa in ipas if not ipa_is_usable(written, ipa)]
    if not usable:
        return Verdict.DROP_ROUND_TRIP, None, []
    # Reading the written form already delivers a documented pronunciation, so
    # there is nothing to repair — this is what keeps být, dům and město out.
    if any(reads_as(written, ipa) for ipa in usable):
        return Verdict.READS_CORRECTLY, None, []
    # The written form contains exactly the right sounds, just in another order:
    # the transcription is a typo, not a pronunciation. "odstoupí" reads
    # [ɔtstɔʊ̯piː] and the dump types [ɔt͡stɔpʊiː] — the same phonemes with two
    # transposed — which would respell it to "octopuí". Czech never metathesizes
    # against its own spelling, so a permutation is always the typist's, and a
    # genuine loanword never looks like one: judo's [d͡ʒʊdɔ] CHANGES a phoneme
    # against the reading [jʊdɔ] rather than reordering it.
    if any(_is_transposition(written, ipa) for ipa in usable):
        return Verdict.DROP_TRANSPOSED_IPA, None, []

    spellings: list[str] = []
    for ipa in usable:
        try:
            candidate = restore_final_voicing(written, ipa_to_czech(ipa))
        except UnknownSymbol:
            continue
        if not candidate:
            continue
        candidate = anchor_to_written(written, candidate, ipa)
        if not reads_as(candidate, ipa):
            continue
        spellings.append(candidate)
    if not spellings:
        return (
            Verdict.DROP_UNKNOWN_SYMBOL
            if any(_has_unknown(ipa) for ipa in usable)
            else Verdict.DROP_ROUND_TRIP
        ), None, []

    # Variants differing only in vowel length are the same decision; the first
    # documented one wins. Structurally different variants (puzzle [pazl] vs
    # [pʊt͡slɛ]) are a real disagreement no algorithm should settle by ear.
    distinct = {_fold_length(spelling) for spelling in spellings}
    if len(distinct) > 1:
        return Verdict.REVIEW_CONFLICTING, None, sorted(set(spellings))
    spelling = spellings[0]
    # A respelling may never LOSE a háček sibilant. Czech reads š/ž/č/ř as
    # [ʃ]/[ʒ]/[t͡ʃ]/[r̝] with no exception but voicing — there is no reading of
    # "š" as [s] — so a transcription that claims otherwise is a typo, and the
    # dump is full of them: příští is typed [pr̝̊iːsciː] (s for š) and kořist
    # [ˈkɔrɪst] (plain r for ř, which needs two combining marks). Every other
    # filter waves these through: the similarity is ~0.9 and the length is
    # unchanged. Unlike a devoicing quarrel this has no defensible reading —
    # the phoneme is simply gone.
    #
    # Only a DROP is suspicious. A loanword may well gain one (judo -> "džudo"),
    # and the háčeks the di/ti/ni repair adds (ď/ť/ň) are the whole point.
    if _loses_hacek(written, spelling):
        return Verdict.REVIEW_LOST_HACEK, spelling, sorted(set(spellings))
    if _spurious_phoneme_swap(written, spelling):
        return Verdict.REVIEW_SPURIOUS_PHONEME, spelling, sorted(set(spellings))
    if _spurious_softening(written, spelling):
        return Verdict.REVIEW_SPURIOUS_SOFTENING, spelling, sorted(set(spellings))
    if similarity(written, spelling) < REVIEW_SIMILARITY:
        return Verdict.REVIEW_DISSIMILAR, spelling, sorted(set(spellings))
    return Verdict.IN_MAP, spelling, sorted(set(spellings))


_HACEK_SIBILANTS = "šžčř"


def _loses_hacek(written: str, spelling: str) -> bool:
    """True when the respelling drops a š/ž/č/ř the written form has."""
    source = written.casefold()
    return any(
        spelling.count(letter) < source.count(letter) for letter in _HACEK_SIBILANTS
    )


# Single-character (written -> spelling) substitutions the dump's IPA produces
# that Czech orthography NEVER treats as sound-equivalent — a plain letter turned
# into an unrelated phoneme. These are crowd-sourced Wiktionary transcription
# errors, usually the IPA of a NEIGHBOURING word: "pradlena" (washerwoman) carries
# the IPA of "přadlena" (spinner), so it respells r->ř; "mocná" gains ť; "dopamin"
# turns p->m. They slip past every other guard because the string barely
# changes — similarity ~0.9, length unchanged, and _loses_hacek only fires on the
# opposite (drop) direction, since GAINING a háček is legitimate for real
# loanwords (judo -> "džudo"). The difference: a real loan gain is an INSERTION
# (judo->džudo adds a letter); these are same-length substitutions.
#
# Only substitutions with NO legitimate member belong here. c->č is deliberately
# excluded: it is genuinely ambiguous (cembalo -> "čembalo" is CORRECT Italian
# [tʃ], while akcelerometr -> "akčelerometr" is wrong [ts]) and cannot be settled
# by rule — those need ears, so the ambiguous garbles are dropped by an explicit
# per-word list in the builder instead.
_SPURIOUS_SUBSTITUTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("r", "ř"),  # pradlena -> přadlena
        ("s", "š"),  # soustavná -> šoustavná
        ("z", "ž"),  # závlačku -> žávlačku
        ("c", "ť"),  # mocná -> moťná, cink -> ťink
        ("s", "c"),  # představitel -> předctavitel
        ("p", "m"),  # dopamin -> domamin
        ("g", "ž"),  # girarďák -> žirarďák
        ("t", "r"),  # parašutisté -> parašuristé
        ("t", "c"),  # jistí -> jiscí
        ("y", "o"),  # kohyponym -> kohoponym
        ("i", "á"),  # ohijan -> ohájan
    }
)


def _spurious_phoneme_swap(written: str, spelling: str) -> bool:
    """True when the respelling swaps exactly one letter for an unrelated phoneme.

    Guards against Wiktionary IPA that carries a neighbouring word's pronunciation
    (see `_SPURIOUS_SUBSTITUTIONS`). Only equal-length, single-position
    substitutions in that set count; the legitimate di/ti/ni softenings (t->ť,
    d->ď, n->ň) and the sound-equal i/y, í/ý pairs are absent from the set and so
    always pass.
    """
    source = written.casefold()
    if len(source) != len(spelling):
        return False
    diffs = [(a, b) for a, b in zip(source, spelling) if a != b]
    return len(diffs) == 1 and diffs[0] in _SPURIOUS_SUBSTITUTIONS


# A hard d/t/n and the soft ď/ť/ň the respelling may turn it into.
_HARD_TO_SOFT = {"d": "ď", "t": "ť", "n": "ň"}
# Contexts that license the softening: a soft vowel WRITTEN after the consonant
# (the di/ti/ni trigger — "nivu" -> "ňivu"), or a soft consonant the RESPELLING
# puts after it (regressive palatal assimilation — "kundička" -> "kuňďička",
# "Rwanďan" -> "rvaňďan", where n takes ň before ď/ť/ň).
_SOFT_VOWELS = frozenset("iíě")
_SOFT_CONSONANTS = frozenset("ďťň")


def _spurious_softening(written: str, spelling: str) -> bool:
    """True when the respelling softens a hard d/t/n with nothing to license it.

    ď/ť/ň only belong before a soft vowel (i/í/ě) or a soft consonant. When the
    dump's IPA carries a neighbouring word's [ɲ]/[c]/[ɟ], the transliteration
    plants ňo/ťy/ďa where Czech has a plain n/t/d — "heřmanova" -> "heřmaňova",
    "moučná" -> "moučňá", "svícen" -> "svíceň", "plonková" -> "ploňková". Every
    other guard waves these through: the length is unchanged and the similarity
    is ~0.9. The legitimate softenings (ni -> ňi, and the ňď/ňť assimilations)
    are licensed by the context test and pass.
    """
    source = written.casefold()
    if len(source) != len(spelling):
        return False
    for i, (a, b) in enumerate(zip(source, spelling)):
        if _HARD_TO_SOFT.get(a) != b:
            continue
        written_next = source[i + 1] if i + 1 < len(source) else ""
        spelling_next = spelling[i + 1] if i + 1 < len(spelling) else ""
        if written_next not in _SOFT_VOWELS and spelling_next not in _SOFT_CONSONANTS:
            return True
    return False


def _is_transposition(written: str, ipa: str) -> bool:
    """True when the IPA is the written form's reading with phonemes reordered."""
    reading = model_g2p(written)
    if reading is None or AMBIGUOUS in reading:
        # Unreadable (foreign letters) or an unresolved di/ti/ni site: the
        # reading is not a reliable thing to compare against.
        return False
    source = fold_phonemes(clean_ipa(ipa))
    reading = fold_phonemes(reading)
    if reading == source:
        return False
    return sorted(_phonemes(reading)) == sorted(_phonemes(source))


def _has_unknown(ipa: str) -> bool:
    try:
        ipa_to_czech(ipa)
    except UnknownSymbol:
        return True
    return False


_LENGTH_FOLD = str.maketrans({"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ý": "y"})


def _fold_length(word: str) -> str:
    return word.casefold().translate(_LENGTH_FOLD)
