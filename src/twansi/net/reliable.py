from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from twansi.identity import ShardAuthenticator
from twansi.net.messages import canonical_bytes, make_envelope
from twansi.net.transport_udp import UDPTransport


@dataclass
class PendingPacket:
    addr: tuple[str, int]
    raw: bytes
    sent_ts: float
    retries: int


class ReliableMesh:
    def __init__(
        self,
        transport: UDPTransport,
        auth: ShardAuthenticator,
        sender_id: str,
        shard: str,
        epoch: int,
        on_message: Callable[[dict[str, Any], tuple[str, int]], None],
    ):
        self.transport = transport
        self.auth = auth
        self.sender_id = sender_id
        self.shard = shard
        self.epoch = int(epoch)
        self.on_message = on_message

        self.next_seq = 1
        self.highest_remote_seq: dict[str, int] = {}
        self.recv_window: dict[str, int] = {}
        self.pending: dict[int, PendingPacket] = {}
        self.rate_counter: dict[tuple[str, int], list[float]] = {}

    def _rate_allowed(self, addr: tuple[str, int]) -> bool:
        now = time.time()
        bucket = self.rate_counter.setdefault(addr, [])
        bucket[:] = [t for t in bucket if now - t < 1.0]
        if len(bucket) > 120:
            return False
        bucket.append(now)
        return True

    def _ack_bits(self, sender: str) -> tuple[int, int]:
        highest = self.highest_remote_seq.get(sender, 0)
        bits = self.recv_window.get(sender, 0)
        return highest, bits

    def _track_remote_seq(self, sender: str, seq: int) -> None:
        highest = self.highest_remote_seq.get(sender, 0)
        bits = self.recv_window.get(sender, 0)
        if seq > highest:
            shift = min(64, seq - highest)
            bits = ((bits << shift) | 1) & ((1 << 64) - 1)
            highest = seq
        else:
            diff = highest - seq
            if diff < 64:
                bits |= (1 << diff)
        self.highest_remote_seq[sender] = highest
        self.recv_window[sender] = bits

    def _apply_ack(self, ack: int, ack_bits: int) -> None:
        to_remove: list[int] = []
        for seq in self.pending:
            if seq == ack:
                to_remove.append(seq)
                continue
            if seq < ack:
                delta = ack - seq
                if 1 <= delta <= 64 and ((ack_bits >> (delta - 1)) & 1):
                    to_remove.append(seq)
        for seq in to_remove:
            self.pending.pop(seq, None)

    def _wrap(self, envelope: dict[str, Any]) -> bytes:
        signed = dict(envelope)
        mac = self.auth.sign(signed)
        signed["mac"] = mac
        return canonical_bytes(signed)

    def send(self, msg_type: str, payload: dict[str, Any], addr: tuple[str, int], reliable: bool = False) -> int:
        seq = self.next_seq
        self.next_seq += 1
        ack, ack_bits = self._ack_bits(self.sender_id)
        envelope = make_envelope(
            msg_type=msg_type,
            sender=self.sender_id,
            seq=seq,
            ack=ack,
            ack_bits=ack_bits,
            shard=self.shard,
            epoch=self.epoch,
            payload=payload,
            reliable=reliable,
        )
        raw = self._wrap(envelope)
        self.transport.send(raw, addr)
        if reliable:
            self.pending[seq] = PendingPacket(addr=addr, raw=raw, sent_ts=time.time(), retries=0)
        return seq

    def broadcast(self, msg_type: str, payload: dict[str, Any], port: int, reliable: bool = False) -> int:
        seq = self.next_seq
        self.next_seq += 1
        ack, ack_bits = self._ack_bits(self.sender_id)
        envelope = make_envelope(
            msg_type=msg_type,
            sender=self.sender_id,
            seq=seq,
            ack=ack,
            ack_bits=ack_bits,
            shard=self.shard,
            epoch=self.epoch,
            payload=payload,
            reliable=reliable,
        )
        raw = self._wrap(envelope)
        self.transport.broadcast(raw, port)
        if reliable:
            self.pending[seq] = PendingPacket(addr=("255.255.255.255", port), raw=raw, sent_ts=time.time(), retries=0)
        return seq

    async def recv_loop(self) -> None:
        while True:
            data, addr = await self.transport.recv()
            if not self._rate_allowed(addr):
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue

            mac = msg.pop("mac", "")
            if not self.auth.verify(msg, mac):
                continue
            if msg.get("shard") != self.shard:
                continue
            if int(msg.get("epoch", -1)) != self.epoch:
                continue

            sender = str(msg.get("sender", ""))
            seq = int(msg.get("seq", 0))
            ack = int(msg.get("ack", 0))
            ack_bits = int(msg.get("ack_bits", 0))
            self._apply_ack(ack, ack_bits)
            self._track_remote_seq(sender, seq)

            flags = set(msg.get("flags", []))
            if "reliable" in flags:
                # piggyback ack on next messages; explicit ack-only for idle periods.
                ack_env = make_envelope(
                    msg_type="ACK",
                    sender=self.sender_id,
                    seq=self.next_seq,
                    ack=self.highest_remote_seq.get(sender, 0),
                    ack_bits=self.recv_window.get(sender, 0),
                    shard=self.shard,
                    epoch=self.epoch,
                    payload={"for": seq},
                    ack_only=True,
                )
                self.next_seq += 1
                self.transport.send(self._wrap(ack_env), addr)

            self.on_message(msg, addr)

    async def retransmit_loop(self) -> None:
        while True:
            await asyncio.sleep(0.2)
            now = time.time()
            to_remove: list[int] = []
            for seq, packet in list(self.pending.items()):
                if now - packet.sent_ts < 0.5:
                    continue
                if packet.retries >= 6:
                    to_remove.append(seq)
                    continue
                self.transport.send(packet.raw, packet.addr)
                packet.retries += 1
                packet.sent_ts = now
            for seq in to_remove:
                self.pending.pop(seq, None)
