# mendelio-voice-mcp

MCP server for **Hezky česky** and the
[Mendelio Voice API](https://voice.mendelio.net/developers). Generate playable speech with more
than 190 unique voices—including natural speakers, creatures, dragons, robots, other characters,
and personal voices—and create a personal voice from an authorized recording in Claude, Codex,
Cursor, or any MCP client.

The public Czech brand is **Hezky česky**. The technical platform, API, package, and server identity
remain **Mendelio Voice**. Prompts naming either product use the same tools and release.

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

Users who know the service as Hezky česky may choose that local connection name without installing
another package:

```toml
[mcp_servers.hezky-cesky]
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

For example: “Use Hezky česky MCP to generate this sentence with an interesting dragon voice and
play it immediately.” The same request continues to work when it names Mendelio Voice MCP.

MIT. No telemetry. Your API key is never printed or logged.
