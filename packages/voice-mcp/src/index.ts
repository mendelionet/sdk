#!/usr/bin/env node
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { deviceLogin } from "mendelio-voice";
import { buildTools } from "./core.js";
import { resolveClient } from "./auth.js";
import { record } from "./record.js";

/**
 * The stdio MCP server: `npx -y mendelio-voice-mcp`. Registers the local tool set (with microphone
 * capture and device login) and speaks MCP over stdin/stdout. The key is resolved fresh on every
 * tool call, so a login that completes in the background is picked up by the next call.
 */
async function main(): Promise<void> {
  const server = new McpServer({ name: "mendelio-voice", version: "0.1.0" });

  const tools = buildTools({
    mode: "local",
    client: () => resolveClient(),
    record: (seconds) => record(seconds),
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
      const result = await tool.handler(args as Record<string, unknown>);
      // The SDK's CallToolResult carries an index signature; a fresh object literal satisfies it.
      return { content: result.content };
    });
  }

  await server.connect(new StdioServerTransport());
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
