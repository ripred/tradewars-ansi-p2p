# twansi

`twansi` is a Tradewars-inspired ANSI terminal multiplayer game with a serverless peer mesh.

## Features
- UDP peer mesh with gossip discovery and retransmit reliability
- Persistent SQLite world state + event log
- Offline catch-up digest on login
- Alliances, sectors, economy, and doctrine-based combat
- Fast curses dashboard with radar and live metrics
- Optional local JSON agent API for bots/LLMs (`127.0.0.1:<listen_port+100>`)

## Quickstart
```bash
cd /home/arduino/tradewars-ansi-p2p
python3 -m venv .venv
. .venv/bin/activate
pip install -e .

# initialize profile
TWANSI_HOME=$PWD/.data twansi init --nick captain --listen 0.0.0.0:39000 --shard alpha

# run node
TWANSI_HOME=$PWD/.data twansi run
```

In another shell (same host), run another profile on a different port:
```bash
TWANSI_HOME=$PWD/.data2 twansi init --nick rival --listen 0.0.0.0:39001 --shard alpha --seed 127.0.0.1:39000
TWANSI_HOME=$PWD/.data2 twansi run
```

Notes:
- Peers must share the same `--shard` and `--shard-key` (if provided).
- If `--shard-key` is omitted, a deterministic key is derived from shard name.

Headless mode (no curses UI):
```bash
TWANSI_HOME=$PWD/.data TWANSI_DISABLE_UI=1 twansi run
```

## Optional Agent Interface
When a node is running, a local TCP JSON-lines API is exposed on `127.0.0.1:<listen_port+100>`.

Requests:
- `{"cmd":"observe"}`
- `{"cmd":"act","action":"mine|attack|scan|invite|digest|observe"}`
- `{"cmd":"digest"}`
- `{"cmd":"ack"}`

Responses:
- `{"ok":true,"result":...}`
- `{"ok":false,"error":"..."}`

Run included bot harness:
```bash
twansi bot --host 127.0.0.1 --port 39100 --seconds 30
```

## Controls
- `q` quit
- `m` mine burst
- `a` random attack event
- `s` scan peers
- `i` invite random player to alliance
- `d` print digest summary to event panel
- `h` toggle help panel
