# Operations

Run under tmux for persistent sessions:
```bash
tmux new -s twansi
TWANSI_HOME=/home/arduino/.twansi twansi run
```

Useful env vars:
- `TWANSI_HOME`: profile/data directory
- `TWANSI_DISABLE_UI=1`: disable curses dashboard
- `TWANSI_LOG_LEVEL=debug|info`

## Bootstrap Discovery (WAN-Friendly)

By default nodes will periodically try to fetch seeds from:
- `https://twansi.trentwyatt.com/bootstrap.json`

You can host `bootstrap.json` (example in repo root) and keep it updated with reachable `host:port` seeds.

Optional DNS SRV discovery (requires `dnspython`):
- `_twansi._udp.twansi.trentwyatt.com` SRV records

Environment overrides:
- `TWANSI_BOOTSTRAP_URL` (default `https://twansi.trentwyatt.com/bootstrap.json`)
- `TWANSI_BOOTSTRAP_DOMAIN` (default `twansi.trentwyatt.com`)
