import assert from "node:assert/strict";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { MendelioVoice, readCredentials } from "mendelio-voice";

const credentials = readCredentials();
assert.ok(credentials?.api_key, "Run `mendelio-voice login` before the authenticated smoke");
const apiKey = credentials.api_key;
const client = new MendelioVoice({ apiKey, maxRetries: 1, timeoutMs: 30_000 });

const balance = await client.balance.get();
assert.equal(balance.object, "voice.balance");
assert.equal(balance.total, balance.available + balance.reserved);

const catalog = await client.voices.page({ language: "cs", limit: 50 });
const selectable = catalog.data.filter(
  (voice) => voice.availability === "available" && voice.capabilities.includes("speech"),
);
assert.ok(selectable.length > 0, "No selectable Czech speech voice is available");
const voiceVersionId = selectable[0].voiceVersionId;

const created = await client.generations.create({
  text: "Produkční kontrola veřejného hlasového rozhraní proběhla úspěšně.",
  voiceVersionId,
  format: "mp3",
  store: true,
});
assert.equal(created.object, "audio.speech_job");
const finished = await client.generations.waitFor(created.id, {
  timeoutMs: 180_000,
  pollIntervalMs: 2_000,
});
assert.equal(finished.state, "completed");
assert.equal(finished.output?.status, "available");

const audioResponse = await fetch(finished.output.url);
const audio = new Uint8Array(await audioResponse.arrayBuffer());
assert.equal(audioResponse.status, 200);
assert.ok(audioResponse.headers.get("content-type")?.startsWith("audio/mpeg"));
assert.ok(audio.byteLength > 1_000, `Downloaded audio is too small (${audio.byteLength} bytes)`);

const transport = new StreamableHTTPClientTransport(
  new URL("https://api.mendelio.net/mcp"),
  { requestInit: { headers: { authorization: `Bearer ${apiKey}` } } },
);
const mcp = new Client({ name: "mendelio-voice-authenticated-smoke", version: "1.0.0" });
let remoteTools;
try {
  await mcp.connect(transport);
  remoteTools = await mcp.listTools();
  const expectedNames = [
    "voice_generate_speech",
    "voice_list_voices",
    "voice_get_generation",
    "voice_get_balance",
    "voice_list_reference_prompts",
    "voice_clone_voice",
  ];
  assert.deepEqual(
    remoteTools.tools.map((tool) => tool.name),
    expectedNames,
    "Remote MCP is not using the shared W4b tool set",
  );

  const mcpBalance = await mcp.callTool({ name: "voice_get_balance", arguments: {} });
  assert.equal(mcpBalance.isError, undefined);
  assert.equal(mcpBalance.structuredContent?.balance?.unit, "audio_second");

  const generated = await mcp.callTool({
    name: "voice_generate_speech",
    arguments: {
      text: "Produkční kontrola vzdáleného MCP proběhla úspěšně.",
      voice_version_id: voiceVersionId,
      format: "mp3",
    },
  });
  assert.equal(generated.isError, undefined);
  assert.equal(generated.structuredContent?.status, "completed");
  const output = generated.structuredContent?.generation?.output;
  assert.equal(output?.status, "available");
  const mcpAudio = await fetch(output.url);
  assert.equal(mcpAudio.status, 200);
  assert.ok(mcpAudio.headers.get("content-type")?.startsWith("audio/mpeg"));
  assert.ok((await mcpAudio.arrayBuffer()).byteLength > 1_000);
} finally {
  await mcp.close();
}

process.stdout.write(
  `authenticated API and remote MCP audio passed (${audio.byteLength} API bytes, ${remoteTools.tools.length} tools)\n`,
);
