# twansi

`twansi` is a Tradewars-inspired ANSI terminal multiplayer space game with a serverless peer mesh (no central game server). It runs in a terminal, uses a curses dashboard, and supports optional headless agent control.

## What’s Implemented
- ANSI dashboard (20 FPS target) with radar, live events, metrics, market/tech summaries
- P2P UDP mesh with:
  - reliability layer (ACK + retransmit)
  - epoch + HMAC authentication
  - policy-enforced min/max protocol version
  - gossip-style event fanout with hop limit
- Bootstrap discovery:
  - LAN UDP broadcast `HELLO`
  - manual seeds (`--seed host:port`)
  - HTTPS bootstrap seeds (default `https://twansi.trentwyatt.com/bootstrap.json`)
  - optional DNS SRV `_twansi._udp.<domain>` if `dnspython` is installed
- Persistence:
  - SQLite world state + append-only event log
  - offline digest cursor (catch-up summary)
- Core gameplay:
  - sectors with warp graph (ring + extra links)
  - deterministic world generation per `shard` + `protocol_epoch` (topology/ports match across nodes)
  - action points (AP) with time-based regeneration and action costs
  - movement simulation (for radar animation)
  - mining + economy ticks
  - station markets with per-sector stock and prices (buy/sell ore/gas/crystal)
  - ports (Tradewars-style B/S classes) with bid/ask pricing; port inventory deltas converge across the mesh
  - tech tree (tiered): `ship_hull`, `weapons`, `shields`, `mining`, `defense_grid`
  - shields + shield regeneration
  - sector ownership + sector defenses (owners can upgrade defense level)
  - combat v2 (doctrine triangle + weapon/defense/shield + sector defense bonus)
- Optional local agent API (JSON-lines over TCP, localhost only)

## Install (Board / Dev)
```bash
cd /home/arduino/tradewars-ansi-p2p
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## Run One Node
```bash
cd /home/arduino/tradewars-ansi-p2p

TWANSI_HOME=$PWD/.data \
  twansi init --nick captain --listen 0.0.0.0:39000 --shard alpha

TWANSI_HOME=$PWD/.data \
  twansi run
