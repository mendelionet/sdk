#!/usr/bin/env python3
"""Turn the build reports into pronunciation-lab groups for an ear audit.

The map changes ~6k respellings against what production says today. Nobody
can audit that word by word, and hand-editing the lab's variants JSON is how
mistakes get in (plan 8.2 asks for a script for exactly this reason).

So group the diff by WHAT KIND of change it is and audition each class, not each
word. Class size is the signal worth listening for: a change that shows up 1000+
times is systematic and almost certainly a real Czech irregularity
(absentismus -> "absentyzmus", the -ismus suffix really is [ɪzmʊs]); a class with
a handful of members is usually Wiktionary noise. The dump really claims
"příští" is [pr̝̊iːsciː] (s for š) and "březník" is [pr̝ɛzɲiːk] (p for b), and no
rule separates those from the real irregularities — only ears do. The rare tail
is therefore emitted in FULL, while the big systematic classes get samples.

    python3 tools/build_lab_group_from_diff.py            # writes the lab JSON
    python3 tools/build_lab_group_from_diff.py --dry-run  # just print the plan

Then run the lab (needs the prod tunnel; OmniVoice never runs locally):
    ssh -f -N -L 18080:127.0.0.1:18080 <ssh-host>
    python3 services/podcast-renderer/scripts/tts_pronunciation_lab.py
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
DIFF = SERVICE_ROOT / "build-reports/czech_ipa_transliteration_diff.json"
REVIEW = SERVICE_ROOT / "build-reports/czech_ipa_transliteration_review.json"
LAB_VARIANTS = REPO_ROOT / "services/podcast-renderer/scripts/tts_pronunciation_variants.json"

# Below this many members a class is a tail class: emitted in full, because this
# is where the dump's typos hide.
RARE_CLASS = 15
SAMPLES_PER_CLASS = 4


def classify(written: str, baseline: str, ipa: str) -> str:
    if "j" not in baseline and baseline.replace("j", "") == ipa.replace("j", ""):
        return "hiátové j"
    if "x" in written and "ks" in ipa:
        return "x → ks"
    if len(baseline) == len(ipa):
        changed = {(a, b) for a, b in zip(baseline, ipa) if a != b}
        if len(changed) == 1:
            (a, b), = changed
            if {a, b} <= set("iyíý"):
                return "i/y záměna"
            if {a, b} <= set("aáeéoóuú"):
                return "délka samohlásky"
            return f"jedno písmeno {a} → {b}"
    return "strukturální"


def sentence(word: str) -> str:
    # One word per clip: the lab compares spellings, and a carrier sentence would
    # only add its own pronunciation problems to the judgement.
    return f"{word.capitalize()}."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    diff = json.loads(DIFF.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))["review"]

    classes: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for word, change in diff["changed"].items():
        classes[classify(word, change["baseline"], change["ipa"])].append(
            (word, change["baseline"], change["ipa"])
        )
    # The ADDED bucket is where the foreign class lives (judo -> "džudo"), i.e.
    # the whole point of the layer AND its largest behavioural change: today
    # these words are said as written, and the map respells them. Auditing only
    # "changed" left every one unheard. Here the baseline IS the written form.
    for word, spelling in diff.get("added", {}).items():
        classes[f"NOVĚ přepsané: {classify(word, word, spelling)}"].append(
            (word, word, spelling)
        )

    groups = []
    for name, members in sorted(classes.items(), key=lambda item: -len(item[1])):
        rare = len(members) <= RARE_CLASS
        shown = members if rare else members[:SAMPLES_PER_CLASS]
        groups.append(
            {
                "word": f"[diff] {name} ({len(members)}×)",
                "issue": (
                    (
                        f"VZÁCNÁ TŘÍDA — kandidát na šum Wiktionary, posloucháme všech {len(members)}"
                        if rare
                        else f"systematická třída, vzorek {len(shown)} z {len(members)}"
                    )
                    + "; vlevo co říká produkce dnes, vpravo nová ipa mapa"
                ),
                "variants": [
                    variant
                    for word, baseline, ipa in shown
                    for variant in (
                        {"label": f"{word} → {baseline} (dnes)", "text": sentence(baseline)},
                        {"label": f"{word} → {ipa} (ipa, nově)", "text": sentence(ipa)},
                    )
                ],
            }
        )

    # The review queue never reaches the map; ears decide whether it should.
    for item in review[:20]:
        groups.append(
            {
                "word": f"[review] {item['word']} ({item['reason']})",
                "issue": f"mimo mapu, IPA {' × '.join(item['ipa'])}; psaná forma vs. kandidáti",
                "variants": [
                    {"label": f"{item['word']} (psaná forma, dnes)", "text": sentence(item["word"])},
                    *(
                        {"label": f"{candidate} (kandidát)", "text": sentence(candidate)}
                        for candidate in item["transliterations"]
                    ),
                ],
            }
        )

    config = json.loads(LAB_VARIANTS.read_text(encoding="utf-8"))
    kept = [g for g in config["groups"] if not g["word"].startswith(("[diff]", "[review]"))]
    config["groups"] = kept + groups

    print(f"{len(groups)} groups ({len(classes)} diff classes + {len(review[:20])} review)")
    for group in groups[:30]:
        print(f"   {group['word']}")
    if args.dry_run:
        return
    LAB_VARIANTS.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {LAB_VARIANTS.relative_to(REPO_ROOT)} (kept {len(kept)} existing groups)")


if __name__ == "__main__":
    main()
