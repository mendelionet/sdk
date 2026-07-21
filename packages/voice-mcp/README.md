# mendelio-voice-mcp

MCP server for the [Mendelio Voice API](https://voice.mendelio.net/developers) — generate speech and
clone voices from Claude, Codex, Cursor and any MCP client.

## Install

**Claude Code**
```bash
claude mcp add mendelio-voice -- npx -y mendelio-voice-mcp
```

**Codex** (`~/.codex/config.toml`)
```toml
[mcp_servers.mendelio-voice]
command = "npx"
args = ["-y", "mendelio-voice-mcp"]
```

**Claude Desktop** (`claude_desktop_config.json` → `mcpServers`)
```json
{ "mendelio-voice": { "command": "npx", "args": ["-y", "mendelio-voice-mcp"] } }
```

Then call `voice_login` once (opens a browser, one click). Or set `MENDELIO_VOICE_API_KEY`.

## Remote (no install)

In claude.ai → Connectors, add `https://api.mendelio.net/mcp`. OAuth approval is one click.

## Tools

`voice_generate_speech`, `voice_list_voices`, `voice_get_generation`, `voice_get_balance`,
`voice_list_reference_prompts`, `voice_clone_voice`, `voice_record_and_clone` (local mic capture via
sox/ffmpeg), `voice_login`.

MIT. No telemetry. Your API key is never printed or logged.
