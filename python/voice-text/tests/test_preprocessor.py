from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pytest

from mendelio_voice_text import (
    AdapterCapabilities,
    LanguageTag,
    LiveCapabilityError,
    ModelDocument,
    SpeechPreprocessor,
    SourceDocument,
    SpokenDocument,
    SynthesisConstraints,
    TargetId,
    UnsupportedLocaleError,
    VerbatimModelAdapter,
)

_BEHAVIOR_CORPUS = Path(__file__).with_name("data") / "behavior-corpus-v0.1.json"


def _corpus_preprocessor(case: dict[str, object]) -> SpeechPreprocessor:
    kwargs = {
        "max_chars": int(case["max_chars"]),
        "live": bool(case["live"]),
    }
    if case["profile"] == "cs-generic":
        return SpeechPreprocessor.czech_generic(**kwargs)
    if case["profile"] == "cs-omnivoice":
        return SpeechPreprocessor.czech_omnivoice(**kwargs)
    return SpeechPreprocessor.verbatim(
        str(case["locale"]),
        target="omnivoice",
        **kwargs,
    )


def test_machine_readable_behavior_corpus() -> None:
    corpus = json.loads(_BEHAVIOR_CORPUS.read_text(encoding="utf-8"))
    assert corpus["package_version"] == "0.1.0"
    for case in corpus["cases"]:
        prepared = _corpus_preprocessor(case).prepare(str(case["input"]))
        assert prepared.display_text == case["display_text"], case["id"]
        assert prepared.spoken_text == case["spoken_text"], case["id"]
        assert prepared.model_text == case["model_text"], case["id"]
        assert all(
            len(chunk.model_text) <= int(case["max_chars"])
            for chunk in prepared.chunks
        ), case["id"]


def test_czech_profile_keeps_three_text_representations_distinct() -> None:
    prepared = SpeechPreprocessor.czech_omnivoice(max_chars=300).prepare(
        "Kupodivu stálo 5 km cesty 10 Kč."
    )

    assert prepared.display_text == "Kupodivu stálo 5 km cesty 10 Kč."
    assert "pět kilometrů" in prepared.spoken_text
    assert "Kupoďivu" in prepared.model_text
    assert prepared.data_id and prepared.data_id.startswith("sha256:")
    assert prepared.chunks[0].spoken_text != prepared.chunks[0].model_text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "Rok 1921, číslo 21.",
            "Rok devatenáct set dvacetjedna, číslo dvacetjedna.",
        ),
        ("1 %", "jedno procento"),
        ("2 %", "dvě procenta"),
        ("5 %", "pět procent"),
        ("Ve 13. a 14. století", "Ve třináctém a čtrnáctém století"),
        ("V XIX. století", "V devatenáctém století"),
        (
            "Filosofie XIX. a XX. století",
            "Filosofie devatenáctého a dvacátého století",
        ),
    ],
)
def test_czech_semantic_golden(source: str, expected: str) -> None:
    assert SpeechPreprocessor.czech_generic().prepare(source).spoken_text == expected


def test_czech_range_and_sentence_dash_have_distinct_meaning() -> None:
    spoken = SpeechPreprocessor.czech_generic().prepare(
        "něco jiného – moudrost, rozsah 10–20"
    ).spoken_text
    assert "jiného - moudrost" in spoken
    assert "deset až dvacet" in spoken


def test_final_model_chunks_obey_limit_after_respelling() -> None:
    prepared = SpeechPreprocessor.czech_omnivoice(max_chars=28).prepare(
        "Kupodivu kupodivu kupodivu kupodivu."
    )

    assert len(prepared.chunks) > 1
    assert all(len(chunk.model_text) <= 28 for chunk in prepared.chunks)


@dataclass(frozen=True)
class FakeBatchNormalizer:
    adapter_id: str = "fake.third-party/1"
    capabilities: AdapterCapabilities = AdapterCapabilities(
        locales=frozenset({LanguageTag("xx")}),
        live_safe=False,
        preserves_segments=False,
    )

    def normalize(
        self,
        text: SourceDocument,
        *,
        locale: LanguageTag,
    ) -> SpokenDocument:
        return SpokenDocument(display_text=text.text, text=text.text.upper())


def test_fake_third_party_adapter_is_batch_safe_but_refused_live() -> None:
    batch = SpeechPreprocessor(
        language=FakeBatchNormalizer(),
        model=VerbatimModelAdapter(
            locale=LanguageTag("xx"),
            target=TargetId("fake"),
            live_safe=False,
            preserves_segments=False,
        ),
        locale=LanguageTag("xx"),
        constraints=SynthesisConstraints(max_chars=20),
    )
    assert batch.prepare("hello").spoken_text == "HELLO"

    with pytest.raises(LiveCapabilityError):
        SpeechPreprocessor(
            language=FakeBatchNormalizer(),
            model=VerbatimModelAdapter(
                locale=LanguageTag("xx"),
                target=TargetId("fake"),
            ),
            locale=LanguageTag("xx"),
            constraints=SynthesisConstraints(max_chars=20, live=True),
        )


def test_unsupported_locale_is_typed_failure() -> None:
    with pytest.raises(UnsupportedLocaleError):
        SpeechPreprocessor.czech_generic(locale="en")


def test_verbatim_profile_is_explicit_and_deterministic() -> None:
    prepared = SpeechPreprocessor.verbatim("pl", target="omnivoice").prepare(
        "Zażółć 12."
    )
    assert prepared.spoken_text == "Zażółć 12."
    assert prepared.model_text == "Zażółć 12."
