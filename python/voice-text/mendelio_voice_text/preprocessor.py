"""The single deep product interface for speech text preparation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from mendelio_voice_text.locale import (
    canonicalize_language_tag,
    supports_locale,
)
from mendelio_voice_text.models import (
    OmniVoiceModelAdapter,
    VerbatimModelAdapter,
)
from mendelio_voice_text.normalizers import (
    CzechNormalizer,
    VerbatimLanguageNormalizer,
)
from mendelio_voice_text.synthesis_split import split_for_synthesis
from mendelio_voice_text.types import (
    ChunkConstraintError,
    LanguageNormalizer,
    LanguageTag,
    LiveCapabilityError,
    ModelTextAdapter,
    PreparedSpeech,
    SourceDocument,
    SpeechChunk,
    SpokenDocument,
    SynthesisConstraints,
    TargetId,
    UnsupportedLocaleError,
    UnsupportedTargetError,
)


RULESET_ID = "mendelio-voice-text/0.1.0"


def _require_adapter_support(
    adapter: LanguageNormalizer | ModelTextAdapter,
    locale: LanguageTag,
    *,
    live: bool,
) -> None:
    if not supports_locale(adapter.capabilities.locales, locale):
        raise UnsupportedLocaleError(
            f"{adapter.adapter_id} does not support locale {locale}"
        )
    if live and (
        not adapter.capabilities.live_safe
        or not adapter.capabilities.preserves_segments
    ):
        raise LiveCapabilityError(
            f"{adapter.adapter_id} is batch-only and cannot be used live"
        )


def _model_text(
    model: ModelTextAdapter,
    spoken: str,
    *,
    locale: LanguageTag,
) -> str:
    return model.adapt(
        SpokenDocument(display_text=spoken, text=spoken),
        locale=locale,
    ).text


def _largest_prefix_that_fits(
    text: str,
    *,
    model: ModelTextAdapter,
    locale: LanguageTag,
    max_chars: int,
) -> tuple[str, str]:
    """Return the longest leading human-readable piece whose model text fits."""
    candidate = split_for_synthesis(text, max_chars=max_chars)[0]
    model_candidate = _model_text(model, candidate, locale=locale)
    if len(model_candidate) <= max_chars:
        return candidate, model_candidate

    boundaries = [
        index
        for index, char in enumerate(candidate, start=1)
        if char.isspace() or char in ".,;:!?"
    ]
    for end in reversed(boundaries):
        spoken = candidate[:end].strip()
        if not spoken:
            continue
        adapted = _model_text(model, spoken, locale=locale)
        if len(adapted) <= max_chars:
            return spoken, adapted

    for end in range(min(len(candidate), max_chars), 0, -1):
        spoken = candidate[:end].strip()
        if not spoken:
            continue
        adapted = _model_text(model, spoken, locale=locale)
        if len(adapted) <= max_chars:
            return spoken, adapted
    raise ChunkConstraintError(
        "model adaptation cannot fit even one source character into max_chars"
    )


@dataclass(frozen=True)
class SpeechPreprocessor:
    language: LanguageNormalizer
    model: ModelTextAdapter
    locale: LanguageTag
    constraints: SynthesisConstraints = SynthesisConstraints()
    ruleset_id: str = RULESET_ID

    def __post_init__(self) -> None:
        canonical = canonicalize_language_tag(str(self.locale))
        object.__setattr__(self, "locale", canonical)
        _require_adapter_support(
            self.language,
            canonical,
            live=self.constraints.live,
        )
        _require_adapter_support(
            self.model,
            canonical,
            live=self.constraints.live,
        )
        if not str(self.model.target).strip():
            raise UnsupportedTargetError("model adapter target must not be blank")

    @classmethod
    def czech_generic(
        cls,
        *,
        locale: str = "cs",
        max_chars: int = 300,
        live: bool = False,
    ) -> "SpeechPreprocessor":
        canonical = canonicalize_language_tag(locale)
        return cls(
            language=CzechNormalizer(),
            model=VerbatimModelAdapter(
                locale=canonical,
                target=TargetId("generic"),
            ),
            locale=canonical,
            constraints=SynthesisConstraints(max_chars=max_chars, live=live),
        )

    @classmethod
    def czech_omnivoice(
        cls,
        *,
        locale: str = "cs",
        max_chars: int = 300,
        live: bool = False,
    ) -> "SpeechPreprocessor":
        canonical = canonicalize_language_tag(locale)
        return cls(
            language=CzechNormalizer(),
            model=OmniVoiceModelAdapter(),
            locale=canonical,
            constraints=SynthesisConstraints(max_chars=max_chars, live=live),
        )

    @classmethod
    def verbatim(
        cls,
        locale: str,
        *,
        target: str = "generic",
        max_chars: int = 300,
        live: bool = False,
    ) -> "SpeechPreprocessor":
        canonical = canonicalize_language_tag(locale)
        return cls(
            language=VerbatimLanguageNormalizer(canonical),
            model=VerbatimModelAdapter(
                locale=canonical,
                target=TargetId(target),
            ),
            locale=canonical,
            constraints=SynthesisConstraints(max_chars=max_chars, live=live),
        )

    def prepare(self, text: str) -> PreparedSpeech:
        source = SourceDocument(text)
        spoken = self.language.normalize(source, locale=self.locale)
        full_model = self.model.adapt(spoken, locale=self.locale)
        chunks: list[SpeechChunk] = []
        remaining = spoken.text.strip()
        model_changes = []

        while remaining:
            spoken_piece, model_piece = _largest_prefix_that_fits(
                remaining,
                model=self.model,
                locale=self.locale,
                max_chars=self.constraints.max_chars,
            )
            piece_document = self.model.adapt(
                SpokenDocument(display_text=spoken_piece, text=spoken_piece),
                locale=self.locale,
            )
            model_changes.extend(piece_document.changes)
            chunks.append(
                SpeechChunk(
                    display_text=spoken_piece,
                    spoken_text=spoken_piece,
                    model_text=model_piece,
                )
            )
            remaining = remaining[len(spoken_piece) :].lstrip()

        model_text = " ".join(chunk.model_text for chunk in chunks)
        if not chunks and full_model.text:
            model_text = full_model.text
        identity = json.dumps(
            [
                model_text,
                str(self.locale),
                self.language.adapter_id,
                self.model.adapter_id,
                self.ruleset_id,
                self.model.data_id,
                self.constraints.max_chars,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return PreparedSpeech(
            locale=self.locale,
            target=self.model.target,
            language_adapter_id=self.language.adapter_id,
            model_adapter_id=self.model.adapter_id,
            display_text=text,
            spoken_text=spoken.text,
            model_text=model_text,
            chunks=tuple(chunks),
            changes=spoken.changes + tuple(model_changes),
            warnings=spoken.warnings + full_model.warnings,
            ruleset_id=self.ruleset_id,
            data_id=self.model.data_id,
            speech_plan_hash=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        )
