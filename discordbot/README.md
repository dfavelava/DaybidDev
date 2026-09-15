## discordbot

Discord bot for the Daybid connectome memory service, built on
[discord.py](https://discordpy.readthedocs.io/). It talks to the Go backend
via `ConnectomeClient`, a minimal async HTTP client that hits the backend's
`/api/connectome` routes directly (`httpx`, no MCP dependency) - see [issue
#41](https://github.com/dfavelava/DaybidDev/issues/41).

### Identity

Each Discord user is mapped to a Connectome entity id deterministically:
`discord-<user_id>` (see `discord_entity_id` in
[`identity.py`](src/discordbot/identity.py)). There's no entity-lookup tool
yet (Phase 2), so a deterministic id needs no separate lookup step.

### Commands

- `/remember <content>` - stores `content` as a memory attributed to the
  calling user's entity id.
- `/play-character <name>` - resolve-or-create a PC entity
  (`ent_<slugified name>.json`, `kind: "character"`) and record that the
  calling player plays it (see [`characters.py`](src/discordbot/characters.py)
  for `handle_play_character`). Refuses if another player already owns a PC
  with that name; re-running it for a PC the caller already plays is a
  no-op. If the caller already plays a *different* PC, that PC's `plays`
  relationship is superseded by the new one (retirement) via the
  already-shipped `supersede_relationship` backend endpoint - no new backend
  capability needed. Party `member_of` does **not** carry over to the new PC
  on retirement (a design decision, not an oversight - see the module
  docstring): run `/join-party` again for the new PC if it needs one.

  There's no entity-lookup tool yet (Phase 2), so the bot can't ask the
  backend "which memory currently asserts this player's `plays`
  relationship?" when it's time to retire a PC. Instead it caches the
  current PC id and that memory's key itself, in-process
  (`PlayerState`) - this state does not survive a bot restart.

### Run the bot

```bash
uv sync
uv run discordbot
```

Requires `DISCORD_BOT_TOKEN` (see below) and a reachable Connectome backend.

### Why a standalone HTTP client instead of reusing `daybidmcp.server`

`daybidmcp.server`'s tool functions could be imported and called in-process
instead - same repo, same language, and it would reuse that module's
`format_memory`/entity-merge logic rather than re-deriving it. This package
takes the other option instead: a fresh client independent of `daybidmcp`,
hitting `/api/connectome/...` directly. That keeps the bot's only dependency
on the memory service being the same HTTP API any other client would use,
rather than an in-process import of the MCP server package.

### Environment

Copy the example env file and set the API key:

```bash
cp .env.example .env
```

```dotenv
CONNECTOME_API_BASE_URL=http://localhost:8080/api/connectome
CONNECTOME_API_KEY=your-api-key
DISCORD_BOT_TOKEN=your-discord-bot-token
DISCORD_GUILD_ID=
```

Set `CONNECTOME_API_KEY` to the same value as `apikey` in `backend/.env`.
`ConnectomeClient` also falls back to `DAYBID_API_KEY` or `apikey` if
`CONNECTOME_API_KEY` isn't set, so it can share an env file with `daybidMCP`
in local dev.

`DISCORD_BOT_TOKEN` comes from your bot's application in the [Discord
Developer Portal](https://discord.com/developers/applications). Set
`DISCORD_GUILD_ID` to a test server's id to sync slash commands there
instantly during development; leave it unset in production so commands sync
globally (which can take up to an hour to propagate).

### Run the tests

```bash
uv sync
uv run pytest
```

### `ConnectomeClient`

```python
from discordbot import ConnectomeClient

client = ConnectomeClient()
await client.remember("David prefers tea over coffee.", entities=["david"])
await client.recall("what does david drink")
```

Covers the routes needed to write and search memory:

- `POST /api/connectome/memory/` (`remember`, `create_entity`)
- `POST /api/connectome/memory/search` (`recall`)
- `GET /api/connectome/memory/?key=...` (`get_memory`, `get_entity`)
- `GET /api/connectome/memory/list` (`browse_all`)
- `DELETE /api/connectome/memory/` (`forget`)
- `PATCH /api/connectome/memory/relationship` (`supersede_relationship`)

`remember` writes a plain memory document (content + entity ids +
relationships, via `format_relationship`); unlike `daybidmcp.server`'s
`remember`, it does not merge onto existing entity records or maintain
`member_of` - `create_entity` writes a bare entity record outright, with no
read-modify-write merge of its own. Callers that need read-modify-write
semantics should `get_entity` first, as `handle_play_character` does to
check PC ownership before deciding whether to create or reuse one.
