"""Built-in language normalizers."""

from __future__ import annotations

from dataclasses import dataclass
import re

from mendelio_voice_text.czech_numbers import cardinal, percent_words
from mendelio_voice_text.czech_spoken_forms import normalize_czech_spoken_forms
from mendelio_voice_text.locale import language_base, supports_locale
from mendelio_voice_text.types import (
    AdapterCapabilities,
    LanguageTag,
    SourceDocument,
    SpokenDocument,
    TextChange,
    UnsupportedLocaleError,
)


_DIGITS = re.compile(r"\d+")
_RANGE = re.compile(r"(\d+)\s*[–-]\s*(\d+)")
_PERCENT = re.compile(r"(\d+)\s*%")
_SPACE = re.compile(r"\s+")

_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("%", " procent"),
    ("µm", " mikrometrů"),
    ("→", " na "),
    ("≠", " není totéž co "),
    ("—", " - "),
    ("–", " - "),
    ("~", " přibližně "),
    ("+", " plus "),
    ("=", " rovná se "),
)


def _large_cardinal(value: int) -> str:
    if value < 10_000:
        return cardinal(value)
    return " ".join(cardinal(int(digit)) for digit in str(value))


def _digits_as_words(raw: str) -> str:
    """Convert an untrusted digit token without Python's huge-int limit."""
    if len(raw) <= 4:
        return _large_cardinal(int(raw))
    return " ".join(cardinal(ord(digit) - ord("0")) for digit in raw)


def normalize_czech_text(text: str) -> str:
    """Apply the canonical fixed-order Czech semantic pipeline."""
    normalized = normalize_czech_spoken_forms(text)
    normalized = _RANGE.sub(
        lambda match: f"{match.group(1)} až {match.group(2)}",
        normalized,
    )
    normalized = _PERCENT.sub(
        lambda match: (
            percent_words(int(match.group(1)))
            if len(match.group(1)) <= 4
            else f"{_digits_as_words(match.group(1))} procent"
        ),
        normalized,
    )
    for source, target in _SYMBOLS:
        normalized = normalized.replace(source, target)

    def replace_digits(match: re.Match[str]) -> str:
        words = _digits_as_words(match.group(0))
        prefix = (
            " "
            if match.start() > 0 and normalized[match.start() - 1].isalpha()
            else ""
        )
        suffix = (
            " "
            if match.end() < len(normalized) and normalized[match.end()].isalpha()
            else ""
        )
        return f"{prefix}{words}{suffix}"

    normalized = _DIGITS.sub(replace_digits, normalized)
    return _SPACE.sub(" ", normalized).strip()


@dataclass(frozen=True)
class CzechNormalizer:
    adapter_id: str = "mendelio.cs/0.1.0"
    capabilities: AdapterCapabilities = AdapterCapabilities(
        locales=frozenset({LanguageTag("cs")}),
        live_safe=True,
        preserves_segments=True,
    )

    def normalize(
        self,
        text: SourceDocument,
        *,
        locale: LanguageTag,
    ) -> SpokenDocument:
        if language_base(locale) != "cs":
            raise UnsupportedLocaleError(
                f"{self.adapter_id} does not support locale {locale}"
            )
        spoken = normalize_czech_text(text.text)
        changes: tuple[TextChange, ...] = ()
        if spoken != text.text:
            changes = (
                TextChange(
                    rule_id="cs.spoken_forms.pipeline",
                    category="abbreviation",
                    before=text.text,
                    after=spoken,
                ),
            )
        return SpokenDocument(
            display_text=text.text,
            text=spoken,
            changes=changes,
        )


@dataclass(frozen=True)
class VerbatimLanguageNormalizer:
    locale: LanguageTag
    live_safe: bool = True
    preserves_segments: bool = True

    @property
    def adapter_id(self) -> str:
        return f"verbatim.{self.locale}/0.1.0"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            locales=frozenset({self.locale}),
            live_safe=self.live_safe,
            preserves_segments=self.preserves_segments,
        )

    def normalize(
        self,
        text: SourceDocument,
        *,
        locale: LanguageTag,
    ) -> SpokenDocument:
        if not supports_locale(self.capabilities.locales, locale):
            raise UnsupportedLocaleError(
                f"{self.adapter_id} does not support locale {locale}"
            )
        return SpokenDocument(display_text=text.text, text=text.text)
