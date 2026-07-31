#!/usr/bin/env python3
"""Find corpus entries that may need to KEEP an English reading.

Step 1 of the build hardens di/ti/ni blindly from Wiktionary: every word tagged
lang_code=cs gets it hardened to the documented Czech pronunciation. For a
naturalized loanword that is correct (puding -> pudyng, lingvistika ->
lingvistyka). It is WRONG for the small class of words Czech speakers read with
English phonology — "meetyng" stops the model recognizing the English word.

Step 2 usually rescues that class: a word with its own IPA gets transliterated
from it instead ("mítyng"). The risk is what step 2 CANNOT decide and step 1
therefore still owns — which is how "meeting" survives as damage, filed in the
dump as a spelling variant of the lemma "mítink".

A plain English-dictionary cross-match cannot find the class: it flags ~480
Latinate internationalisms (audit, tenis, festival, diplomat...) whose Czech
hard reading is correct — excluding those would reintroduce the very bug the
corpus fixes. What distinguishes the English-read class is SPELLING the model
resolves through English: grapheme clusters Czech orthography does not produce
(ee, w, q) and English -ing morphology.

This script prints candidate lemma groups for a listening pass in the
pronunciation lab (services/podcast-renderer/scripts/tts_pronunciation_lab.py).
Confirmed words go to CORPUS_EXCLUSIONS in build_czech_pronunciation_map.py —
never hand-edit the generated corpus JSON, a rebuild would silently undo it.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

CORPUS = (
    Path(__file__).resolve().parents[1]
    / "mendelio_voice_text/data/czech_ipa_transliteration_map.json"
)

# Native patterns that superficially look English and must not be flagged:
# prefix boundaries (roz+z, s+h: rozzuřit, shodit, přeshraniční), vowel hiatus
# (ne+etický, ko+ordinace, jiho+osetinský), and native tchyně. The detectors
# below are chosen so those never match; extend the negative lookaheads if a
# future corpus snapshot surfaces a new native false positive.
_ENGLISH_ING = re.compile(r"(?:t|n|d|k|m|r|p|s|l|g|sh|ch)ing", re.IGNORECASE)


def candidate_reasons(word: str) -> list[str]:
    reasons = []
    if "ee" in word and not word.startswith("nee"):  # ne+etický
        reasons.append("ee")
    if "w" in word:
        reasons.append("w")
    if "q" in word:
        reasons.append("q")
    if _ENGLISH_ING.search(word):
        reasons.append("-ing")
    return reasons


def main() -> None:
    entries: dict[str, str] = json.loads(CORPUS.read_text(encoding="utf-8"))["entries"]
    groups: dict[str, list[tuple[str, str, list[str]]]] = defaultdict(list)
    for written, spoken in sorted(entries.items()):
        reasons = candidate_reasons(written.lower())
        if reasons:
            groups[written.lower()[:7]].append((written, spoken, reasons))
    print(f"{sum(len(v) for v in groups.values())} candidate forms in {len(groups)} groups\n")
    for key in sorted(groups):
        written, spoken, reasons = groups[key][0]
        extra = len(groups[key]) - 1
        print(f"{written!r:35} -> {spoken!r:35} {','.join(reasons):10} (+{extra} forms)")


if __name__ == "__main__":
    main()
