"""Mendelio Voice Text: deterministic speech preprocessing."""

from mendelio_voice_text.conformance import (
    AdapterConformanceError,
    AdapterConformanceReport,
    ConformanceViolation,
    check_adapter_conformance,
)
from mendelio_voice_text.locale import canonicalize_language_tag
from mendelio_voice_text.models import OmniVoiceModelAdapter, VerbatimModelAdapter
from mendelio_voice_text.normalizers import (
    CzechNormalizer,
    VerbatimLanguageNormalizer,
)
from mendelio_voice_text.preprocessor import RULESET_ID, SpeechPreprocessor
from mendelio_voice_text.provenance import (
    PACKAGE_VERSION,
    SpeechPackageProvenance,
    package_provenance,
)
from mendelio_voice_text.synthesis_split import (
    BATCH_MAX_SYNTHESIS_CHARS,
    LIVE_HARD_FLUSH_CHARS,
    ZEROSHOT_MAX_TEXT_CHARS,
)
from mendelio_voice_text.types import (
    AdapterCapabilities,
    ChunkConstraintError,
    LanguageNormalizer,
    LanguageTag,
    LiveCapabilityError,
    ModelDocument,
    ModelTextAdapter,
    NormalizationWarning,
    PreparedSpeech,
    SourceDocument,
    SpeechChunk,
    SpeechPreprocessingError,
    SpokenDocument,
    SynthesisConstraints,
    TargetId,
    TextChange,
    UnsupportedLocaleError,
    UnsupportedTargetError,
)

__version__ = PACKAGE_VERSION

__all__ = [
    "AdapterConformanceError",
    "AdapterConformanceReport",
    "AdapterCapabilities",
    "BATCH_MAX_SYNTHESIS_CHARS",
    "ChunkConstraintError",
    "ConformanceViolation",
    "CzechNormalizer",
    "LIVE_HARD_FLUSH_CHARS",
    "LanguageNormalizer",
    "LanguageTag",
    "LiveCapabilityError",
    "ModelDocument",
    "ModelTextAdapter",
    "NormalizationWarning",
    "OmniVoiceModelAdapter",
    "PreparedSpeech",
    "SpeechPackageProvenance",
    "RULESET_ID",
    "SourceDocument",
    "SpeechChunk",
    "SpeechPreprocessingError",
    "SpeechPreprocessor",
    "SpokenDocument",
    "SynthesisConstraints",
    "TargetId",
    "TextChange",
    "UnsupportedLocaleError",
    "UnsupportedTargetError",
    "VerbatimLanguageNormalizer",
    "VerbatimModelAdapter",
    "ZEROSHOT_MAX_TEXT_CHARS",
    "__version__",
    "canonicalize_language_tag",
    "check_adapter_conformance",
    "package_provenance",
]
