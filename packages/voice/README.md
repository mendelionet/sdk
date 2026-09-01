# mendelio-voice

Official zero-dependency TypeScript/Node SDK for the [Mendelio Voice API](https://voice.mendelio.net/developers).

```bash
npm install mendelio-voice
npx mendelio-voice login
```

```ts
import { MendelioVoice } from "mendelio-voice";
const client = new MendelioVoice();
const { audio } = await client.speak({ text: "Ahoj!" });

// Moving aliases are resolved from the live catalogue to an exact version.
const soniox = await client.models.resolve("soniox");
const result = await client.speak({
  text: "Dobrý den.",
  voiceVersionId: "<voice-version-id>",
  model: soniox.id,
});
```

See the [repository README](https://github.com/mendelionet/sdk) for the full guide (voice cloning,
webhooks, the CLI, and the MCP server). MIT. No telemetry. Requests are camelCase, responses are
snake_case — the SDK mirrors the wire 1:1.
