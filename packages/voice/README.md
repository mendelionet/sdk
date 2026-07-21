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
```

See the [repository README](https://github.com/mendelionet/sdk) for the full guide (voice cloning,
webhooks, the CLI, and the MCP server). MIT. No telemetry. Requests are camelCase, responses are
snake_case — the SDK mirrors the wire 1:1.
