from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from twansi.config import Profile, load_profile, parse_listen, save_profile, twansi_home
from twansi.game.alliances import create_alliance, join_alliance, player_alliance
from twansi.game.mapgen import ensure_map
from twansi.game.market import drift_market, market_snapshot
from twansi.game.rules import RESOURCE_TICK_SECONDS, STRATEGIC_TICK_SECONDS
from twansi.game.tech import TECH_DOMAINS, can_upgrade, tech_tree_spec, tier_cost, upgrade_tech
from twansi.game.tick import GameEngine
from twansi.game.ship import ship_stats
from twansi.identity import Identity, ShardAuthenticator
from twansi.net.membership import Membership
from twansi.net.netsplit import NetsplitTracker
from twansi.net.reliable import ReliableMesh
from twansi.net.transport_udp import UDPTransport
from twansi.net.bootstrap import dns_srv_seeds, fetch_bootstrap, merge_seeds, read_cached, write_cached
from twansi.policy import load_policy, derive_shard_key
from twansi.sim.bots import main as bot_main
from twansi.state.digest import build_offline_digest
from twansi.state.eventlog import compact_event, event_id
from twansi.state.snapshot import snapshot_hash
from twansi.state.store_sqlite import Store
from twansi.ui.terminal import Dashboard


@dataclass
class RuntimeState:
    shutdown: bool = False
    tick_ms: float = 0.0
    events_seen: int = 0


