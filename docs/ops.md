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
