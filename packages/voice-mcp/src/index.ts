#!/usr/bin/env node
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { deviceLogin, MENDELIO_VOICE_MCP_CLIENT_ID, MendelioVoice, readCredentials } from "mendelio-voice";
import { buildTools } from "./core.js";
import { recordMicrophone } from "./record.js";
import { MendelioVoiceSdkOperations } from "./sdkOperations.js";

/**
 * The stdio MCP server: `npx -y mendelio-voice-mcp`. Registers the local tool set (with microphone
 * capture and device login) and speaks MCP over stdin/stdout. The key is resolved fresh on every
 * tool call, so a login that completes in the background is picked up by the next call.
 */
async function main(): Promise<void> {
  const server = new McpServer({ name: "mendelio-voice", version: "0.1.0" });

  const tools = buildTools({
    mode: "local",
    operations: () => {
      const apiKey = process.env.MENDELIO_VOICE_API_KEY ?? readCredentials()?.api_key;
      return apiKey ? new MendelioVoiceSdkOperations(new MendelioVoice({ apiKey })) : null;
    },
    record: recordMicrophone,
    writeAudio: (bytes, name) => {
      const path = resolve(process.cwd(), name);
      writeFileSync(path, bytes);
      return path;
    },
    login: async () => {
      // Begin device login and return the code immediately; the poll runs in the background and
      // writes credentials on approval. The next tool call finds the key.
      return await new Promise((resolveCode, reject) => {
        let settled = false;
        deviceLogin({
          clientId: MENDELIO_VOICE_MCP_CLIENT_ID,
          openBrowser: false,
          onCode: ({ userCode, verificationUriComplete }) => {
            settled = true;
            resolveCode({ userCode, verificationUriComplete });
          },
        }).catch((err) => {
          if (!settled) reject(err);
        });
      });
    },
  });

  for (const tool of tools) {
    server.tool(tool.name, tool.description, tool.inputSchema, async (args) => {
      return await tool.handler(args as Record<string, unknown>);
    });
  }

  await server.connect(new StdioServerTransport());
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
