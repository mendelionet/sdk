"""Small deterministic BCP 47 canonicalization used at adapter boundaries."""

from __future__ import annotations

import re

from mendelio_voice_text.types import LanguageTag, UnsupportedLocaleError


_LANGUAGE_TAG_RE = re.compile(
    r"^(?P<language>[A-Za-z]{2,3})(?P<rest>(?:-[A-Za-z0-9]{2,8})*)$"
)


def canonicalize_language_tag(value: str) -> LanguageTag:
    raw = value.strip().replace("_", "-")
    match = _LANGUAGE_TAG_RE.fullmatch(raw)
    if not match:
        raise UnsupportedLocaleError(f"invalid BCP 47 language tag: {value!r}")
    parts = raw.split("-")
    canonical = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            canonical.append(part.title())
        elif len(part) == 2 and part.isalpha():
            canonical.append(part.upper())
        else:
            canonical.append(part.lower())
    return LanguageTag("-".join(canonical))


def language_base(locale: LanguageTag) -> str:
    return str(locale).split("-", 1)[0]


def supports_locale(
    supported: frozenset[LanguageTag],
    locale: LanguageTag,
) -> bool:
    wanted = str(locale)
    base = language_base(locale)
    return any(str(candidate) in {wanted, base} for candidate in supported)
