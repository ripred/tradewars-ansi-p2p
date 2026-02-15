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
  - action points (AP) with time-based regeneration and action costs
  - movement simulation (for radar animation)
  - mining + economy ticks
  - station markets with per-sector stock and prices (buy/sell ore/gas/crystal)
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
- `q` quit
- `h` toggle help text
- `+` / `-` radar zoom in/out
- `m` mine burst (AP cost)
- `a` attack random target (AP cost)
- `s` scan/ping peers
- `i` invite a peer to your alliance (AP cost)
- `d` offline digest summary
- `b` buy ore at current station (AP cost)
- `n` sell ore at current station (AP cost)
- `u` upgrade next available tech tier (AP cost)
- `j` jump to another sector (cheaper if it’s a direct warp; AP+gas cost)
- `g` upgrade sector defenses (only if you own the sector; AP+resources)

## Optional Agent Interface
When a node is running, a local TCP JSON-lines API is exposed on:
- `127.0.0.1:<listen_port + 100>`

Requests:
- `{"cmd":"observe"}`
- `{"cmd":"digest"}`
- `{"cmd":"act","action":"mine|attack|scan|invite|buy|sell|upgrade|jump|defend|observe","args":{...}}`

Example actions:
- Buy gas: `{"cmd":"act","action":"buy","args":{"resource":"gas","qty":5}}`
- Sell ore: `{"cmd":"act","action":"sell","args":{"resource":"ore","qty":10}}`
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
