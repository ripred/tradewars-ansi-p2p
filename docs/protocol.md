# Protocol

Transport: UDP + lightweight reliability layer.

## Envelope
JSON object (UTF-8), fields:
- `v`: protocol version
- `type`: message type
- `sender`: sender id
- `seq`: sender monotonic sequence
- `ack`: highest contiguous remote seq seen
- `ack_bits`: bitmap of previous 64 packet receipts
- `ts`: unix ms timestamp
- `shard`: shard id
- `flags`: array (`reliable`, `ack_only`)
- `payload`: message-specific object
- `mac`: HMAC-SHA256 over canonical envelope bytes excluding `mac`

## Message types
- `HELLO`, `PEER_LIST`, `PING`, `PONG`
- `EVENT_BATCH`
- `SNAPSHOT_HASH`, `SNAPSHOT_REQ`, `SNAPSHOT_RES`
- `ALLIANCE_INVITE`, `ALLIANCE_ACCEPT`
- `CHAT`

## Security
Current runtime uses shard-level HMAC authentication due local crypto constraints.
Interface is designed to be upgraded to Ed25519 without changing message semantics.
