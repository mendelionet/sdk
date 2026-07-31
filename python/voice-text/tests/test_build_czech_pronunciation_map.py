from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools/build_czech_pronunciation_map.py"


def build(source: Path, out_dir: Path) -> dict[str, Path]:
    """Run the builder with every output redirected into a temp dir.

    Passing all four paths matters: the defaults point at the repo's real map
    and build reports, so a test that omits them overwrites shipped data.
    """
    paths = {
        "output": out_dir / "map.json",
        "ipa-output": out_dir / "ipa.json",
        "review-output": out_dir / "review.json",
        "diff-output": out_dir / "diff.json",
    }
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input", str(source),
            *[arg for flag, path in paths.items() for arg in (f"--{flag}", str(path))],
            "--extraction-date", "2026-01-02",
            "--wiktionary-dump-date", "2026-01-01",
            "--wiktextract-commit", "fixture-wiktextract",
            "--wikitextprocessor-commit", "fixture-wtp",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return paths


def test_builds_runtime_map_from_wiktextract_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "czech.jsonl.gz"
    entries = [
        {
            "word": "kupodivu",
            "lang_code": "cs",
            "sounds": [{"ipa": "[kupɔɟɪvu]"}],
        },
        {
            "word": "diktovat",
            "lang_code": "cs",
            "sounds": [{"ipa": "[dɪktɔvat]"}],
            "forms": [{"form": "diktoval"}, {"form": "diktoval si"}],
            "related": [
                {"word": "nadiktovat"},
                {"word": "pseudodiktovat"},
            ],
        },
    ]
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    output = tmp_path / "map.json"
    build(source, tmp_path)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["license"] == "CC-BY-SA-4.0"
    assert payload["source_metadata"]["wiktionary_dump_date"] == "2026-01-01"
    assert payload["entries"] == {
        "diktoval": "dyktoval",
        "diktovat": "dyktovat",
        "kupodivu": "kupoďivu",
        "nadiktoval": "nadyktoval",
        "nadiktovat": "nadyktovat",
    }


def write_dump(path: Path, entries: list[dict]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def test_the_shipped_map_keeps_every_di_ti_ni_repair_step_one_makes(tmp_path: Path) -> None:
    # Step 2 OVERRIDES step 1 rather than layering on it, so anything step 1
    # repairs has to survive into the shipped map or the fix is silently lost.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "kupodivu", "lang_code": "cs", "sounds": [{"ipa": "[kupɔɟɪvu]"}]},
            {
                "word": "diktovat",
                "lang_code": "cs",
                "sounds": [{"ipa": "[dɪktɔvat]"}],
                "forms": [{"form": "diktoval"}],
                "related": [{"word": "nadiktovat"}],
            },
        ],
    )
    paths = build(source, tmp_path)

    di_ti_ni = json.loads(paths["output"].read_text(encoding="utf-8"))["entries"]
    shipped = json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    assert shipped == di_ti_ni
    assert shipped["nadiktoval"] == "nadyktoval"  # prefix propagation (plan 4e)


def test_the_shipped_map_respells_foreign_spelling_step_one_cannot(tmp_path: Path) -> None:
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "judo", "lang_code": "cs", "sounds": [{"ipa": "[d͡ʒʊdɔ]"}]},
            {"word": "notebook", "lang_code": "cs", "sounds": [{"ipa": "[ˈnɔʊ̯t.buk]"}]},
            {
                "word": "screeningový",
                "lang_code": "cs",
                "sounds": [{"ipa": "[skriːnɪŋgɔviː]"}],
                "forms": [{"form": "screeningová"}],
            },
        ],
    )
    paths = build(source, tmp_path)

    ipa = json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    assert ipa["judo"] == "džudo"
    assert ipa["notebook"] == "noutbuk"
    assert ipa["screeningový"] == "skrínyngový"
    # 4e: the form has no IPA of its own and grafts the lemma's stem.
    assert ipa["screeningová"] == "skrínyngová"


