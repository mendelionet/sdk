# Mendelio Voice Text data builders

Regenerate the committed Czech pronunciation map from the current Czech
Wiktionary Wiktextract snapshot:

```bash
cd python/voice-text
python3 tools/build_czech_pronunciation_map.py
```

The command downloads source data to a temporary directory, writes the compact
runtime map to `mendelio_voice_text/data/czech_ipa_transliteration_map.json`, and records
the source URL and SHA-256 checksum in that file. Raw dictionary data must not be
committed. Licence and attribution details are in
`mendelio_voice_text/data/CZECH_PRONUNCIATION_MAP_LICENSE.md`.

For a pinned local snapshot, pass `--input path/to/extract.jsonl.gz` together
with `--extraction-date`, `--wiktionary-dump-date`, `--wiktextract-commit`, and
`--wikitextprocessor-commit`. The output is deterministic for identical input
bytes and metadata. The per-language extract
(`kaikki.org/cswiktionary/čeština/…jsonl`, ~150 MB) is accepted too and yields a
byte-identical result — it carries the same records, just without the other
languages.

## One map, two steps

Respellings come from each word's documented IPA. The build gets there in two
passes over the same dump:

1. every documented di/ti/ni site is resolved (`kupodivu` → `kupoďivu`). This
   runs per FORM, so it reaches stem-changing forms whose lemma carries no IPA;
2. each word is transliterated from its own IPA and **overrides** step 1 wherever
   it has better evidence, adding the foreign spelling step 1 never could
   (`notebook` → `noutbuk`).

Step 1 is internal — it lands in `build-reports/` as an intermediate, and only
the map from step 2 ships. It used to be a second runtime map behind
`OMNIVOICE_RESPELL_MODE`; that switch was removed on 2026-07-17 when IPA became
the only path. Design and rationale:
`docs/plans/tts-foreign-ipa-transliteration-2026-07-17.md`.

Two build reports land in `build-reports/` (gitignored, regenerable):

- `…_diff.json` — every respelling that differs from step 1 alone, i.e. what
  the IPA pass changes. Pass `--diff-baseline <a previously shipped map>` to
  answer the other question instead: what changes for production.
- `…_review.json` — words deliberately left out of the map: conflicting IPA
  variants (`puzzle` [pazl] × [pʊt͡slɛ]) and respellings that stray far from the
  written form. Wiktionary's IPA is crowd-sourced and does contain another
  word's pronunciation; these need ears, not a rule.

Never hand-edit either generated map — a rebuild silently undoes it. Ear-verified
fixes belong in the package model adapter. Words that must keep an English
reading go to `CORPUS_EXCLUSIONS` in the builder — find candidates with
`tools/find_english_reading_candidates.py`.

To audition the diff before shipping (OmniVoice only ever runs on the box —
never locally):

```bash
python3 tools/build_lab_group_from_diff.py     # groups the diff by change type
ssh -f -N -L 18080:127.0.0.1:18080 <ssh-host>
python3 ../podcast-renderer/scripts/tts_pronunciation_lab.py
```
