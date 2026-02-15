from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class Store:
    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init()

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
                sector INTEGER NOT NULL,
                pos_x REAL NOT NULL DEFAULT 0,
                pos_y REAL NOT NULL DEFAULT 0,
                vel_x REAL NOT NULL DEFAULT 0,
                vel_y REAL NOT NULL DEFAULT 0,
                alliance_id TEXT,
                updated_ts REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sectors (
                sector_id INTEGER PRIMARY KEY,
                owner_player_id TEXT,
                richness INTEGER NOT NULL,
                danger INTEGER NOT NULL
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
            CREATE TABLE IF NOT EXISTS tech_tree (
                player_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                level INTEGER NOT NULL,
                PRIMARY KEY(player_id, domain)
            );
            """
        )
        self._migrate_players_table()
        self._init_market()
        self.db.commit()

    def _migrate_players_table(self) -> None:
        cols = {row[1] for row in self.db.execute("PRAGMA table_info(players)").fetchall()}
        required = {
            "pos_x": "ALTER TABLE players ADD COLUMN pos_x REAL NOT NULL DEFAULT 0",
            "pos_y": "ALTER TABLE players ADD COLUMN pos_y REAL NOT NULL DEFAULT 0",
            "vel_x": "ALTER TABLE players ADD COLUMN vel_x REAL NOT NULL DEFAULT 0",
            "vel_y": "ALTER TABLE players ADD COLUMN vel_y REAL NOT NULL DEFAULT 0",
        }
        for col, stmt in required.items():
            if col not in cols:
                self.db.execute(stmt)

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
        for domain in ("ship_hull", "weapons", "shields", "mining", "defense_grid"):
            self.db.execute(
                "INSERT OR IGNORE INTO tech_tree(player_id,domain,level) VALUES(?,?,?)",
                (player_id, domain, 0),
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
            "UPDATE players SET pos_x=?, pos_y=?, vel_x=?, vel_y=?, updated_ts=? WHERE player_id=?",
            (pos_x, pos_y, vel_x, vel_y, time.time(), player_id),
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
            "INSERT OR IGNORE INTO sectors(sector_id,owner_player_id,richness,danger) VALUES(?,?,?,?)",
            (sector_id, None, richness, danger),
        )
        self.db.commit()

    def get_sector(self, sector_id: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM sectors WHERE sector_id=?", (sector_id,)).fetchone()
        return dict(row) if row else None

    def claim_sector(self, sector_id: int, owner_player_id: str) -> None:
        self.db.execute("UPDATE sectors SET owner_player_id=? WHERE sector_id=?", (owner_player_id, sector_id))
        self.db.commit()

    def record_battle(self, attacker: str, defender: str, winner: str, damage_a: int, damage_d: int, sector_id: int, summary: str) -> None:
        self.db.execute(
            "INSERT INTO battles(ts,attacker,defender,winner,damage_attacker,damage_defender,sector_id,summary) VALUES(?,?,?,?,?,?,?,?)",
            (time.time(), attacker, defender, winner, damage_a, damage_d, sector_id, summary),
        )
        self.db.commit()

    def recent_battles(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM battles ORDER BY battle_id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
