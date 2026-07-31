# Mendelio Voice Text

Speech text preprocessing with production Czech and OmniVoice support, built by
Mendelio. `mendelio-voice-text` is deterministic, language-extensible, and keeps
three representations distinct:

- `display_text`: the original human-facing text;
- `spoken_text`: language-normalized text;
- `model_text`: text adapted for a specific synthesis model.

```python
from mendelio_voice_text import SpeechPreprocessor

prepared = SpeechPreprocessor.czech_omnivoice(max_chars=300).prepare(
    "Ve 20. století stálo 5 km cesty 10 Kč."
)
for chunk in prepared.chunks:
    send_to_model(chunk.model_text)
```

```bash
pip install mendelio-voice-text
```

The built-in Czech profile is deterministic and performs no network calls or
telemetry. Other catalogue languages use an explicitly selected verbatim
language profile until a real normalizer with its own corpus and evaluation is
integrated. Unknown combinations fail; there is no silent fallback.

This public package is the canonical implementation used by Mendelio speech
callers and powers **Hezky česky**. To synthesize the prepared text with more
than 190 voices, [try Mendelio Voice](https://voice.mendelio.net/?utm_source=github&utm_medium=repository&utm_campaign=voice_text).

## Wrapping an external normalizer

There is no plugin registry. Wrap a library behind the typed protocol and run
the reusable conformance suite in that wrapper's own tests:

```python
from dataclasses import dataclass

from mendelio_voice_text import (
    AdapterCapabilities,
    LanguageTag,
    SourceDocument,
    SpokenDocument,
    TargetId,
    VerbatimModelAdapter,
    check_adapter_conformance,
)


@dataclass(frozen=True)
class ExternalNormalizer:
    library: object
    adapter_id: str = "example.external/1"
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
        normalized = self.library.normalize(text.text)
        return SpokenDocument(display_text=text.text, text=normalized)


report = check_adapter_conformance(
    language=ExternalNormalizer(library=my_library),
    model=VerbatimModelAdapter(
        locale=LanguageTag("xx"),
        target=TargetId("example-model"),
        live_safe=False,
        preserves_segments=False,
    ),
    locale="xx",
    samples=("Synthetic fixture.", "Another fixture."),
)
report.assert_ok()
```

A batch-only adapter is valid. Declaring `live_safe=False` ensures that live
composition fails explicitly instead of silently weakening partial spoken-text
truth.

The same seam replaces a synthesis model independently of the language
normalizer. Keep `CzechNormalizer`, then supply either `VerbatimModelAdapter`
for a model that accepts normalized text directly or a model-specific
`ModelTextAdapter` for phonemes, SSML, pronunciation overrides, and provider
limits. See `ARCHITECTURE.md`.

## CLI and release checks

```bash
mendelio-voice-text normalize --profile cs-omnivoice "Ve 20. století."
mendelio-voice-text explain --profile cs-omnivoice "Kupodivu."
mendelio-voice-text benchmark --profile cs-generic --bundled-corpus
python tools/verify_release_artifact.py
```

The bundled benchmark corpus is synthetic CC0 data. The release verifier builds
both archive formats, checks code/data licence files, scans the sdist for
private or secret markers, and imports the wheel from a fresh virtualenv.

Package code is Apache-2.0. The bundled Czech Wiktionary-derived pronunciation
artifact is CC BY-SA 4.0; see `NOTICE` and the adjacent data licence.