def test_conflicting_ipa_variants_go_to_review_never_to_the_map(tmp_path: Path) -> None:
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {
                "word": "puzzle",
                "lang_code": "cs",
                "sounds": [{"ipa": "[pazl]"}, {"ipa": "[pʊt͡slɛ]"}],
            },
        ],
    )
    paths = build(source, tmp_path)

    assert "puzzle" not in json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    review = json.loads(paths["review-output"].read_text(encoding="utf-8"))["review"]
    assert [item["word"] for item in review] == ["puzzle"]
    assert review[0]["reason"] == "review_conflicting_variants"
    assert review[0]["transliterations"] == ["pazl", "pucle"]


def test_wiktionary_noise_never_reaches_the_map(tmp_path: Path) -> None:
    # Real rows from the 2026-07-17 dump: an entry carrying another word's IPA,
    # a phrase's IPA, and a truncated stub that transliterates to "".
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "šestnáctipodlažní", "lang_code": "cs", "sounds": [{"ipa": "[dvɔʊ̯pɔdlaʒɲiː]"}]},
            {"word": "Moravcovi", "lang_code": "cs", "sounds": [{"ipa": "[panʊ]"}]},
            {"word": "břidlicový", "lang_code": "cs", "sounds": [{"ipa": "[]"}]},
        ],
    )
    paths = build(source, tmp_path)

    assert json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"] == {}


def test_build_is_deterministic_over_the_same_dump(tmp_path: Path) -> None:
    entries = [
        {"word": "kupodivu", "lang_code": "cs", "sounds": [{"ipa": "[kupɔɟɪvu]"}]},
        {"word": "judo", "lang_code": "cs", "sounds": [{"ipa": "[d͡ʒʊdɔ]"}]},
        {"word": "puzzle", "lang_code": "cs", "sounds": [{"ipa": "[pazl]"}, {"ipa": "[pʊt͡slɛ]"}]},
    ]
    source = write_dump(tmp_path / "czech.jsonl.gz", entries)
    first = {name: path.read_bytes() for name, path in build(source, tmp_path / "a").items()}
    second = {name: path.read_bytes() for name, path in build(source, tmp_path / "b").items()}
    assert first == second


def test_final_ch_survives_the_anti_devoicing_rule(tmp_path: Path) -> None:
    # 4a re-voices a final devoiced consonant when the spelling stays voiced
    # (meeting [miːtɪŋk] -> "mítyng"). "ch" ends in "h", so a naive suffix test
    # re-voices every locative plural: abdikacích -> "abdykacíh".
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "abdikacích", "lang_code": "cs", "sounds": [{"ipa": "[abdɪkat͡siːx]"}]},
            {"word": "sníh", "lang_code": "cs", "sounds": [{"ipa": "[sɲiːx]"}]},
        ],
    )
    entries = json.loads(build(source, tmp_path)["ipa-output"].read_text(encoding="utf-8"))["entries"]

    assert entries["abdikacích"] == "abdykacích"
    assert entries["sníh"] == "sňíh"  # a BARE final h is [x]'s voiced counterpart


def test_the_shipped_map_keeps_coverage_step_two_cannot_derive(tmp_path: Path) -> None:
    # Step 1 resolves di/ti/ni per FORM, so it reaches a stem-changing form whose
    # lemma carries no IPA of its own. Suffix grafting (4e) skips those, so the
    # entry must be inherited rather than lost: a word step 1 repairs and step 2
    # drops is a silent regression.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {
                "word": "agonie",
                "lang_code": "cs",
                "sounds": [{"ipa": "[agɔnɪjɛ]"}],
                "forms": [{"form": "agónie"}],
            },
        ],
    )
    paths = build(source, tmp_path)

    di_ti_ni = json.loads(paths["output"].read_text(encoding="utf-8"))["entries"]
    shipped = json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    assert di_ti_ni["agónie"] == "agónye"
    assert set(di_ti_ni) <= set(shipped)
    assert shipped["agónie"] == "agónye"


