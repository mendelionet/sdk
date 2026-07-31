# Hezky česky MCP

<!-- release-stage:start -->
> **Public Preview.** The catalogue and one short browser-verified demo work without an account. Account data and full speech generation require an API key or OAuth login; full generation uses paid audio credit.
<!-- release-stage:end -->

MCP server for **Hezky česky**. Generate playable speech with more
than 190 unique voices—including natural speakers, creatures, dragons, robots, other characters,
and personal voices—and create a personal voice from an authorized recording in Claude, Codex,
Cursor, or any MCP client.

The technical package and API identifiers remain under the `mendelio-voice` namespace.

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

Call `voice_try_speech` for a short anonymous sample; it opens a normal browser for Turnstile and
prints the same URL for headless terminals. For account tools, call `voice_login` once or set
`MENDELIO_VOICE_API_KEY`.

## Remote (no install)

In claude.ai → Connectors, add `https://api.mendelio.net/mcp`. OAuth approval is one click.

## Tools

`voice_try_speech`, `voice_generate_speech`, `voice_list_voices`, `voice_get_generation`, `voice_get_balance`,
`voice_list_reference_prompts`, `voice_clone_voice`, `voice_record_and_clone` (local mic capture via
sox/ffmpeg), `voice_login`.

For example: “Use Hezky česky MCP to generate this sentence with an interesting dragon voice and
play it immediately.”

MIT. No telemetry. Your API key is never printed or logged.
