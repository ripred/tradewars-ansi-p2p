from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any
import random
import hashlib


class Store:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        # These are set by GameNode at startup to make world/market deterministic per shard+epoch.
        self.world_shard = "alpha"
        self.world_epoch = 1
        self._init()

    def configure_world(self, shard: str, epoch: int) -> None:
        self.world_shard = str(shard or "alpha")
        self.world_epoch = int(epoch)

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:
            pass

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()

    def _init(self) -> None:
        cur = self.db.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA temp_store=MEMORY;
            CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY,
                nick TEXT NOT NULL,
                doctrine TEXT NOT NULL,
                credits INTEGER NOT NULL,
                ore INTEGER NOT NULL,
                gas INTEGER NOT NULL,
                crystal INTEGER NOT NULL,
                hp INTEGER NOT NULL,
                shield INTEGER NOT NULL DEFAULT 0,
                sector INTEGER NOT NULL,
                pos_x REAL NOT NULL DEFAULT 0,
                pos_y REAL NOT NULL DEFAULT 0,
                vel_x REAL NOT NULL DEFAULT 0,
                vel_y REAL NOT NULL DEFAULT 0,
                motion_ts REAL NOT NULL DEFAULT 0,
                ap INTEGER NOT NULL DEFAULT 100,
                ap_updated_ts REAL NOT NULL DEFAULT 0,
                alliance_id TEXT,
                updated_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sectors (
                sector_id INTEGER PRIMARY KEY,
                owner_player_id TEXT,
                richness INTEGER NOT NULL,
                danger INTEGER NOT NULL,
                defense_level INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS alliances (
                alliance_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS alliance_members (
                alliance_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                role TEXT NOT NULL,
                PRIMARY KEY (alliance_id, player_id)
            );
            CREATE TABLE IF NOT EXISTS battles (
                battle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                attacker TEXT NOT NULL,
                defender TEXT NOT NULL,
                winner TEXT NOT NULL,
                damage_attacker INTEGER NOT NULL,
                damage_defender INTEGER NOT NULL,
                sector_id INTEGER NOT NULL,
                summary TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                sender TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                event_id TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS digest_cursor (
                player_id TEXT PRIMARY KEY,
                last_event_id INTEGER NOT NULL,
                updated_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_state (
                resource TEXT PRIMARY KEY,
                price INTEGER NOT NULL,
                updated_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS station_inventory (
                sector_id INTEGER NOT NULL,
                resource TEXT NOT NULL,
                stock INTEGER NOT NULL,
                PRIMARY KEY(sector_id, resource)
            );
            CREATE TABLE IF NOT EXISTS ports (
                sector_id INTEGER PRIMARY KEY,
                port_class TEXT NOT NULL,
                created_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS port_inventory (
                sector_id INTEGER NOT NULL,
                resource TEXT NOT NULL,
                stock INTEGER NOT NULL,
                PRIMARY KEY(sector_id, resource)
            );
            CREATE TABLE IF NOT EXISTS warps (
                sector_id INTEGER NOT NULL,
                to_sector_id INTEGER NOT NULL,
                PRIMARY KEY(sector_id, to_sector_id)
            );
            CREATE TABLE IF NOT EXISTS tech_tree (
                player_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                level INTEGER NOT NULL,
                PRIMARY KEY(player_id, domain)
            );
            CREATE TABLE IF NOT EXISTS mission_claims (
                player_id TEXT NOT NULL,
                mission_id TEXT NOT NULL,
                claimed_ts REAL NOT NULL,
                PRIMARY KEY(player_id, mission_id)
            );
            """
        )
        self._migrate_players_table()
        self._migrate_sectors_table()
        self._init_market()
        self._init_stations()
        self._init_ports()
        self.db.commit()

    def has_mission_claim(self, player_id: str, mission_id: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM mission_claims WHERE player_id=? AND mission_id=?",
            (str(player_id), str(mission_id)),
        ).fetchone()
        return bool(row)

    def set_mission_claim(self, player_id: str, mission_id: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO mission_claims(player_id, mission_id, claimed_ts) VALUES(?,?,?)",
            (str(player_id), str(mission_id), time.time()),
        )
        self.db.commit()

    def leaderboard(self, limit: int = 10) -> list[dict[str, Any]]:
        limit = max(1, min(50, int(limit)))
        # Compute owned sectors count in SQL.
        rows = self.db.execute(
            """
            SELECT p.player_id, p.nick, p.credits,
                   COALESCE(s.owned, 0) as sectors_owned
            FROM players p
            LEFT JOIN (
              SELECT owner_player_id as pid, COUNT(*) as owned
              FROM sectors
              WHERE owner_player_id IS NOT NULL
              GROUP BY owner_player_id
            ) s ON s.pid = p.player_id
            ORDER BY p.credits DESC, sectors_owned DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "player_id": str(r[0]),
                    "nick": str(r[1]),
                    "credits": int(r[2]),
                    "sectors_owned": int(r[3]),
                }
            )
        return out

    def _migrate_players_table(self) -> None:
        cols = {row[1] for row in self.db.execute("PRAGMA table_info(players)").fetchall()}
        required = {
            "pos_x": "ALTER TABLE players ADD COLUMN pos_x REAL NOT NULL DEFAULT 0",
            "pos_y": "ALTER TABLE players ADD COLUMN pos_y REAL NOT NULL DEFAULT 0",
            "vel_x": "ALTER TABLE players ADD COLUMN vel_x REAL NOT NULL DEFAULT 0",
            "vel_y": "ALTER TABLE players ADD COLUMN vel_y REAL NOT NULL DEFAULT 0",
            "motion_ts": "ALTER TABLE players ADD COLUMN motion_ts REAL NOT NULL DEFAULT 0",
            "ap": "ALTER TABLE players ADD COLUMN ap INTEGER NOT NULL DEFAULT 100",
            "ap_updated_ts": "ALTER TABLE players ADD COLUMN ap_updated_ts REAL NOT NULL DEFAULT 0",
            "shield": "ALTER TABLE players ADD COLUMN shield INTEGER NOT NULL DEFAULT 0",
        }
        for col, stmt in required.items():
            if col not in cols:
                self.db.execute(stmt)

    def _migrate_sectors_table(self) -> None:
        cols = {row[1] for row in self.db.execute("PRAGMA table_info(sectors)").fetchall()}
        if "defense_level" not in cols:
            self.db.execute("ALTER TABLE sectors ADD COLUMN defense_level INTEGER NOT NULL DEFAULT 0")

    def ensure_player(self, player_id: str, nick: str, doctrine: str = "assault") -> None:
        now = time.time()
        self.db.execute(
            """
            INSERT INTO players(player_id,nick,doctrine,credits,ore,gas,crystal,hp,sector,alliance_id,updated_ts)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(player_id) DO UPDATE SET nick=excluded.nick, updated_ts=excluded.updated_ts
            """,
            (player_id, nick, doctrine, 1000, 100, 100, 100, 100, 1, None, now),
        )
        # Initialize AP timestamp if it's still default.
        self.db.execute(
            "UPDATE players SET ap_updated_ts=? WHERE player_id=? AND ap_updated_ts=0",
            (now, player_id),
        )
        for domain in ("ship_hull", "weapons", "shields", "mining", "defense_grid"):
            self.db.execute(
                "INSERT OR IGNORE INTO tech_tree(player_id,domain,level) VALUES(?,?,?)",
                (player_id, domain, 0),
            )
        self.db.commit()

    def regen_ap(self, player_id: str, max_ap: int = 200, per_minute: int = 20) -> int:
        p = self.get_player(player_id)
        if not p:
            return 0
        now = time.time()
        last = float(p.get("ap_updated_ts", 0.0) or 0.0)
        ap = int(p.get("ap", 0))
        if last <= 0:
            last = now
        delta_min = max(0.0, (now - last) / 60.0)
        gain = int(delta_min * per_minute)
        if gain <= 0 and ap <= max_ap:
            return ap
        new_ap = min(max_ap, ap + gain)
        self.db.execute(
            "UPDATE players SET ap=?, ap_updated_ts=? WHERE player_id=?",
            (new_ap, now, player_id),
        )
        self.db.commit()
        return new_ap

    def consume_ap(self, player_id: str, cost: int) -> None:
        cost = max(0, int(cost))
        if cost == 0:
            return
        p = self.get_player(player_id)
        if not p:
            raise ValueError("player not found")
        ap = int(p.get("ap", 0))
        if ap < cost:
            raise ValueError("insufficient AP")
        self.db.execute("UPDATE players SET ap=ap-?, updated_ts=? WHERE player_id=?", (cost, time.time(), player_id))
        self.db.commit()

    def list_warps(self, sector_id: int) -> list[int]:
        rows = self.db.execute("SELECT to_sector_id FROM warps WHERE sector_id=? ORDER BY to_sector_id ASC", (int(sector_id),)).fetchall()
        return [int(r[0]) for r in rows]

    def add_warp(self, sector_id: int, to_sector_id: int) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO warps(sector_id,to_sector_id) VALUES(?,?)",
            (int(sector_id), int(to_sector_id)),
        )
        self.db.commit()

    def _init_market(self) -> None:
        now = time.time()
        defaults = {
            "ore": 5,
            "gas": 6,
            "crystal": 8,
        }
        for res, price in defaults.items():
            self.db.execute(
                "INSERT OR IGNORE INTO market_state(resource,price,updated_ts) VALUES(?,?,?)",
                (res, price, now),
            )

    def _init_stations(self) -> None:
        # Lazy per-sector station inventory. We don't know sector count here; callers should
        # call ensure_station_inventory(sector_id).
        return

    def _init_ports(self) -> None:
        # Ports are lazily created per sector by ensure_port().
        return

    def _seed64(self, *parts: Any) -> int:
        s = "|".join(str(p) for p in parts)
        h = hashlib.sha256(s.encode("utf-8")).digest()
        return int.from_bytes(h[:8], "big", signed=False)

    def ensure_port(self, sector_id: int, port_class: str | None = None, stock: dict[str, int] | None = None) -> None:
        sector_id = int(sector_id)
        row = self.db.execute("SELECT port_class FROM ports WHERE sector_id=?", (sector_id,)).fetchone()
        if row:
            return
        # Port classes loosely inspired by Tradewars: different commodities favored.
        classes = ["BBS", "BSS", "SBB", "SSB", "BSB", "SBS"]
        if port_class and port_class in classes:
            pclass = str(port_class)
        else:
            # Deterministic fallback: sector_id -> class (no shared RNG required).
            pclass = classes[self._seed64("twansi-port-class", self.world_shard, self.world_epoch, sector_id) % len(classes)]
        self.db.execute(
            "INSERT OR IGNORE INTO ports(sector_id,port_class,created_ts) VALUES(?,?,?)",
            (sector_id, pclass, time.time()),
        )
        # Initialize inventory
        s = self.get_sector(sector_id) or {"richness": 4, "danger": 5}
        richness = int(s.get("richness", 4))
        danger = int(s.get("danger", 5))
        base = 300 + richness * 70 - danger * 12
        base = max(120, base)
        weights = {
            "ore": 1.0,
            "gas": 1.0,
            "crystal": 1.0,
        }
        # Buy-heavy ports keep less stock (they want to buy from players).
        if pclass[0] == "B":
            weights["ore"] *= 0.7
        else:
            weights["ore"] *= 1.25
        if pclass[1] == "B":
            weights["gas"] *= 0.7
        else:
            weights["gas"] *= 1.25
        if pclass[2] == "B":
            weights["crystal"] *= 0.7
        else:
            weights["crystal"] *= 1.25
        for res in ("ore", "gas", "crystal"):
            if stock and res in stock:
                s0 = int(stock[res])
            else:
                srng = random.Random(self._seed64("twansi-port-stock", self.world_shard, self.world_epoch, sector_id, res))
                s0 = int(base * weights[res]) + srng.randint(0, 60)
            self.db.execute(
                "INSERT OR IGNORE INTO port_inventory(sector_id,resource,stock) VALUES(?,?,?)",
                (sector_id, res, max(-999999, min(999999, s0))),
            )
        self.db.commit()

    def adjust_port_stock(self, sector_id: int, resource: str, delta: int) -> None:
        resource = resource.lower()
        if resource not in ("ore", "gas", "crystal"):
            return
        sector_id = int(sector_id)
        self.ensure_port(sector_id)
        delta = int(delta)
        self.db.execute(
            "UPDATE port_inventory SET stock=stock+? WHERE sector_id=? AND resource=?",
            (delta, sector_id, resource),
        )
        self.db.commit()

    def port_info(self, sector_id: int) -> dict[str, Any] | None:
        sector_id = int(sector_id)
        row = self.db.execute("SELECT port_class FROM ports WHERE sector_id=?", (sector_id,)).fetchone()
        if not row:
            return None
        pclass = str(row[0])
        inv_rows = self.db.execute("SELECT resource,stock FROM port_inventory WHERE sector_id=?", (sector_id,)).fetchall()
        inv = {str(r[0]): int(r[1]) for r in inv_rows}
        base = self.get_market_prices()
        # Spread and bias per class: B means port buys from player (higher bid, lower ask stock).
        prices: dict[str, dict[str, int]] = {}
        for idx, res in enumerate(("ore", "gas", "crystal")):
            mode = pclass[idx]
            stock = inv.get(res, 0)
            # Smooth scarcity: allows negative stock (mesh-convergent deltas) without hard OOS errors.
            target = 520.0
            scarcity = 1.0 + ((target - float(stock)) / target) * 0.45
            scarcity = max(0.75, min(1.8, scarcity))
            mid = max(1, int(round(base.get(res, 5) * scarcity)))
            spread = max(1, mid // 6)
            if mode == "B":
                bid = mid + spread
                ask = mid + spread * 3
            else:
                bid = max(1, mid - spread * 3)
                ask = mid - spread
            prices[res] = {"bid": bid, "ask": max(1, ask)}
        return {"sector_id": sector_id, "port_class": pclass, "prices": prices, "stock": inv}

    def port_trade(self, player_id: str, sector_id: int, resource: str, qty: int, side: str) -> dict[str, Any]:
        resource = resource.lower()
        if resource not in ("ore", "gas", "crystal"):
            raise ValueError("invalid resource")
        qty = max(1, int(qty))
        side = side.lower()
        sector_id = int(sector_id)

        p = self.get_player(player_id)
        if not p:
            raise ValueError("player not found")
        if int(p["sector"]) != sector_id:
            raise ValueError("not in that sector")

        info = self.port_info(sector_id)
        if not info:
            raise ValueError("no port in sector")

        mode_idx = {"ore": 0, "gas": 1, "crystal": 2}[resource]
        mode = str(info["port_class"])[mode_idx]
        stock = int(info["stock"][resource])
        bid = int(info["prices"][resource]["bid"])
        ask = int(info["prices"][resource]["ask"])

        # fees lower than station to encourage port gameplay
        if side == "buy":
            if mode != "S":
                raise ValueError("this port does not sell that commodity")
            gross = ask * qty
            fee = max(1, gross // 40)
            total = gross + fee
            if int(p["credits"]) < total:
                raise ValueError("insufficient credits")
            self.db.execute(
                f"UPDATE players SET credits=credits-?, {resource}={resource}+?, updated_ts=? WHERE player_id=?",
                (total, qty, time.time(), player_id),
            )
            self.db.execute(
                "UPDATE port_inventory SET stock=stock-? WHERE sector_id=? AND resource=?",
                (qty, sector_id, resource),
            )
            self.db.commit()
            return {
                "side": side,
                "sector_id": sector_id,
                "resource": resource,
                "qty": qty,
                "unit_price": ask,
                "fee": fee,
                "credits_delta": -total,
                "port_class": str(info["port_class"]),
            }

        if side == "sell":
            if mode != "B":
                raise ValueError("this port does not buy that commodity")
            if int(p[resource]) < qty:
                raise ValueError("insufficient inventory")
            gross = bid * qty
            fee = max(1, gross // 50)
            proceeds = max(1, gross - fee)
            self.db.execute(
                f"UPDATE players SET credits=credits+?, {resource}={resource}-?, updated_ts=? WHERE player_id=?",
                (proceeds, qty, time.time(), player_id),
            )
            # port stock increases when buying from players
            self.db.execute(
                "UPDATE port_inventory SET stock=stock+? WHERE sector_id=? AND resource=?",
                (qty, sector_id, resource),
            )
            self.db.commit()
            return {
                "side": side,
                "sector_id": sector_id,
                "resource": resource,
                "qty": qty,
                "unit_price": bid,
                "fee": fee,
                "credits_delta": proceeds,
                "port_class": str(info["port_class"]),
            }

        raise ValueError("invalid side")

    def ensure_station_inventory(self, sector_id: int, richness: int | None = None, danger: int | None = None) -> None:
        sector_id = int(sector_id)
        row = self.db.execute("SELECT 1 FROM station_inventory WHERE sector_id=? LIMIT 1", (sector_id,)).fetchone()
        if row:
            return
        if richness is None or danger is None:
            s = self.get_sector(sector_id) or {"richness": 4, "danger": 5}
            richness = int(s.get("richness", 4))
            danger = int(s.get("danger", 5))
        base = 420 + richness * 60 - danger * 10
        base = max(120, base)
        for res, mult in (("ore", 1.2), ("gas", 1.0), ("crystal", 0.8)):
            # Deterministic per shard+epoch+sector, so stations converge without a central server.
            srng = random.Random(self._seed64("twansi-station-stock", self.world_shard, self.world_epoch, sector_id, res))
            stock = int(base * mult) + srng.randint(0, 50)
            self.db.execute(
                "INSERT OR IGNORE INTO station_inventory(sector_id,resource,stock) VALUES(?,?,?)",
                (sector_id, res, stock),
            )
        self.db.commit()

    def adjust_station_stock(self, sector_id: int, resource: str, delta: int) -> None:
        resource = resource.lower()
        if resource not in ("ore", "gas", "crystal"):
            return
        sector_id = int(sector_id)
        self.ensure_station_inventory(sector_id)
        delta = int(delta)
        self.db.execute(
            "UPDATE station_inventory SET stock=stock+? WHERE sector_id=? AND resource=?",
            (delta, sector_id, resource),
        )
        self.db.commit()

    def station_modifier(self, sector_id: int) -> float:
        s = self.get_sector(int(sector_id)) or {"richness": 4, "danger": 5}
        richness = int(s.get("richness", 4))
        danger = int(s.get("danger", 5))
        mod = 1.0 + (danger - 5) * 0.03 - (richness - 4) * 0.02
        return max(0.7, min(1.4, mod))

    def station_market(self, sector_id: int) -> dict[str, Any]:
        sector_id = int(sector_id)
        self.ensure_station_inventory(sector_id)
        base = self.get_market_prices()
        mod = self.station_modifier(sector_id)
        rows = self.db.execute("SELECT resource,stock FROM station_inventory WHERE sector_id=?", (sector_id,)).fetchall()
        inv = {str(r[0]): int(r[1]) for r in rows}
        prices: dict[str, int] = {}
        for res, base_price in base.items():
            stock = inv.get(res, 0)
            scarcity = 1.0
            if stock < 120:
                scarcity = 1.25
            elif stock > 650:
                scarcity = 0.9
            prices[res] = max(1, int(round(base_price * mod * scarcity)))
        return {"sector_id": sector_id, "modifier": mod, "prices": prices, "stock": inv}

    def station_trade(self, player_id: str, sector_id: int, resource: str, qty: int, side: str) -> dict[str, Any]:
        resource = resource.lower()
        if resource not in ("ore", "gas", "crystal"):
            raise ValueError("invalid resource")
        qty = max(1, int(qty))
        side = side.lower()
        sector_id = int(sector_id)

        mkt = self.station_market(sector_id)
        unit_price = int(mkt["prices"][resource])
        stock = int(mkt["stock"][resource])

        p = self.get_player(player_id)
        if not p:
            raise ValueError("player not found")
        if int(p["sector"]) != sector_id:
            raise ValueError("not in that sector")

        gross = unit_price * qty
        fee = max(1, gross // 30)

        if side == "buy":
            if stock < qty:
                raise ValueError("station out of stock")
            total = gross + fee
            if int(p["credits"]) < total:
                raise ValueError("insufficient credits")
            self.db.execute(
                f"UPDATE players SET credits=credits-?, {resource}={resource}+?, updated_ts=? WHERE player_id=?",
                (total, qty, time.time(), player_id),
            )
            self.db.execute(
                "UPDATE station_inventory SET stock=stock-? WHERE sector_id=? AND resource=?",
                (qty, sector_id, resource),
            )
            self.db.commit()
            return {
                "side": side,
                "sector_id": sector_id,
                "resource": resource,
                "qty": qty,
                "unit_price": unit_price,
                "fee": fee,
                "credits_delta": -total,
            }
        if side == "sell":
            if int(p[resource]) < qty:
                raise ValueError("insufficient inventory")
            proceeds = max(1, gross - fee)
            self.db.execute(
                f"UPDATE players SET credits=credits+?, {resource}={resource}-?, updated_ts=? WHERE player_id=?",
                (proceeds, qty, time.time(), player_id),
            )
            self.db.execute(
                "UPDATE station_inventory SET stock=stock+? WHERE sector_id=? AND resource=?",
                (qty, sector_id, resource),
            )
            self.db.commit()
            return {
                "side": side,
                "sector_id": sector_id,
                "resource": resource,
                "qty": qty,
                "unit_price": unit_price,
                "fee": fee,
                "credits_delta": proceeds,
            }
        raise ValueError("invalid side")

    def get_market_prices(self) -> dict[str, int]:
        rows = self.db.execute("SELECT resource,price FROM market_state").fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    def update_market_price(self, resource: str, price: int) -> None:
        self.db.execute(
            "UPDATE market_state SET price=?, updated_ts=? WHERE resource=?",
            (max(1, int(price)), time.time(), resource),
        )
        self.db.commit()

    def trade_resource(self, player_id: str, resource: str, qty: int, side: str) -> dict[str, Any]:
        if resource not in ("ore", "gas", "crystal"):
            raise ValueError("invalid resource")
        qty = max(1, int(qty))
        side = side.lower()
        price_row = self.db.execute("SELECT price FROM market_state WHERE resource=?", (resource,)).fetchone()
        if not price_row:
            raise ValueError("resource not listed")
        unit_price = int(price_row[0])
        gross = unit_price * qty

        p = self.get_player(player_id)
        if not p:
            raise ValueError("player not found")

        fee = max(1, gross // 25)
        if side == "buy":
            total_cost = gross + fee
            if int(p["credits"]) < total_cost:
                raise ValueError("insufficient credits")
            self.db.execute(
                f"UPDATE players SET credits=credits-?, {resource}={resource}+?, updated_ts=? WHERE player_id=?",
                (total_cost, qty, time.time(), player_id),
            )
            # slightly increase price under buy pressure
            self.db.execute(
                "UPDATE market_state SET price=price+?, updated_ts=? WHERE resource=?",
                (max(1, qty // 12), time.time(), resource),
            )
            self.db.commit()
            return {"side": side, "resource": resource, "qty": qty, "unit_price": unit_price, "fee": fee, "credits_delta": -total_cost}
        if side == "sell":
            if int(p[resource]) < qty:
                raise ValueError("insufficient inventory")
            proceeds = max(1, gross - fee)
            self.db.execute(
                f"UPDATE players SET credits=credits+?, {resource}={resource}-?, updated_ts=? WHERE player_id=?",
                (proceeds, qty, time.time(), player_id),
            )
            # slightly decrease price under sell pressure
            self.db.execute(
                "UPDATE market_state SET price=max(1, price-?), updated_ts=? WHERE resource=?",
                (max(1, qty // 15), time.time(), resource),
            )
            self.db.commit()
            return {"side": side, "resource": resource, "qty": qty, "unit_price": unit_price, "fee": fee, "credits_delta": proceeds}
        raise ValueError("invalid side")

    def get_tech_levels(self, player_id: str) -> dict[str, int]:
        rows = self.db.execute("SELECT domain,level FROM tech_tree WHERE player_id=?", (player_id,)).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    def set_tech_level(self, player_id: str, domain: str, level: int) -> None:
        self.db.execute(
            """
            INSERT INTO tech_tree(player_id,domain,level) VALUES(?,?,?)
            ON CONFLICT(player_id,domain) DO UPDATE SET level=excluded.level
            """,
            (player_id, domain, max(0, int(level))),
        )
        self.db.commit()

    def get_player(self, player_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM players WHERE player_id=?", (player_id,)).fetchone()
        return dict(row) if row else None

    def list_players(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM players ORDER BY updated_ts DESC").fetchall()
        return [dict(r) for r in rows]

    def alliance_info(self, alliance_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM alliances WHERE alliance_id=?", (str(alliance_id),)).fetchone()
        return dict(row) if row else None

    def list_alliance_members(self, alliance_id: str) -> list[dict[str, Any]]:
        alliance_id = str(alliance_id)
        rows = self.db.execute(
            """
            SELECT m.player_id as player_id, m.role as role, p.nick as nick
            FROM alliance_members m
            LEFT JOIN players p ON p.player_id=m.player_id
            WHERE m.alliance_id=?
            ORDER BY CASE m.role WHEN 'leader' THEN 0 ELSE 1 END, COALESCE(p.nick, m.player_id) ASC
            """,
            (alliance_id,),
        ).fetchall()
        out = []
        for r in rows:
            out.append({"player_id": str(r[0]), "role": str(r[1]), "nick": str(r[2] or str(r[0])[:8])})
        return out

    def create_alliance(self, alliance_id: str, name: str, owner_player_id: str) -> None:
        alliance_id = str(alliance_id)
        name = str(name or "alliance")
        owner_player_id = str(owner_player_id)
        self.db.execute(
            "INSERT OR IGNORE INTO alliances(alliance_id,name,created_ts) VALUES(?,?,?)",
            (alliance_id, name, time.time()),
        )
        self.db.execute(
            "INSERT OR REPLACE INTO alliance_members(alliance_id,player_id,role) VALUES(?,?,?)",
            (alliance_id, owner_player_id, "leader"),
        )
        self.db.execute("UPDATE players SET alliance_id=? WHERE player_id=?", (alliance_id, owner_player_id))
        self.db.commit()

    def rename_alliance(self, alliance_id: str, name: str) -> None:
        self.db.execute("UPDATE alliances SET name=? WHERE alliance_id=?", (str(name or "alliance"), str(alliance_id)))
        self.db.commit()

    def remove_alliance_member(self, alliance_id: str, player_id: str) -> None:
        self.db.execute(
            "DELETE FROM alliance_members WHERE alliance_id=? AND player_id=?",
            (str(alliance_id), str(player_id)),
        )
        self.db.execute("UPDATE players SET alliance_id=NULL WHERE player_id=? AND alliance_id=?", (str(player_id), str(alliance_id)))
        self.db.commit()

    def leave_alliance(self, player_id: str) -> None:
        p = self.get_player(str(player_id))
        if not p or not p.get("alliance_id"):
            return
        aid = str(p["alliance_id"])
        self.db.execute("DELETE FROM alliance_members WHERE alliance_id=? AND player_id=?", (aid, str(player_id)))
        self.db.execute("UPDATE players SET alliance_id=NULL WHERE player_id=?", (str(player_id),))
        self.db.commit()

    def update_player_resources(self, player_id: str, credits: int, ore: int, gas: int, crystal: int, hp: int | None = None) -> None:
        now = time.time()
        if hp is None:
            self.db.execute(
                """
                UPDATE players SET credits=credits+?, ore=ore+?, gas=gas+?, crystal=crystal+?, updated_ts=?
                WHERE player_id=?
                """,
                (credits, ore, gas, crystal, now, player_id),
            )
        else:
            self.db.execute(
                """
                UPDATE players SET credits=credits+?, ore=ore+?, gas=gas+?, crystal=crystal+?, hp=?, updated_ts=?
                WHERE player_id=?
                """,
                (credits, ore, gas, crystal, hp, now, player_id),
            )
        self.db.commit()

    def set_player_sector(self, player_id: str, sector: int) -> None:
        self.db.execute("UPDATE players SET sector=?, updated_ts=? WHERE player_id=?", (sector, time.time(), player_id))
        self.db.commit()

    def set_player_motion(self, player_id: str, pos_x: float, pos_y: float, vel_x: float, vel_y: float) -> None:
        self.db.execute(
            "UPDATE players SET pos_x=?, pos_y=?, vel_x=?, vel_y=?, motion_ts=?, updated_ts=? WHERE player_id=?",
            (pos_x, pos_y, vel_x, vel_y, time.time(), time.time(), player_id),
        )
        self.db.commit()

    def record_event(self, sender: str, event_type: str, payload: dict[str, Any], event_id: str | None = None) -> int:
        cur = self.db.cursor()
        cur.execute(
            "INSERT OR IGNORE INTO event_log(ts,sender,event_type,payload,event_id) VALUES(?,?,?,?,?)",
            (time.time(), sender, event_type, json.dumps(payload, separators=(",", ":")), event_id),
        )
        self.db.commit()
        if cur.lastrowid:
            return int(cur.lastrowid)
        row = self.db.execute("SELECT id FROM event_log WHERE event_id=?", (event_id,)).fetchone()
        return int(row[0]) if row else 0

    def events_since(self, last_id: int) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM event_log WHERE id>? ORDER BY id ASC", (last_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    def recent_events(self, limit: int = 80) -> list[dict[str, Any]]:
        limit = max(0, min(500, int(limit)))
        rows = self.db.execute("SELECT * FROM event_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in reversed(rows):
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    def get_digest_cursor(self, player_id: str) -> int:
        row = self.db.execute("SELECT last_event_id FROM digest_cursor WHERE player_id=?", (player_id,)).fetchone()
        return int(row[0]) if row else 0

    def set_digest_cursor(self, player_id: str, event_id: int) -> None:
        self.db.execute(
            """
            INSERT INTO digest_cursor(player_id,last_event_id,updated_ts) VALUES(?,?,?)
            ON CONFLICT(player_id) DO UPDATE SET last_event_id=excluded.last_event_id, updated_ts=excluded.updated_ts
            """,
            (player_id, event_id, time.time()),
        )
        self.db.commit()

    def ensure_sector(self, sector_id: int, richness: int, danger: int) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO sectors(sector_id,owner_player_id,richness,danger,defense_level) VALUES(?,?,?,?,?)",
            (sector_id, None, richness, danger, 0),
        )
        self.db.commit()

    def get_sector(self, sector_id: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM sectors WHERE sector_id=?", (sector_id,)).fetchone()
        return dict(row) if row else None

    def claim_sector(self, sector_id: int, owner_player_id: str) -> None:
        # On conquest, reset defenses.
        self.db.execute(
            "UPDATE sectors SET owner_player_id=?, defense_level=0 WHERE sector_id=?",
            (owner_player_id, sector_id),
        )
        self.db.commit()

    def upgrade_sector_defense(self, sector_id: int, player_id: str, delta: int = 1) -> int:
        sector_id = int(sector_id)
        delta = max(1, int(delta))
        s = self.get_sector(sector_id)
        if not s:
            raise ValueError("sector not found")
        if str(s.get("owner_player_id") or "") != str(player_id):
            raise ValueError("must own sector to upgrade defenses")

        cur = int(s.get("defense_level", 0))
        nxt = min(25, cur + delta)
        # Cost scales with level.
        credits = 120 + nxt * 30
        ore = 10 + nxt * 3
        crystal = 6 + nxt * 2
        p = self.get_player(player_id)
        if not p:
            raise ValueError("player not found")
        if int(p["credits"]) < credits or int(p["ore"]) < ore or int(p["crystal"]) < crystal:
            raise ValueError("insufficient resources to upgrade defenses")

        self.update_player_resources(player_id, -credits, -ore, 0, -crystal)
        self.db.execute("UPDATE sectors SET defense_level=? WHERE sector_id=?", (nxt, sector_id))
        self.db.commit()
        return nxt

    def record_battle(self, attacker: str, defender: str, winner: str, damage_a: int, damage_d: int, sector_id: int, summary: str) -> None:
        self.db.execute(
            "INSERT INTO battles(ts,attacker,defender,winner,damage_attacker,damage_defender,sector_id,summary) VALUES(?,?,?,?,?,?,?,?)",
            (time.time(), attacker, defender, winner, damage_a, damage_d, sector_id, summary),
        )
        self.db.commit()

    def recent_battles(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM battles ORDER BY battle_id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