class GameNode:
    def __init__(self, profile: Profile):
        self.profile = profile
        self.policy = load_policy()
        self.print_logs = os.environ.get("TWANSI_LOG_STDOUT", "0") == "1"
        self.identity = Identity(profile.secret)
        shard_key = profile.shard_key or derive_shard_key(profile.shard, self.policy.protocol_epoch)
        self.shard_auth = ShardAuthenticator(shard_key)
        self.store = Store(profile.db_path)
        ensure_map(self.store, sectors=96)
        self.store.ensure_player(self.identity.sender_id, profile.nick, doctrine=random.choice(["assault", "siege", "defense"]))

        self.engine = GameEngine(self.store)
        self.membership = Membership()
        self.netsplit = NetsplitTracker()

        self.runtime = RuntimeState()
        self.transport = UDPTransport(profile.listen_host, profile.listen_port)
        self.mesh = ReliableMesh(
            transport=self.transport,
            auth=self.shard_auth,
            sender_id=self.identity.sender_id,
            shard=profile.shard,
            epoch=self.policy.protocol_epoch,
            on_message=self.on_net_message,
        )

        self.local_event_counter = 0
        self.event_panel: list[str] = []
        self.panel_lock = threading.Lock()
        self.command_queue: Queue[str] = Queue()
        self.state_lock = threading.Lock()
        self.last_resource_tick = time.time()
        self.last_strategic_tick = time.time()
        self.last_announce_second = -1
        self.last_snapshot_second = -1
        self.last_bootstrap_ts = 0.0
        self.agent_server_port = int(os.environ.get("TWANSI_AGENT_PORT", str(profile.listen_port + 100)))
        self.radar_zoom = 1.0
        self.server: asyncio.AbstractServer | None = None

    def log_event(self, text: str) -> None:
        if self.print_logs:
            print(text, flush=True)
        with self.panel_lock:
            self.event_panel.append(text)
            if len(self.event_panel) > 500:
                self.event_panel = self.event_panel[-500:]

    def drain_new_events(self) -> list[str]:
        with self.panel_lock:
            out = list(self.event_panel)
            self.event_panel.clear()
            return out

    def public_state(self) -> dict[str, Any]:
        player = self.store.get_player(self.identity.sender_id) or {}
        healthy = self.membership.healthy()
        self.netsplit.tick(len(healthy))
        if player:
            self.store.regen_ap(self.identity.sender_id)
            player = self.store.get_player(self.identity.sender_id) or player
        tech_levels = self.store.get_tech_levels(self.identity.sender_id)
        contacts: list[dict[str, Any]] = []
        for p in healthy:
            rp = self.store.get_player(p.peer_id)
            if not rp:
                continue
            contacts.append(
                {
                    "id": p.peer_id,
                    "nick": rp.get("nick", p.nick),
                    "x": float(rp.get("pos_x", 0.0)),
                    "y": float(rp.get("pos_y", 0.0)),
                }
            )
        return {
            "player": player,
            "contacts": contacts,
            "market": market_snapshot(self.store),
            "station": self.store.station_market(int(player.get("sector", 1))) if player else {},
            "nav": {"warps": self.store.list_warps(int(player.get("sector", 1))) if player else []},
            "tech": {
                "levels": tech_levels,
                "tree": self._tech_tree_view(tech_levels),
            },
            "ship": ship_stats(player, tech_levels) if player else {},
            "metrics": {
                "peer_count": len(healthy),
                "events_seen": self.runtime.events_seen,
                "pending_packets": len(self.mesh.pending),
                "radar_zoom": self.radar_zoom,
                "netsplit": self.netsplit.split_active,
                "merge_count": self.netsplit.merge_count,
                "tick_ms": self.runtime.tick_ms,
            },
            "new_events": self.drain_new_events(),
        }

    def _tech_tree_view(self, levels: dict[str, int]) -> dict[str, dict[str, Any]]:
        spec = tech_tree_spec()
        out: dict[str, dict[str, Any]] = {}
        for domain, cfg in spec.items():
            cur = int(levels.get(domain, 0))
            next_tier = cur + 1
            allowed, reason = can_upgrade(levels, domain, next_tier)
            out[domain] = {
                "name": cfg.get("name", domain),
                "tier": cur,
                "max_tier": int(cfg.get("max_tier", 8)),
                "requires": cfg.get("requires", {}),
                "next_cost": tier_cost(cur) if allowed else None,
                "upgrade_ready": allowed,
                "blocked_reason": "" if allowed else reason,
            }
        return out

    def enqueue_command(self, cmd: str) -> None:
        self.command_queue.put(cmd)

    def _fanout_events(self, events: list[dict[str, Any]], exclude_peer_ids: set[str] | None = None, reliable: bool = True) -> None:
        peers = [p for p in self.membership.healthy(max_age=240) if (exclude_peer_ids is None or p.peer_id not in exclude_peer_ids)]
        if not peers:
            self.mesh.broadcast("EVENT_BATCH", {"events": events}, port=self.profile.listen_port, reliable=reliable)
            return
        fanout = min(len(peers), max(3, int(math.sqrt(len(peers))) + 1))
        for p in random.sample(peers, fanout):
            self.mesh.send("EVENT_BATCH", {"events": events}, (p.host, p.port), reliable=reliable)

    def _emit_event(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.local_event_counter += 1
        eid = event_id(self.identity.sender_id, self.local_event_counter, payload)
        self.store.record_event(self.identity.sender_id, event_type, payload, eid)
        ce = compact_event(event_type, payload, self.identity.sender_id, eid)
        ce["hops"] = 0
        # Avoid reliable spam for high-frequency/low-stakes updates.
        reliable = event_type in set(self.policy.reliable_event_types)
        self._fanout_events([ce], reliable=reliable)
        self.log_event(f"{event_type}: {payload}")
        return ce

    def _apply_remote_event(self, ev: dict[str, Any]) -> None:
        et = str(ev.get("event_type", ""))
        payload = dict(ev.get("payload", {}))
        sender = str(ev.get("sender", ""))
        eid = str(ev.get("event_id", ""))
        row_id = self.store.record_event(sender, et, payload, eid)
        if row_id == 0:
            return

        pid = str(payload.get("player_id", ""))
        if et == "resource_tick" and pid:
            self.store.ensure_player(pid, payload.get("nick", pid[:8]))
            self.store.update_player_resources(pid, int(payload.get("credits", 0)), int(payload.get("ore", 0)), int(payload.get("gas", 0)), int(payload.get("crystal", 0)))
        elif et == "mine_burst" and pid:
            self.store.ensure_player(pid, payload.get("nick", pid[:8]))
            self.store.update_player_resources(pid, int(payload.get("credits", 0)), int(payload.get("ore", 0)), int(payload.get("gas", 0)), int(payload.get("crystal", 0)))
        elif et == "repair_tick" and pid:
            p = self.store.get_player(pid)
            if p:
                self.store.update_player_resources(pid, 0, 0, 0, 0, hp=int(payload.get("hp_after", p["hp"])))
        elif et == "movement" and pid:
            self.store.ensure_player(pid, payload.get("nick", pid[:8]))
            self.store.set_player_motion(
                pid,
                float(payload.get("x", 0.0)),
                float(payload.get("y", 0.0)),
                float(payload.get("vx", 0.0)),
                float(payload.get("vy", 0.0)),
            )
        elif et == "battle":
            atk = str(payload.get("attacker", ""))
            dfn = str(payload.get("defender", ""))
            if atk:
                self.store.ensure_player(atk, f"{atk[:8]}")
                self.store.update_player_resources(atk, 0, 0, 0, 0, hp=int(payload.get("attacker_hp", 100)))
            if dfn:
                self.store.ensure_player(dfn, f"{dfn[:8]}")
                self.store.update_player_resources(dfn, 0, 0, 0, 0, hp=int(payload.get("defender_hp", 100)))
            self.store.record_battle(
                atk,
                dfn,
                str(payload.get("winner", "")),
                int(payload.get("damage_attacker", 0)),
                int(payload.get("damage_defender", 0)),
                int(payload.get("sector_id", 1)),
                str(payload.get("summary", "")),
            )
            winner = str(payload.get("winner", ""))
            if winner == atk:
                self.store.claim_sector(int(payload.get("sector_id", 1)), winner)
        elif et == "alliance_join":
            aid = str(payload.get("alliance_id", ""))
            if aid and pid:
                join_alliance(self.store, aid, pid)
        elif et == "market_trade" and pid:
            self.store.ensure_player(pid, payload.get("nick", pid[:8]))
            resource = str(payload.get("resource", "ore"))
            qty = int(payload.get("qty", 0))
            side = str(payload.get("side", "buy"))
            credits_delta = int(payload.get("credits_delta", 0))
            ore = gas = crystal = 0
            sign = 1 if side == "buy" else -1
            if resource == "ore":
                ore = sign * qty
            elif resource == "gas":
                gas = sign * qty
            elif resource == "crystal":
                crystal = sign * qty
            self.store.update_player_resources(pid, credits_delta, ore, gas, crystal)
        elif et == "tech_upgrade" and pid:
            self.store.ensure_player(pid, payload.get("nick", pid[:8]))
            domain = str(payload.get("domain", "ship_hull"))
            tier = int(payload.get("to_tier", 0))
            self.store.set_tech_level(pid, domain, tier)
        elif et == "jump" and pid:
            self.store.ensure_player(pid, payload.get("nick", pid[:8]))
            to_sector = int(payload.get("to", 1))
            self.store.set_player_sector(pid, to_sector)
            self.store.set_player_motion(pid, 0.0, 0.0, 0.0, 0.0)

        self.log_event(f"remote/{et}: {payload}")

        hops = int(ev.get("hops", 0))
        sender = str(ev.get("sender", ""))
        if hops < int(self.policy.max_event_hops):
            fwd = dict(ev)
            fwd["hops"] = hops + 1
            reliable = str(fwd.get("event_type", "")) in set(self.policy.reliable_event_types)
            self._fanout_events([fwd], exclude_peer_ids={sender}, reliable=reliable)

    def on_net_message(self, msg: dict[str, Any], addr: tuple[str, int]) -> None:
        mtype = str(msg.get("type", ""))
        payload = dict(msg.get("payload", {}))
        sender = str(msg.get("sender", ""))
        v = int(msg.get("v", 0))
        epoch = int(msg.get("epoch", -1))

        # Enforce repo policy: protocol version and current epoch.
        if v < self.policy.min_protocol_version or v > self.policy.max_protocol_version:
            return
        if epoch != self.policy.protocol_epoch:
            return

        if sender == self.identity.sender_id:
            return

        if mtype == "HELLO":
            nick = str(payload.get("nick", sender[:8]))
            port = int(payload.get("port", addr[1]))
            self.membership.seen(sender, addr[0], port, self.profile.shard, nick)
            self.netsplit.on_peer_seen()
            self.store.ensure_player(sender, nick)
            self.store.set_player_motion(
                sender,
                float(payload.get("x", 0.0)),
                float(payload.get("y", 0.0)),
                float(payload.get("vx", 0.0)),
                float(payload.get("vy", 0.0)),
            )
            peer_dump = [
                {"id": p.peer_id, "host": p.host, "port": p.port, "nick": p.nick}
                for p in self.membership.healthy()
            ]
            self.mesh.send("PEER_LIST", {"peers": peer_dump}, (addr[0], port), reliable=False)
            self.log_event(f"peer online: {nick}@{addr[0]}:{port}")
            return

        if mtype == "PEER_LIST":
            for peer in payload.get("peers", []):
                pid = str(peer.get("id", ""))
                if not pid or pid == self.identity.sender_id:
                    continue
                host = str(peer.get("host", ""))
                port = int(peer.get("port", 0))
                nick = str(peer.get("nick", pid[:8]))
                if host and port:
                    self.membership.seen(pid, host, port, self.profile.shard, nick)
            return

        if mtype == "PING":
            self.mesh.send("PONG", {"ts": payload.get("ts", 0)}, addr, reliable=False)
            return

        if mtype == "PONG":
            self.netsplit.on_peer_seen()
            return

        if mtype == "EVENT_BATCH":
            events = payload.get("events", [])
            for ev in events:
                self.runtime.events_seen += 1
                self._apply_remote_event(ev)
            return

        if mtype == "ALLIANCE_INVITE":
            target = str(payload.get("target", ""))
            aid = str(payload.get("alliance_id", ""))
            if target == self.identity.sender_id and aid:
                join_alliance(self.store, aid, self.identity.sender_id)
                ev = {
                    "player_id": self.identity.sender_id,
                    "alliance_id": aid,
                }
                self._emit_event("alliance_join", ev)
            return

        if mtype == "SNAPSHOT_HASH":
            remote_hash = str(payload.get("hash", ""))
            local_hash = snapshot_hash(self.store)
            if remote_hash != local_hash:
                self.mesh.send("SNAPSHOT_REQ", {}, addr, reliable=False)
            return

        if mtype == "SNAPSHOT_REQ":
            players = self.store.list_players()
            self.mesh.send("SNAPSHOT_RES", {"players": players, "hash": snapshot_hash(self.store)}, addr, reliable=False)
            return

        if mtype == "SNAPSHOT_RES":
            # conservative merge: upsert known players only.
            for p in payload.get("players", []):
                pid = str(p.get("player_id", ""))
                nick = str(p.get("nick", pid[:8]))
                if pid:
                    self.store.ensure_player(pid, nick)
            return

    def _announce(self) -> None:
        local = self.store.get_player(self.identity.sender_id) or {}
        hello = {
            "nick": self.profile.nick,
            "port": self.profile.listen_port,
            "x": float(local.get("pos_x", 0.0)),
            "y": float(local.get("pos_y", 0.0)),
            "vx": float(local.get("vel_x", 0.0)),
            "vy": float(local.get("vel_y", 0.0)),
        }
        for seed in self.profile.seed_peers:
            try:
                host, port = seed.rsplit(":", 1)
                self.mesh.send("HELLO", hello, (host, int(port)), reliable=False)
            except Exception:
                continue
        self.mesh.broadcast("HELLO", hello, port=self.profile.listen_port, reliable=False)

    def _bootstrap_update(self) -> None:
        # Lightweight, non-underhanded discovery: explicit HTTPS bootstrap + optional DNS SRV.
        now = time.time()
        if now - self.last_bootstrap_ts < 30.0:
            return
        self.last_bootstrap_ts = now

        cache_path = Path(self.profile.data_dir or ".") / "bootstrap_cache.json"
        cached = read_cached(cache_path, max_age_s=3600.0)
        if cached:
            self.profile.seed_peers = merge_seeds(self.profile.seed_peers, cached.seeds)

        # DNS SRV seeds (optional, requires dnspython installed)
        domain = os.environ.get("TWANSI_BOOTSTRAP_DOMAIN", "twansi.trentwyatt.com")
        srv = dns_srv_seeds(domain)
        if srv:
            self.profile.seed_peers = merge_seeds(self.profile.seed_peers, srv)

        # HTTPS bootstrap seeds
        url = self.profile.bootstrap_url
        if url:
            try:
                b = fetch_bootstrap(url, timeout_s=2.5)
                self.profile.seed_peers = merge_seeds(self.profile.seed_peers, b.seeds)
                write_cached(cache_path, b)
                self.log_event(f"bootstrap: +{len(b.seeds)} seeds")
            except Exception as e:  # noqa: BLE001
                self.log_event(f"bootstrap failed: {e}")

    def _scan(self) -> None:
        peers = self.membership.healthy(max_age=240)
        if not peers:
            self._bootstrap_update()
            self._announce()
            self.log_event("scan: no peers known, sent HELLO to seed/broadcast")
            return
        for p in peers:
            self.mesh.send("PING", {"ts": int(time.time() * 1000)}, (p.host, p.port), reliable=False)
        self.log_event(f"scan: pinged {len(peers)} peers")

    def _action_mine(self) -> dict[str, Any]:
        ev = self.engine.mine_burst_for_player(self.identity.sender_id)
        if not ev:
            return {"ok": False, "error": "mine failed"}
        ev["payload"]["nick"] = self.profile.nick
        self._emit_event(ev["event_type"], ev["payload"])
        return {"ok": True, "result": ev}

    def _action_attack(self) -> dict[str, Any]:
        ev = self.engine.random_battle_for_player(self.identity.sender_id)
        if not ev:
            return {"ok": False, "error": "no target players"}
        self._emit_event(ev["event_type"], ev["payload"])
        return {"ok": True, "result": ev}

    def _action_invite(self) -> dict[str, Any]:
        peers = self.membership.healthy(max_age=240)
        if not peers:
            return {"ok": False, "error": "no known peer"}
        target = random.choice(peers)
        alliance = player_alliance(self.store, self.identity.sender_id)
        if not alliance:
            alliance = create_alliance(self.store, f"{self.profile.nick}-alliance", self.identity.sender_id)
        self.mesh.send("ALLIANCE_INVITE", {"target": target.peer_id, "alliance_id": alliance}, (target.host, target.port), reliable=True)
        self.log_event(f"alliance invite sent to {target.nick}")
        return {"ok": True, "result": {"target": target.peer_id, "alliance_id": alliance}}

    def _action_trade(self, side: str, resource: str, qty: int) -> dict[str, Any]:
        try:
            p = self.store.get_player(self.identity.sender_id) or {}
            sector_id = int(p.get("sector", 1))
            trade = self.store.station_trade(self.identity.sender_id, sector_id, resource, qty, side)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        ev = {"player_id": self.identity.sender_id, "nick": self.profile.nick, **trade}
        self._emit_event("market_trade", ev)
        return {"ok": True, "result": ev}

    def _action_upgrade(self, domain: str) -> dict[str, Any]:
        try:
            up = upgrade_tech(self.store, self.identity.sender_id, domain)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        ev = {"player_id": self.identity.sender_id, "nick": self.profile.nick, **up}
        self._emit_event("tech_upgrade", ev)
        return {"ok": True, "result": ev}

    def do_action(self, action: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        args = args or {}
        action = action.strip().lower()
        if action == "mine":
            try:
                self.store.consume_ap(self.identity.sender_id, 1)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return self._action_mine()
        if action == "attack":
            try:
                self.store.consume_ap(self.identity.sender_id, 3)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return self._action_attack()
        if action == "scan":
            self._scan()
            return {"ok": True, "result": "scan"}
        if action == "invite":
            try:
                self.store.consume_ap(self.identity.sender_id, 1)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            return self._action_invite()
        if action == "digest":
            digest = build_offline_digest(self.store, self.identity.sender_id)
            self.log_event(f"digest: {digest}")
            return {"ok": True, "result": digest}
        if action == "buy":
            try:
                self.store.consume_ap(self.identity.sender_id, 1)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            resource = str(args.get("resource", "ore")).lower()
            qty = int(args.get("qty", 10))
            return self._action_trade("buy", resource, qty)
        if action == "sell":
            try:
                self.store.consume_ap(self.identity.sender_id, 1)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            resource = str(args.get("resource", "ore")).lower()
            qty = int(args.get("qty", 10))
            return self._action_trade("sell", resource, qty)
        if action == "upgrade":
            try:
                self.store.consume_ap(self.identity.sender_id, 2)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            domain = str(args.get("domain", "")).lower()
            if not domain:
                levels = self.store.get_tech_levels(self.identity.sender_id)
                tree = self._tech_tree_view(levels)
                ready = [d for d in TECH_DOMAINS if tree[d]["upgrade_ready"]]
                if not ready:
                    return {"ok": False, "error": "no upgrade currently available"}
                domain = sorted(ready, key=lambda d: (levels.get(d, 0), d))[0]
            if domain not in TECH_DOMAINS:
                return {"ok": False, "error": f"invalid domain {domain}"}
            return self._action_upgrade(domain)
        if action == "jump":
            p = self.store.get_player(self.identity.sender_id) or {}
            cur = int(p.get("sector", 1))
            target = int(args.get("sector", 0) or 0)
            if target <= 0:
                target = random.randint(1, 96)
            if target == cur:
                target = 1 + (target % 96)
            warps = set(self.store.list_warps(cur))
            is_short = target in warps
            gas_cost = (3 if is_short else 10) + abs(target - cur) // (12 if is_short else 6)
            ap_cost = 1 if is_short else 3
            try:
                self.store.consume_ap(self.identity.sender_id, ap_cost)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            if int(p.get("gas", 0)) < gas_cost:
                return {"ok": False, "error": "insufficient gas to jump"}
            self.store.update_player_resources(self.identity.sender_id, 0, 0, -gas_cost, 0)
            self.store.set_player_sector(self.identity.sender_id, target)
            self.store.set_player_motion(self.identity.sender_id, 0.0, 0.0, 0.0, 0.0)
            ev = {"player_id": self.identity.sender_id, "nick": self.profile.nick, "from": cur, "to": target, "gas_cost": gas_cost, "ap_cost": ap_cost}
            self._emit_event("jump", ev)
            return {"ok": True, "result": ev}
        if action == "observe":
            return {"ok": True, "result": self.public_state()}
        return {"ok": False, "error": f"unknown action '{action}'"}

    async def _agent_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while not self.runtime.shutdown:
            line = await reader.readline()
            if not line:
                break
            try:
                cmd = json.loads(line.decode("utf-8"))
            except Exception:
                writer.write(b'{"ok":false,"error":"invalid json"}\n')
                await writer.drain()
                continue

            op = str(cmd.get("cmd", ""))
            if op == "observe":
                resp = {"ok": True, "result": self.public_state()}
            elif op == "digest":
                resp = {"ok": True, "result": build_offline_digest(self.store, self.identity.sender_id)}
            elif op == "act":
                resp = self.do_action(str(cmd.get("action", "")), dict(cmd.get("args", {})))
            elif op == "ack":
                resp = {"ok": True, "result": "ack"}
            else:
                resp = {"ok": False, "error": "unknown cmd"}
            writer.write((json.dumps(resp, separators=(",", ":")) + "\n").encode("utf-8"))
            await writer.drain()

        writer.close()
        await writer.wait_closed()

    async def _tick_loop(self) -> None:
        while not self.runtime.shutdown:
            t0 = time.perf_counter()
            now = time.time()

            if now - self.last_strategic_tick >= STRATEGIC_TICK_SECONDS:
                res = self.engine.strategic_tick(self.identity.sender_id)
                self.runtime.tick_ms = res.tick_ms
                self.last_strategic_tick = now
                for ev in res.events:
                    ev["payload"]["nick"] = self.profile.nick
                    self._emit_event(ev["event_type"], ev["payload"])

            if now - self.last_resource_tick >= RESOURCE_TICK_SECONDS:
                ev = self.engine.resource_tick_for_player(self.identity.sender_id)
                self.last_resource_tick = now
                if ev:
                    ev["payload"]["nick"] = self.profile.nick
                    self._emit_event(ev["event_type"], ev["payload"])
                drift_market(self.store)

            while True:
                try:
                    cmd = self.command_queue.get_nowait()
                except Empty:
                    break
                if cmd == "quit":
                    self.runtime.shutdown = True
                    break
                elif cmd == "m":
                    self.do_action("mine")
                elif cmd == "a":
                    self.do_action("attack")
                elif cmd == "s":
                    self.do_action("scan")
                elif cmd == "i":
                    self.do_action("invite")
                elif cmd == "d":
                    self.do_action("digest")
                elif cmd == "b":
                    self.do_action("buy", {"resource": "ore", "qty": 8})
                elif cmd == "n":
                    self.do_action("sell", {"resource": "ore", "qty": 8})
                elif cmd == "u":
                    self.do_action("upgrade")
                elif cmd == "j":
                    self.do_action("jump")
                elif cmd == "zoom_in":
                    self.radar_zoom = max(0.25, self.radar_zoom * 0.8)
                elif cmd == "zoom_out":
                    self.radar_zoom = min(4.0, self.radar_zoom * 1.25)

            now_sec = int(now)
            if now_sec % 8 == 0 and now_sec != self.last_announce_second:
                self._bootstrap_update()
                self._announce()
                self.last_announce_second = now_sec
            if now_sec % 11 == 0 and now_sec != self.last_snapshot_second:
                self.mesh.broadcast("SNAPSHOT_HASH", {"hash": snapshot_hash(self.store)}, self.profile.listen_port)
                self.last_snapshot_second = now_sec

            elapsed = time.perf_counter() - t0
            await asyncio.sleep(max(0.05, 0.2 - elapsed))

    async def run_async(self) -> None:
        await self.transport.start()
        self.log_event(f"node up: {self.profile.nick} {self.profile.listen_host}:{self.profile.listen_port}")

        self._announce()
        self._scan()

        self.server = await asyncio.start_server(self._agent_client, host="127.0.0.1", port=self.agent_server_port)
        self.log_event(f"agent api: 127.0.0.1:{self.agent_server_port}")

        recv_task = asyncio.create_task(self.mesh.recv_loop())
        retransmit_task = asyncio.create_task(self.mesh.retransmit_loop())
        tick_task = asyncio.create_task(self._tick_loop())

        try:
            while not self.runtime.shutdown:
                await asyncio.sleep(0.2)
        finally:
            for t in (recv_task, retransmit_task, tick_task):
                t.cancel()
            await asyncio.gather(recv_task, retransmit_task, tick_task, return_exceptions=True)
            if self.server:
                self.server.close()
                await self.server.wait_closed()
            await self.transport.close()

    def run(self, with_ui: bool = True) -> int:
        loop = asyncio.new_event_loop()
        exc: list[BaseException] = []

        def runner() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run_async())
            except BaseException as e:  # noqa: BLE001
                exc.append(e)
            finally:
                loop.stop()
                loop.close()

        t = threading.Thread(target=runner, daemon=True)
        t.start()

        try:
            if with_ui:
                dash = Dashboard(state_cb=self.public_state, command_cb=self.enqueue_command)
                dash.run()
            else:
                while t.is_alive() and not self.runtime.shutdown:
                    time.sleep(0.2)
        except KeyboardInterrupt:
            self.runtime.shutdown = True
        finally:
            self.runtime.shutdown = True
            self.enqueue_command("quit")
            t.join(timeout=3.0)

        if exc:
            raise exc[0]
        return 0


def cmd_init(args: argparse.Namespace) -> int:
    host, port = parse_listen(args.listen)
    profile = Profile(
        nick=args.nick,
        listen_host=host,
        listen_port=port,
        shard=args.shard,
        seed_peers=args.seed or [],
        shard_key=args.shard_key or "",
    )
    home = twansi_home()
    save_profile(profile, home)
    print(f"initialized profile at {home}/profile.json")
    return 0


def cmd_join(args: argparse.Namespace) -> int:
    profile = load_profile()
    seeds = set(profile.seed_peers)
    seeds.add(args.seed)
    profile.seed_peers = sorted(seeds)
    if args.shard:
        profile.shard = args.shard
    save_profile(profile)
    print("updated profile with seed")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    profile = load_profile()
    node = GameNode(profile)
    with_ui = os.environ.get("TWANSI_DISABLE_UI", "0") != "1"
    return node.run(with_ui=with_ui)


def cmd_dashboard(args: argparse.Namespace) -> int:
    # dashboard is integrated in run; this alias keeps CLI compatibility.
    return cmd_run(args)


def cmd_bot(args: argparse.Namespace) -> int:
    bot_args = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--seconds",
        str(args.seconds),
        "--aggressiveness",
        str(args.aggressiveness),
    ]
    return bot_main(bot_args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="twansi multiplayer ansi game")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="initialize local profile")
    p_init.add_argument("--nick", required=True)
    p_init.add_argument("--listen", default="0.0.0.0:39000")
    p_init.add_argument("--shard", default="alpha")
    p_init.add_argument("--seed", action="append", default=[])
    p_init.add_argument("--shard-key", default="", help="optional shared shard auth key (hex)")
    p_init.set_defaults(func=cmd_init)

    p_join = sub.add_parser("join", help="add a seed peer")
    p_join.add_argument("--seed", required=True, help="host:port")
    p_join.add_argument("--shard", default=None)
    p_join.set_defaults(func=cmd_join)

    p_run = sub.add_parser("run", help="run node")
    p_run.set_defaults(func=cmd_run)

    p_dash = sub.add_parser("dashboard", help="run node with dashboard")
    p_dash.set_defaults(func=cmd_dashboard)

    p_bot = sub.add_parser("bot", help="run optional headless bot client")
    p_bot.add_argument("--host", default="127.0.0.1")
    p_bot.add_argument("--port", type=int, default=39100)
    p_bot.add_argument("--seconds", type=int, default=30)
    p_bot.add_argument("--aggressiveness", type=float, default=0.35)
    p_bot.set_defaults(func=cmd_bot)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
