# Contributing

Every linguistic change needs positive fixtures, ambiguity guards, provenance,
idempotence and a bounded performance check. Pronunciation changes additionally
need an authorized listening evaluation against the production OmniVoice
runbook; OmniVoice is never run locally.

Do not add network calls, default telemetry, a global plugin registry or a
mandatory heavyweight NLP dependency.
