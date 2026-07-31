"""Immutable public types for Mendelio speech preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType, Protocol, runtime_checkable


LanguageTag = NewType("LanguageTag", str)
TargetId = NewType("TargetId", str)


class SpeechPreprocessingError(ValueError):
    """Base class for typed preprocessing failures."""


class UnsupportedLocaleError(SpeechPreprocessingError):
    """The selected adapter does not declare support for the requested locale."""


class UnsupportedTargetError(SpeechPreprocessingError):
    """The selected model adapter cannot serve the requested target."""


class LiveCapabilityError(SpeechPreprocessingError):
    """A batch-only adapter was selected for a live preprocessing profile."""


class ChunkConstraintError(SpeechPreprocessingError):
    """No valid model chunk can satisfy the configured synthesis constraint."""


@dataclass(frozen=True)
class TextChange:
    rule_id: str
    category: str
    before: str
    after: str
    source_start: int | None = None
    source_end: int | None = None


@dataclass(frozen=True)
class NormalizationWarning:
    code: str
    message: str


@dataclass(frozen=True)
class SourceDocument:
    text: str


@dataclass(frozen=True)
class SpokenDocument:
    display_text: str
    text: str
    changes: tuple[TextChange, ...] = ()
    warnings: tuple[NormalizationWarning, ...] = ()


@dataclass(frozen=True)
class ModelDocument:
    display_text: str
    spoken_text: str
    text: str
    changes: tuple[TextChange, ...] = ()
    warnings: tuple[NormalizationWarning, ...] = ()
    data_id: str | None = None


@dataclass(frozen=True)
class SpeechChunk:
    display_text: str
    spoken_text: str
    model_text: str
    source_start: int | None = None
    source_end: int | None = None


@dataclass(frozen=True)
class PreparedSpeech:
    locale: LanguageTag
    target: TargetId
    language_adapter_id: str
    model_adapter_id: str
    display_text: str
    spoken_text: str
    model_text: str
    chunks: tuple[SpeechChunk, ...]
    changes: tuple[TextChange, ...]
    warnings: tuple[NormalizationWarning, ...]
    ruleset_id: str
    data_id: str | None
    speech_plan_hash: str


@dataclass(frozen=True)
class AdapterCapabilities:
    locales: frozenset[LanguageTag]
    live_safe: bool
    preserves_segments: bool


@dataclass(frozen=True)
class SynthesisConstraints:
    max_chars: int = 300
    live: bool = False

    def __post_init__(self) -> None:
        if self.max_chars < 1:
            raise ChunkConstraintError(
                f"max_chars must be at least 1, got {self.max_chars}"
            )


@runtime_checkable
class LanguageNormalizer(Protocol):
    adapter_id: str
    capabilities: AdapterCapabilities

    def normalize(
        self,
        text: SourceDocument,
        *,
        locale: LanguageTag,
    ) -> SpokenDocument: ...


@runtime_checkable
class ModelTextAdapter(Protocol):
    adapter_id: str
    capabilities: AdapterCapabilities
    target: TargetId
    data_id: str | None

    def adapt(
        self,
        text: SpokenDocument,
        *,
        locale: LanguageTag,
    ) -> ModelDocument: ...
