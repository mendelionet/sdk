# Mendelio Voice SDK

Official SDKs and tools for the [Mendelio Voice API](https://voice.mendelio.net/developers) —
generate natural Czech (and multilingual) speech, clone voices from a short recording, and drive it
all from your editor over MCP.

| Package | What it is |
|---|---|
| [`mendelio-voice`](./packages/voice) | Zero-dependency TypeScript/Node SDK + `mendelio-voice` CLI |
| [`mendelio-voice-mcp`](./packages/voice-mcp) | MCP server — use Mendelio Voice from Claude, Codex, Cursor… |

## Quickstart (TypeScript)

```bash
npm install mendelio-voice
npx mendelio-voice login          # opens the browser, one click to approve
```

```ts
import { MendelioVoice } from "mendelio-voice";
import { writeFileSync } from "node:fs";

const client = new MendelioVoice(); // reads the key saved by `login`, or MENDELIO_VOICE_API_KEY

// One call: pick a system voice, generate, wait, download.
const { audio } = await client.speak({ text: "Ahoj! Tohle je Mendelio Voice." });
writeFileSync("hello.mp3", audio);
```

You can also set the key explicitly: `new MendelioVoice({ apiKey: "mv_live_…" })`, or via the
`MENDELIO_VOICE_API_KEY` environment variable.

## Česky

`mendelio-voice` je oficiální klient pro Mendelio Voice API. Vygeneruje přirozený český hlas z textu,
naklonuje hlas z krátké nahrávky a ověří webhooky. Přihlásíš se přes `npx mendelio-voice login`
(jeden klik v prohlížeči), nebo nastavíš `MENDELIO_VOICE_API_KEY`. Kredit dobiješ na
[voice.mendelio.net/credit](https://voice.mendelio.net/credit).

## MCP (Claude, Codex, Cursor)

```bash
claude mcp add mendelio-voice -- npx -y mendelio-voice-mcp
```

Or connect the **remote** server (no install) in claude.ai → Connectors:
`https://api.mendelio.net/mcp` — approval is one click.

## Cloning a voice

```ts
import { readFileSync } from "node:fs";
const prompts = await client.referencePrompts.list({ language: "cs" });
const voice = await client.voices.createFromFile({
  name: "My voice",
  referenceTextId: prompts[0].id,     // read this text aloud when you record
  file: readFileSync("reference.wav"),
});
const ready = await client.voices.waitForReady(voice.id);
```

## Webhooks

```ts
import { constructEvent } from "mendelio-voice";
const event = await constructEvent(rawBody, req.headers, process.env.WEBHOOK_SECRET!);
// deduplicate by event.id — deliveries are at-least-once
```

## Docs

- API reference & OpenAPI: <https://api.mendelio.net/openapi.json>
- Developer console (keys, interactive reference): <https://voice.mendelio.net/developers>

MIT licensed. No telemetry.