```

World consistency note:
- The galaxy (sectors/warps/ports) is generated deterministically from `--shard` and `twansi_policy.json` `protocol_epoch`.
- If you previously ran older builds that created a different map, delete your `TWANSI_HOME` directory and re-`init` to avoid mismatches.

## Run Two Nodes (Same Host)
Terminal 1:
```bash
cd /home/arduino/tradewars-ansi-p2p
TWANSI_HOME=$PWD/.p1 twansi init --nick alpha --listen 0.0.0.0:39010 --shard alpha --seed 127.0.0.1:39011
TWANSI_HOME=$PWD/.p1 twansi run
```

Terminal 2:
```bash
cd /home/arduino/tradewars-ansi-p2p
TWANSI_HOME=$PWD/.p2 twansi init --nick beta --listen 0.0.0.0:39011 --shard alpha --seed 127.0.0.1:39010
TWANSI_HOME=$PWD/.p2 twansi run
```

## Headless Mode
```bash
TWANSI_HOME=$PWD/.data TWANSI_DISABLE_UI=1 twansi run
```

## Controls (Dashboard)
- `1` HUD, `2` map, `3` players, `4` trade, `5` alliance, `6` chat
- `t` open global chat input, `l` open local (sector) chat input, `/` open command input
- `q` quit
- `h` toggle help text
- `+` / `-` radar zoom in/out
- `m` mine burst (AP cost)
- `a` attack random target (AP cost) or `/attack <idprefix>` to target
- `s` scan/ping peers
- `i` invite a peer to your alliance (AP cost)
- `d` offline digest summary
- `b` / `n` buy/sell ore (AP cost)
- `f` / `r` buy/sell gas (AP cost)
- `c` / `v` buy/sell crystal (AP cost)
- `B/N/F/R/C/V` open a prefilled buy/sell command you can edit (for custom quantities)
- `u` upgrade next available tech tier (AP cost)
- `j` jump to another sector (cheaper if it’s a direct warp; AP+gas cost)
- `g` upgrade sector defenses (only if you own the sector; AP+resources)

Missions:
- Shown on the map screen (`2`). They rotate every ~5 minutes (deterministic per shard/epoch).
- `survey`: scan (`s`) in the mission sector
- `raid`: win a battle in the mission sector
- `supply`: sell cargo in the mission sector

Slash commands:
- `/say <text>` global chat
- `/local <text>` sector-local chat
- `/attack <idprefix>` targeted combat (same sector)
- `/jump <sector>`
- `/buy <res> <qty>`, `/sell <res> <qty>`
- `/all create <name>`, `/all rename <name>`, `/all leave`, `/all kick <idprefix>`
- `/help`

The metrics panel already surfaces shared market prices plus station and port totals while the help overlay (`h`) reiterates these keys. `s` logs warp neighbors, current sector ownership/defense, and whether a port exists so you can spot trade targets before jumping. Trades triggered with `b/n`, `f/r`, or `c/v` are routed through the local port when one is present, otherwise they fall back to the per-sector station market highlighted on the dashboard.

## Deterministic Galaxy
- A shared shard name plus the `protocol_epoch` from `twansi_policy.json` seed every nodeʼs galaxy topology and ports via `_seed64("twansi-map", shard, epoch, sectors)` so sectors, warps, and port placements converge without a central authority.
- Warp rails always form a base ring (`ensure_map` adds `s -> s+1` plus extra random links seeded with the same deterministic RNG) and `store.configure_world` applies the shard/epoch before any topology or market state writes.
- Ports use `_seed64("twansi-port-class"...)` to pick a Tradewars-style `B/S` class and `_seed64("twansi-port-stock"...)` for balanced inventory, while `drift_market` and `_det_shift` keep the global market prices in sync by advancing a per-minute slot hash tied to the shard, epoch, and resource.
- If you change `--shard` or bump `protocol_epoch`, wipe your `TWANSI_HOME` and re-run `twansi init` so every node rebuilds the same deterministic world and market.

## Ports & Market Behavior
- Ports encode a three-letter class such as `BBS` or `SSB`, where each `B`/`S` letter determines whether the port prefers buying or selling ore, gas, or crystal. `port_info` uses the class, current inventory, and the shared market base price to calculate bid/ask spreads that favor either selling into the port or buying from it.
- When you trade with `game.node` commands, the code prefers a local port (if present) before falling back to the station market. Port trades emit buy/sell events that adjust the shared per-sector `port_inventory`, letting every peer converge on the same supply/demand deltas.
- Station markets (`station_market`) compute prices from the shared base market plus a sector-specific modifier (richness/danger and stock level) and also track inventory deterministically via `_seed64("twansi-station-stock"...)`. Their fees are slightly higher than ports to keep the flashy ports enticing.
- Market drift (`drift_market`) updates the in-memory market price every resource tick and writes it through `store.update_market_price`, so even headless nodes (or scale smoke) experience the same minute-by-minute price swings.

## Optional Agent Interface
When a node is running, a local TCP JSON-lines API is exposed on:
- `127.0.0.1:<listen_port + 100>`

Requests:
- `{"cmd":"observe"}`
- `{"cmd":"digest"}`
- `{"cmd":"act","action":"mine|attack|scan|invite|buy|sell|upgrade|jump|defend|chat|alliance_create|alliance_rename|alliance_leave|alliance_kick|observe","args":{...}}`

Example actions:
- Buy gas: `{"cmd":"act","action":"buy","args":{"resource":"gas","qty":5}}`
- Sell ore: `{"cmd":"act","action":"sell","args":{"resource":"ore","qty":10}}`
- Targeted attack: `{"cmd":"act","action":"attack","args":{"target":"deadbeef"}}`
- Chat: `{"cmd":"act","action":"chat","args":{"channel":"global","text":"hi"}}`
- Upgrade a specific domain: `{"cmd":"act","action":"upgrade","args":{"domain":"weapons"}}`
- Jump to a sector: `{"cmd":"act","action":"jump","args":{"sector":7}}`
- Upgrade defenses: `{"cmd":"act","action":"defend"}`

Responses:
- `{"ok":true,"result":...}`
- `{"ok":false,"error":"..."}`

Run included bot harness (talks to agent API):
```bash
twansi bot --host 127.0.0.1 --port 39100 --seconds 30
```

## Policy Hardening (Repo-Committed)
The game reads `twansi_policy.json` from repo root at runtime.

Key fields:
- `min_protocol_version`, `max_protocol_version`: receivers drop packets outside this range
- `protocol_epoch`: receivers drop packets with a different epoch
- `reliable_event_types`: which events are sent reliably
- `max_event_hops`: limits gossip amplification

Important note:
- Epoch+HMAC prevents “casual bypass” only if you provide a private secret. A purely public shard cannot prevent malicious clients from reimplementing the protocol.

Optional private salt:
- Set `TWANSI_SHARD_SECRET` on nodes you control. It is mixed into the shard HMAC key derivation.

## Discovery / Finding Other Players
Default HTTPS bootstrap:
- `TWANSI_BOOTSTRAP_URL` defaults to `https://twansi.trentwyatt.com/bootstrap.json`

DNS SRV (optional):
- Create SRV records for `_twansi._udp.twansi.trentwyatt.com`
- Requires `dnspython` installed for clients to use SRV discovery

Manual:
- Use `--seed host:port` on `twansi init`

## Test / Verify
```bash
./bin/run-tests
./bin/continuous-smoke 75
./bin/scale-smoke 8 60 39600
```

## Demos

Two players:
```bash
./bin/demo-federation-tmux twansi-demo
tmux attach -t twansi-demo
```

Four players + 4 bots:
```bash
./bin/demo-4p twansi-4p
tmux attach -t twansi-4p
```

Agent API docs:
- `docs/agent_api.md`
