from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from mendelio_voice_text import (
    AdapterCapabilities,
    AdapterConformanceError,
    LanguageTag,
    ModelDocument,
    SpeechPreprocessor,
    SourceDocument,
    SpokenDocument,
    TargetId,
    VerbatimModelAdapter,
    check_adapter_conformance,
)


@dataclass
class ExternalNormalizer:
    adapter_id: str = "external.example/1"
    capabilities: AdapterCapabilities = AdapterCapabilities(
        locales=frozenset({LanguageTag("xx")}),
        live_safe=True,
        preserves_segments=True,
    )

    def normalize(
        self,
        text: SourceDocument,
        *,
        locale: LanguageTag,
    ) -> SpokenDocument:
        return SpokenDocument(display_text=text.text, text=text.text.upper())


def test_external_adapter_conformance_report_is_reusable() -> None:
    report = check_adapter_conformance(
        language=ExternalNormalizer(),
        model=VerbatimModelAdapter(
            locale=LanguageTag("xx"),
            target=TargetId("example"),
        ),
        locale="xx",
        samples=("hello world", "two segments " * 20),
        max_chars=30,
    )

    assert report.ok
    assert report.cases_checked == 2
    report.assert_ok()


def test_batch_only_adapter_is_valid_and_live_rejection_is_enforced() -> None:
    normalizer = ExternalNormalizer(
        capabilities=AdapterCapabilities(
            locales=frozenset({LanguageTag("xx")}),
            live_safe=False,
            preserves_segments=False,
        )
    )
    report = check_adapter_conformance(
        language=normalizer,
        model=VerbatimModelAdapter(
            locale=LanguageTag("xx"),
            target=TargetId("example"),
            live_safe=False,
            preserves_segments=False,
        ),
        locale="xx",
        samples=("batch input",),
    )

    assert report.ok


@dataclass
class NondeterministicModelAdapter:
    adapter_id: str = "external.nondeterministic/1"
    target: TargetId = TargetId("example")
    data_id: str | None = None
    capabilities: AdapterCapabilities = AdapterCapabilities(
        locales=frozenset({LanguageTag("xx")}),
        live_safe=True,
        preserves_segments=True,
    )
    calls: int = field(default=0, init=False)

    def adapt(
        self,
        text: SpokenDocument,
        *,
        locale: LanguageTag,
    ) -> ModelDocument:
        self.calls += 1
        return ModelDocument(
            display_text=text.display_text,
            spoken_text=text.text,
            text=f"{text.text}:{self.calls}",
        )


@dataclass(frozen=True)
class ExternalModelAdapter:
    """Example adapter for a synthesis model with its own input notation."""

    adapter_id: str = "external.model/1"
    target: TargetId = TargetId("external-tts")
    data_id: str | None = "external-model-rules-v1"
    capabilities: AdapterCapabilities = AdapterCapabilities(
        locales=frozenset({LanguageTag("xx")}),
        live_safe=True,
        preserves_segments=True,
    )

    def adapt(
        self,
        text: SpokenDocument,
        *,
        locale: LanguageTag,
    ) -> ModelDocument:
        return ModelDocument(
            display_text=text.display_text,
            spoken_text=text.text,
            text=f"<speak>{text.text}</speak>",
            data_id=self.data_id,
        )


def test_external_synthesis_model_reuses_the_same_preprocessor_contract() -> None:
    model = ExternalModelAdapter()
    report = check_adapter_conformance(
        language=ExternalNormalizer(),
        model=model,
        locale="xx",
        samples=("replace the synthesis backend",),
        max_chars=40,
    )
    prepared = SpeechPreprocessor(
        language=ExternalNormalizer(),
        model=model,
        locale=LanguageTag("xx"),
    ).prepare("replace the synthesis backend")

    assert report.ok
    assert prepared.target == TargetId("external-tts")
    assert prepared.spoken_text == "REPLACE THE SYNTHESIS BACKEND"
    assert prepared.model_text == (
        "<speak>REPLACE THE SYNTHESIS BACKEND</speak>"
    )


def test_conformance_reports_nondeterministic_adapter() -> None:
    report = check_adapter_conformance(
        language=ExternalNormalizer(),
        model=NondeterministicModelAdapter(),
        locale="xx",
        samples=("hello",),
    )

    assert not report.ok
    assert any(
        violation.code == "nondeterministic_output"
        for violation in report.violations
    )
    with pytest.raises(AdapterConformanceError):
        report.assert_ok()


def test_conformance_reports_unsupported_locale_as_typed_combination() -> None:
    report = check_adapter_conformance(
        language=ExternalNormalizer(),
        model=VerbatimModelAdapter(
            locale=LanguageTag("xx"),
            target=TargetId("example"),
        ),
        locale="yy",
        samples=("hello",),
    )

    assert [violation.code for violation in report.violations] == [
        "unsupported_combination"
    ]
