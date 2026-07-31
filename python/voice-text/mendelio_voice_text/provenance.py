"""Stable non-content provenance for service health and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from mendelio_voice_text.models import OmniVoiceModelAdapter
from mendelio_voice_text.preprocessor import RULESET_ID


PACKAGE_VERSION = "0.1.0"


@dataclass(frozen=True)
class SpeechPackageProvenance:
    package_version: str
    ruleset_id: str
    model_adapter_id: str
    data_id: str


@lru_cache(maxsize=1)
def package_provenance() -> SpeechPackageProvenance:
    adapter = OmniVoiceModelAdapter()
    return SpeechPackageProvenance(
        package_version=PACKAGE_VERSION,
        ruleset_id=RULESET_ID,
        model_adapter_id=adapter.adapter_id,
        data_id=adapter.data_id,
    )
