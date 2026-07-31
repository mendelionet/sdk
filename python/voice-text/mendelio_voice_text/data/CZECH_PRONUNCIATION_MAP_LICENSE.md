# Czech pronunciation map — licence and attribution

`czech_ipa_transliteration_map.json` is adapted from Czech Wiktionary entries
extracted by [Wiktextract](https://github.com/tatuylonen/wiktextract) and
distributed by [Kaikki](https://kaikki.org/cswiktionary/rawdata.html).

Attribution: **Czech Wiktionary contributors**. Each map key corresponds to the
Wiktionary entry or an inflected form listed by that entry. The entry and its
contributors can be inspected at
`https://cs.wiktionary.org/wiki/<word>` and
`https://cs.wiktionary.org/w/index.php?title=<word>&action=history`.
The generated file records the dated Wikimedia dump, Kaikki extraction date,
Wiktextract and Wikitextprocessor revisions, source URL, and source SHA-256.

Wiktionary contributors provide the source material under the
[Creative Commons Attribution-ShareAlike 4.0 International licence](https://creativecommons.org/licenses/by-sa/4.0/)
and the GNU Free Documentation License. This generated map is distributed under
**CC BY-SA 4.0** (`SPDX-License-Identifier: CC-BY-SA-4.0`). Commercial use is
allowed under that licence, subject to attribution and share-alike obligations.

Changes made by Eden AI: definitions, translations, examples and audio links are
discarded; Czech orthographic `di/ti/ni` sites are aligned with IPA pronunciations;
the result contains only a deterministic mapping from written word forms to
OmniVoice-oriented pronunciation spellings. Ambiguous alignments are excluded.

The generator is `scripts/build_czech_pronunciation_map.py`. It records the
source URL and SHA-256 checksum in every generated map. The generator itself is
project code and is not part of the CC BY-SA dataset.
