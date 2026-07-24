import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const packageRoot = fileURLToPath(new URL("..", import.meta.url));
const emptyConfig = mkdtempSync(join(tmpdir(), "mendelio-mcp-stdio-"));
const env = Object.fromEntries(
  Object.entries(process.env).filter(
    ([key, value]) => value !== undefined && key !== "MENDELIO_VOICE_API_KEY",
  ),
);
env.XDG_CONFIG_HOME = emptyConfig;

const transport = new StdioClientTransport({
  command: process.execPath,
  args: [join(packageRoot, "dist/index.js")],
  cwd: packageRoot,
  env,
  stderr: "pipe",
});
const client = new Client({ name: "mendelio-voice-mcp-stdio-smoke", version: "1.0.0" });

try {
  await client.connect(transport);

  const listed = await client.listTools();
  assert.deepEqual(
    listed.tools.map((tool) => tool.name),
    [
      "voice_generate_speech",
      "voice_list_voices",
      "voice_get_generation",
      "voice_get_balance",
      "voice_list_reference_prompts",
      "voice_clone_voice",
      "voice_record_and_clone",
      "voice_login",
    ],
  );

  const balance = await client.callTool({ name: "voice_get_balance", arguments: {} });
  assert.deepEqual(balance.structuredContent, {
    status: "authentication_required",
    action: "voice_login",
  });
  assert.equal(balance.isError, undefined);

  const invalid = await client.callTool({ name: "voice_generate_speech", arguments: {} });
  assert.equal(invalid.isError, true);
  assert.equal(invalid.structuredContent, undefined);

  const unsafeClone = await client.callTool({
    name: "voice_clone_voice",
    arguments: {
      name: "Schema probe",
      reference_text_id: "prompt-cs",
      audio_path: "/tmp/probe.wav",
    },
  });
  assert.equal(unsafeClone.isError, true);
  assert.equal(unsafeClone.structuredContent, undefined);

  process.stdout.write("stdio initialize, tools/list, tools/call, and schema validation passed\n");
} finally {
  await client.close();
}