def test_dropped_words_fall_back_to_their_di_ti_ni_entry(tmp_path: Path) -> None:
    # A word step 2 refuses to transliterate must fall back to step 1's
    # ear-tested respelling, not lose its entry. "w" is outside the phoneme
    # table, so the whole word drops (never a silent mistransliteration) — but
    # step 1's di/ti/ni alignment handles it fine.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [{"word": "wikipedie", "lang_code": "cs", "sounds": [{"ipa": "[wɪkɪpɛdɪjɛ]"}]}],
    )
    paths = build(source, tmp_path)

    di_ti_ni = json.loads(paths["output"].read_text(encoding="utf-8"))["entries"]
    shipped = json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    assert di_ti_ni["wikipedie"] == "wikipedye"
    assert shipped["wikipedie"] == "wikipedye"


def test_inherited_entries_respect_the_english_reading_exclusions(tmp_path: Path) -> None:
    # Exactly how the live dump carries it: the lemma is "mítink", and "meeting"
    # rides along as a spelling variant in forms[]. Step 1 transfers the lemma's
    # di/ti/ni decision onto the form and produces "meetyng"; grafting refuses,
    # because the respelled stem no longer contains the form's. So "meeting" can
    # only ever be INHERITED — and nothing downstream will catch it, so an
    # unfiltered inherit hands the model "meetyng" with nothing left to stop it.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {
                "word": "mítink",
                "lang_code": "cs",
                "sounds": [{"ipa": "[miːtɪŋk]"}],
                "forms": [{"form": "meeting"}],
            },
        ],
    )
    paths = build(source, tmp_path)

    di_ti_ni = json.loads(paths["output"].read_text(encoding="utf-8"))["entries"]
    shipped = json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    assert di_ti_ni["meeting"] == "meetyng"  # step 1 is where the damage is made
    assert "meeting" not in shipped
    assert shipped["mítink"] == "mítynk"  # the lemma itself is still repaired


def test_a_form_whose_ipa_contradicts_its_lemma_goes_to_review(tmp_path: Path) -> None:
    # Wiktionary transcribes lemma and form as separate entries, so a typo can
    # hit one and not the other: "šlehačka" is right, the form "šlehačku" carries
    # a doubled a and respelled to "šlehaačku". The paradigm is the cross-check
    # the single entry lacks.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "šlehačka", "lang_code": "cs", "sounds": [{"ipa": "[ʃlɛɦat͡ʃka]"}],
             "forms": [{"form": "šlehačku"}]},
            {"word": "šlehačku", "lang_code": "cs", "sounds": [{"ipa": "[ʃlɛɦaat͡ʃkʊ]"}]},
        ],
    )
    paths = build(source, tmp_path)

    assert "šlehačku" not in json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    review = json.loads(paths["review-output"].read_text(encoding="utf-8"))["review"]
    assert [(r["word"], r["reason"]) for r in review] == [
        ("šlehačku", "review_paradigm_conflict")
    ]


def test_a_form_may_still_open_a_di_ti_ni_site_its_lemma_lacks(tmp_path: Path) -> None:
    # The cross-check must not swallow the corpus's day job: an ending
    # legitimately opens a site the lemma has not got.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "hrad", "lang_code": "cs", "sounds": [{"ipa": "[ɦrat]"}],
             "forms": [{"form": "hradní"}]},
            {"word": "hradní", "lang_code": "cs", "sounds": [{"ipa": "[ɦradɲiː]"}]},
        ],
    )
    entries = json.loads(build(source, tmp_path)["ipa-output"].read_text(encoding="utf-8"))["entries"]

    assert entries["hradní"] == "hradňí"


def test_a_spelling_variant_is_not_vouched_for_by_its_lemma(tmp_path: Path) -> None:
    # forms[] carries spelling variants as well as inflections: "judo" is filed
    # under the lemma "džudo", which of course reads correctly. Letting the lemma
    # vouch for it concludes "so judo reads correctly too" and throws away the
    # very entry this layer exists to make. Same shape as meeting under mítink.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "džudo", "lang_code": "cs", "sounds": [{"ipa": "[d͡ʒʊdɔ]"}],
             "forms": [{"form": "judo"}]},
            {"word": "judo", "lang_code": "cs", "sounds": [{"ipa": "[d͡ʒʊdɔ]"}]},
        ],
    )
    entries = json.loads(build(source, tmp_path)["ipa-output"].read_text(encoding="utf-8"))["entries"]

    assert entries["judo"] == "džudo"


