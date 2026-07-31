# Architecture

`SpeechPreprocessor.prepare()` is the only product-facing preparation seam.
It composes a `LanguageNormalizer`, then a `ModelTextAdapter`, then plans
chunks over final `model_text`.

Adapters are immutable objects with explicit locale and live-safety
capabilities. A third-party normalizer is wrapped by implementing the small
protocol; it is not discovered through a global plugin registry. An adapter
that cannot preserve segment truth declares `live_safe=False` and is refused
by a live profile.

Protocol/control sanitation remains consumer-owned and happens before this
package. GPU synthesis receives wire-v2 final `model_text` and performs no
linguistic mutation.

## Replacing a synthesis backend

The reusable language work and the model-specific work are separate seams.
Replacing OmniVoice does not require copying or changing Czech normalization:

```python
preprocessor = SpeechPreprocessor(
    language=CzechNormalizer(),
    model=NewSynthesisModelAdapter(),
    locale=LanguageTag("cs"),
    constraints=SynthesisConstraints(max_chars=provider_limit, live=True),
)
prepared = preprocessor.prepare(source_text)
send_to_provider(prepared.model_text)
```

If the replacement accepts ordinary normalized text, use
`VerbatimModelAdapter` instead of implementing a no-op adapter. A provider with
special phonemes, SSML, token limits, or pronunciation data supplies its own
`ModelTextAdapter`. The provider transport and voice catalogue stay outside
this module; they consume `PreparedSpeech` and do not own language rules.
