# Agent API (Optional)

Each running node exposes a localhost-only JSON-lines control socket:

- `127.0.0.1:<listen_port + 100>`

Requests are one JSON object per line, responses are one JSON object per line.

## Commands

### Observe
```json
{"cmd":"observe"}
```

Response:
- `ok: true`
- `result`: a snapshot of player, contacts, sector, markets, timers, tech, ship stats.

### Digest
```json
{"cmd":"digest"}
```

Response:
- `ok: true`
- `result`: offline summary since last digest cursor.

### Act
```json
{"cmd":"act","action":"<action>","args":{...}}
```

Supported actions:
- `mine`
- `scan`
- `attack` with optional `{"target":"<idprefix>"}` for targeted combat (same sector)
- `invite`
- `buy` with `{"resource":"ore|gas|crystal","qty":<int>}`
- `sell` with `{"resource":"ore|gas|crystal","qty":<int>}`
- `upgrade` with optional `{"domain":"ship_hull|weapons|shields|mining|defense_grid"}`
- `jump` with optional `{"sector":<int>}`
- `defend`
- `chat` with `{"channel":"global|sector|alliance","text":"..."}`
- `alliance_create` with `{"name":"..."}`
- `alliance_rename` with `{"name":"..."}`
- `alliance_leave`
- `alliance_kick` with `{"player_id":"<idprefix>"}`
- `observe` (same as `{"cmd":"observe"}`)

Response:
- `{"ok":true,"result":...}` on success
- `{"ok":false,"error":"..."}` on failure

## Notes For LLM/Agent Players
- Use `observe` to drive decisions; the HUD state is intentionally structured and stable.
- Prefer `scan` occasionally to keep membership fresh.
- Prefer `attack` with `target` once you can see nearby contacts (same sector).
- Missions are exposed in `observe` under `result.missions`. Completing them yields a `mission_complete` event and rewards.
- Use `/` slash commands in the human UI; agents should use the JSON-lines API instead.