def test_a_respelling_may_not_invent_a_letter_pair_czech_never_writes(tmp_path: Path) -> None:
    # The dump types "googlit" as [ˈguːglɪt] and it respells to "gúglit". Czech
    # writes no "úg" in any of ~850k forms, so whatever the IPA claims, the
    # spelling fails on the layer's own terms: the model has never seen that pair
    # and cannot read it. The authority is the dump's own written forms, not a
    # rule I made up — which is also why it does NOT fire on "tčtyřka": Czech
    # really does write "tč" (matčin, otčím), so that one stays a job for ears.
    # Enough samples to clear MIN_ORTHOGRAPHY_CORPUS, letters only: RUNTIME_WORD
    # rejects digits, so "slovo1" would not count and the gate would quietly
    # switch itself off — which is how this test first passed for the wrong
    # reason.
    letters = "abcdefghijklmnoprstuvyz"
    padding = [
        {"word": f"slov{a}{b}{c}", "lang_code": "cs", "forms": [{"form": f"slov{a}{b}{c}a"}]}
        for a in letters
        for b in letters
        for c in letters
    ][:3_000]
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "googlit", "lang_code": "cs", "sounds": [{"ipa": "[ˈguːglɪt]"}]},
            # A real loanword respelling uses ordinary Czech pairs and must live.
            {"word": "judo", "lang_code": "cs", "sounds": [{"ipa": "[d͡ʒʊdɔ]"}]},
            # Real words, because the corpus has to have SEEN every pair "džudo"
            # needs (dž, žu, ud, do) before it can vouch for it. Synthetic
            # padding alone teaches the detector a Czech that does not exist.
            *(
                {"word": word, "lang_code": "cs"}
                for word in ("džbán", "žula", "budu", "doma", "kilo")
            ),
            *padding,
        ],
    )
    paths = build(source, tmp_path)

    entries = json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    review = json.loads(paths["review-output"].read_text(encoding="utf-8"))["review"]
    assert "googlit" not in entries
    assert entries["judo"] == "džudo"
    flagged = {r["word"]: r for r in review}
    assert flagged["googlit"]["reason"] == "review_unwritable"
    assert "úg" in flagged["googlit"]["unwritable_bigrams"]


def test_the_orthography_gate_disables_itself_on_a_tiny_corpus(tmp_path: Path) -> None:
    # An anomaly detector trained on three words calls everything an anomaly.
    # Silently emptying the map is worse than shipping the odd stray bigram.
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [{"word": "judo", "lang_code": "cs", "sounds": [{"ipa": "[d͡ʒʊdɔ]"}]}],
    )
    entries = json.loads(build(source, tmp_path)["ipa-output"].read_text(encoding="utf-8"))["entries"]

    assert entries["judo"] == "džudo"


def test_the_orthography_gate_only_blames_what_step_two_invented(tmp_path: Path) -> None:
    # "odiózní" -> "odyózňí" is step 1's ordinary di/ti/ni repair; its "yó" is
    # unwritten in Czech only because ó is rare. Step 2 proposes the identical
    # string, so it invented nothing and the word ships unchanged either way —
    # flagging it just puts noise in a queue whose value is that every row matters.
    letters = "abcdefghijklmnoprstuvyz"
    padding = [
        {"word": f"slov{a}{b}{c}", "lang_code": "cs", "forms": [{"form": f"slov{a}{b}{c}a"}]}
        for a in letters for b in letters for c in letters
    ][:3_000]
    source = write_dump(
        tmp_path / "czech.jsonl.gz",
        [
            {"word": "odiózní", "lang_code": "cs", "sounds": [{"ipa": "[ˈʔɔdɪjoːzɲiː]"}]},
            *padding,
        ],
    )
    paths = build(source, tmp_path)

    entries = json.loads(paths["ipa-output"].read_text(encoding="utf-8"))["entries"]
    review = json.loads(paths["review-output"].read_text(encoding="utf-8"))["review"]
    assert entries["odiózní"] == "odyózňí"
    assert [r["word"] for r in review if r["reason"] == "review_unwritable"] == []
