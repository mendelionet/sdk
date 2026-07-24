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

By contributing, you agree that your contribution is licensed under the MIT License in this
repository.
