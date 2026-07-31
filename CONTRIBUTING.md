# Contributing

Thank you for helping improve the Mendelio Voice SDK.

## Development

Use Node.js 20 or newer and pnpm 9:

```bash
pnpm install
pnpm typecheck
pnpm test
pnpm build
```

Keep the public SDK aligned with the API contract at
<https://api.mendelio.net/openapi.json>. Do not add telemetry, log credentials, or expose signed
audio and upload URLs beyond the operation that requested them.

Contributions to `packages/voice` and `packages/voice-mcp` are licensed under MIT. Contributions
to `python/voice-text` are licensed under Apache-2.0; derived pronunciation data retains the
licence documented beside that artifact.
