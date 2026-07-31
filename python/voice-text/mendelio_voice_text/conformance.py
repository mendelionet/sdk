"""Reusable conformance checks for third-party speech-text adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from mendelio_voice_text.preprocessor import SpeechPreprocessor
from mendelio_voice_text.types import (
    LanguageNormalizer,
    LanguageTag,
    LiveCapabilityError,
    ModelTextAdapter,
    SpeechPreprocessingError,
    SynthesisConstraints,
)


@dataclass(frozen=True)
class ConformanceViolation:
    code: str
    message: str
    case_index: int | None = None


@dataclass(frozen=True)
class AdapterConformanceReport:
    language_adapter_id: str
    model_adapter_id: str
    locale: LanguageTag
    cases_checked: int
    violations: tuple[ConformanceViolation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def assert_ok(self) -> None:
        if self.ok:
            return
        details = "; ".join(
            f"{violation.code}: {violation.message}"
            for violation in self.violations
        )
        raise AdapterConformanceError(details)


class AdapterConformanceError(AssertionError):
    """A third-party adapter violated the public adapter contract."""


def _normalized_words(text: str) -> tuple[str, ...]:
    return tuple(text.split())


def check_adapter_conformance(
    *,
    language: LanguageNormalizer,
    model: ModelTextAdapter,
    locale: str,
    samples: Iterable[str],
    max_chars: int = 300,
) -> AdapterConformanceReport:
    """Check deterministic composition, reconstruction and live declarations.

    The function performs no network access and is suitable for an external
    wrapper's own unit suite. Batch-only adapters are valid; their declared
    limitation must simply be enforced when composed as a live profile.
    """

    fixtures = tuple(samples)
    violations: list[ConformanceViolation] = []
    canonical_locale = LanguageTag(locale)
    try:
        preprocessor = SpeechPreprocessor(
            language=language,
            model=model,
            locale=canonical_locale,
            constraints=SynthesisConstraints(max_chars=max_chars),
        )
    except SpeechPreprocessingError as exc:
        violations.append(
            ConformanceViolation("unsupported_combination", str(exc))
        )
        return AdapterConformanceReport(
            language_adapter_id=language.adapter_id,
            model_adapter_id=model.adapter_id,
            locale=canonical_locale,
            cases_checked=0,
            violations=tuple(violations),
        )

    for index, source in enumerate(fixtures):
        try:
            first = preprocessor.prepare(source)
            second = preprocessor.prepare(source)
        except Exception as exc:
            violations.append(
                ConformanceViolation(
                    "prepare_error",
                    f"{type(exc).__name__}: {exc}",
                    index,
                )
            )
            continue
        if first != second:
            violations.append(
                ConformanceViolation(
                    "nondeterministic_output",
                    "identical input produced different PreparedSpeech values",
                    index,
                )
            )
        if first.display_text != source:
            violations.append(
                ConformanceViolation(
                    "display_text_changed",
                    "display_text must preserve the source document",
                    index,
                )
            )
        reconstructed_spoken = _normalized_words(
            " ".join(chunk.spoken_text for chunk in first.chunks)
        )
        if reconstructed_spoken != _normalized_words(first.spoken_text):
            violations.append(
                ConformanceViolation(
                    "spoken_reconstruction",
                    "speech chunks do not reconstruct spoken_text",
                    index,
                )
            )
        if " ".join(chunk.model_text for chunk in first.chunks) != first.model_text:
            violations.append(
                ConformanceViolation(
                    "model_reconstruction",
                    "speech chunks do not reconstruct model_text",
                    index,
                )
            )
        if any(len(chunk.model_text) > max_chars for chunk in first.chunks):
            violations.append(
                ConformanceViolation(
                    "model_chunk_limit",
                    f"a model chunk exceeds {max_chars} characters",
                    index,
                )
            )

    live_declared = (
        language.capabilities.live_safe
        and language.capabilities.preserves_segments
        and model.capabilities.live_safe
        and model.capabilities.preserves_segments
    )
    try:
        SpeechPreprocessor(
            language=language,
            model=model,
            locale=canonical_locale,
            constraints=SynthesisConstraints(max_chars=max_chars, live=True),
        )
    except LiveCapabilityError:
        if live_declared:
            violations.append(
                ConformanceViolation(
                    "live_capability_rejected",
                    "adapters declared live support but live composition failed",
                )
            )
    except SpeechPreprocessingError as exc:
        violations.append(
            ConformanceViolation("live_combination_error", str(exc))
        )
    else:
        if not live_declared:
            violations.append(
                ConformanceViolation(
                    "live_capability_not_enforced",
                    "batch-only adapter was accepted in a live profile",
                )
            )

    return AdapterConformanceReport(
        language_adapter_id=language.adapter_id,
        model_adapter_id=model.adapter_id,
        locale=preprocessor.locale,
        cases_checked=len(fixtures),
        violations=tuple(violations),
    )
