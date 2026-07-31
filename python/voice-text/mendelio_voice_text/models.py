"""Built-in model-facing text adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from importlib.resources import files
import json
import re
from types import MappingProxyType
from typing import Mapping

from mendelio_voice_text.locale import language_base, supports_locale
from mendelio_voice_text.types import (
    AdapterCapabilities,
    LanguageTag,
    ModelDocument,
    SpokenDocument,
    TargetId,
    TextChange,
    UnsupportedLocaleError,
)


_WORD_PATTERN = re.compile(r"\b[^\W\d_]+\b", re.UNICODE)

_EXACT_RESPELLINGS: tuple[tuple[str, str], ...] = (
    ("nashle", "naschle"),
    ("šlechticky", "šlechťycky"),
    ("neutrality", "ne-utrality"),
    ("existence", "existencee"),
    ("puzzle", "puccle"),
    ("chaos", "chchaos"),
    ("pohraniční", "pohraňičňí"),
)

_STEM_RESPELLINGS: tuple[tuple[str, str], ...] = (
    ("versaillesk", "versajsk"),
    ("appeasement", "apízment"),
    ("kancléř", "kantsléř"),
    ("versailles", "versaj"),
    ("muhammad", "mohamed"),
    ("mohammed", "mohamed"),
    ("gibraltar", "džibraltar"),
    ("biblick", "byblitsk"),
    ("bibl", "bybl"),
    ("nizozem", "nízozem"),
    ("mein", "majn"),
)

_PARADIGM_RESPELLINGS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "tipn",
        (
            "out",
            "u",
            "eš",
            "e",
            "eme",
            "ete",
            "ou",
            "i",
            "ěte",
            "ul",
            "ula",
            "ulo",
            "uli",
            "uly",
            "utí",
        ),
        "typn",
    ),
)


def _match_case(written: str, model: str) -> str:
    if written.isupper():
        return model.upper()
    if written[:1].isupper():
        return model[:1].upper() + model[1:]
    return model


@dataclass(frozen=True)
class VerbatimModelAdapter:
    locale: LanguageTag
    target: TargetId = TargetId("generic")
    live_safe: bool = True
    preserves_segments: bool = True
    data_id: str | None = None

    @property
    def adapter_id(self) -> str:
        return f"verbatim.{self.target}/0.1.0"

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            locales=frozenset({self.locale}),
            live_safe=self.live_safe,
            preserves_segments=self.preserves_segments,
        )

    def adapt(
        self,
        text: SpokenDocument,
        *,
        locale: LanguageTag,
    ) -> ModelDocument:
        if not supports_locale(self.capabilities.locales, locale):
            raise UnsupportedLocaleError(
                f"{self.adapter_id} does not support locale {locale}"
            )
        return ModelDocument(
            display_text=text.display_text,
            spoken_text=text.text,
            text=text.text,
            warnings=text.warnings,
        )


@dataclass(frozen=True)
class OmniVoiceModelAdapter:
    """Czech OmniVoice respelling, owned by trusted CPU preprocessing."""

    custom_exact: Mapping[str, str] = field(default_factory=dict)
    target: TargetId = TargetId("omnivoice")
    adapter_id: str = "omnivoice.cs/0.1.0"
    capabilities: AdapterCapabilities = AdapterCapabilities(
        locales=frozenset({LanguageTag("cs")}),
        live_safe=True,
        preserves_segments=True,
    )
    _corpus: Mapping[str, str] = field(init=False, repr=False, compare=False)
    data_id: str = field(init=False)
    _rules: tuple[tuple[re.Pattern[str], str], ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        resource = files("mendelio_voice_text.data").joinpath(
            "czech_ipa_transliteration_map.json"
        )
        raw = resource.read_bytes()
        payload = json.loads(raw)
        if (
            payload.get("format_version") != 1
            or payload.get("license") != "CC-BY-SA-4.0"
        ):
            raise RuntimeError("unsupported Czech pronunciation data artifact")
        corpus = MappingProxyType(dict(payload["entries"]))
        custom = tuple(
            (str(written).casefold(), str(model))
            for written, model in self.custom_exact.items()
        )
        exact = custom + _EXACT_RESPELLINGS
        rules = tuple(
            (
                re.compile(rf"\b{re.escape(written)}\b", re.IGNORECASE),
                model,
            )
            for written, model in exact
        )
        rules += tuple(
            (
                re.compile(rf"\b{re.escape(stem)}", re.IGNORECASE),
                model,
            )
            for stem, model in _STEM_RESPELLINGS
        )
        rules += tuple(
            (
                re.compile(
                    rf"\b{re.escape(stem)}(?=(?:{'|'.join(re.escape(ending) for ending in sorted(endings, key=len, reverse=True))})\b)",
                    re.IGNORECASE,
                ),
                model,
            )
            for stem, endings, model in _PARADIGM_RESPELLINGS
        )
        object.__setattr__(self, "_corpus", corpus)
        object.__setattr__(self, "_rules", rules)
        object.__setattr__(self, "data_id", f"sha256:{hashlib.sha256(raw).hexdigest()}")

    @property
    def corpus_entry_count(self) -> int:
        return len(self._corpus)

    def adapt(
        self,
        text: SpokenDocument,
        *,
        locale: LanguageTag,
    ) -> ModelDocument:
        if language_base(locale) != "cs":
            raise UnsupportedLocaleError(
                f"{self.adapter_id} does not support locale {locale}"
            )
        model_text = text.text
        for pattern, replacement in self._rules:
            model_text = pattern.sub(
                lambda match, value=replacement: _match_case(
                    match.group(0),
                    value,
                ),
                model_text,
            )

        def replace_corpus_word(match: re.Match[str]) -> str:
            written = match.group(0)
            replacement = self._corpus.get(written.casefold())
            return _match_case(written, replacement) if replacement else written

        model_text = _WORD_PATTERN.sub(replace_corpus_word, model_text)
        changes: tuple[TextChange, ...] = ()
        if model_text != text.text:
            changes = (
                TextChange(
                    rule_id="cs.pronunciation.omnivoice",
                    category="pronunciation_corpus",
                    before=text.text,
                    after=model_text,
                ),
            )
        return ModelDocument(
            display_text=text.display_text,
            spoken_text=text.text,
            text=model_text,
            changes=changes,
            warnings=text.warnings,
            data_id=self.data_id,
        )
