from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

from twansi.game.combat2 import resolve_battle_v2
from twansi.game.economy import mine_burst, production_for_sector
from twansi.game.rules import MAX_HP
from twansi.game.tech import tech_effects
from twansi.game.ship import ship_stats
from twansi.state.store_sqlite import Store


@dataclass
class TickResult:
    events: list[dict[str, Any]]
    tick_ms: float


class GameEngine:
    def __init__(self, store: Store):
        self.store = store

    def resource_tick_for_player(self, player_id: str) -> dict[str, Any] | None:
        player = self.store.get_player(player_id)
        if not player:
            return None
        sector = self.store.get_sector(int(player["sector"])) or {"richness": 3}
        prod = production_for_sector(int(sector.get("richness", 3)), str(player["doctrine"]))
        levels = self.store.get_tech_levels(player_id)
        fx = tech_effects(levels)
        prod["ore"] = int(round(prod["ore"] * fx["mining_bonus"]))
        prod["gas"] = int(round(prod["gas"] * fx["mining_bonus"]))
        prod["crystal"] = int(round(prod["crystal"] * fx["mining_bonus"]))
        self.store.update_player_resources(
            player_id,
            credits=prod["credits"],
            ore=prod["ore"],
            gas=prod["gas"],
            crystal=prod["crystal"],
        )
        return {
            "event_type": "resource_tick",
            "payload": {
                "player_id": player_id,
                **prod,
            },
        }

    def mine_burst_for_player(self, player_id: str) -> dict[str, Any] | None:
        player = self.store.get_player(player_id)
        if not player:
            return None
        delta = mine_burst()
        levels = self.store.get_tech_levels(player_id)
        fx = tech_effects(levels)
        delta["ore"] = int(round(delta["ore"] * fx["mining_bonus"]))
        delta["gas"] = int(round(delta["gas"] * fx["mining_bonus"]))
        delta["crystal"] = int(round(delta["crystal"] * fx["mining_bonus"]))
        self.store.update_player_resources(
            player_id,
            credits=delta["credits"],
            ore=delta["ore"],
            gas=delta["gas"],
            crystal=delta["crystal"],
        )
        return {
            "event_type": "mine_burst",
            "payload": {
                "player_id": player_id,
                **delta,
            },
        }

    def random_battle_for_player(self, player_id: str) -> dict[str, Any] | None:
        players = self.store.list_players()
        if len(players) < 2:
            return None
        attacker = next((p for p in players if p["player_id"] == player_id), None)
        if not attacker:
            return None
        targets = [p for p in players if p["player_id"] != player_id]
        defender = random.choice(targets)
        sector_id = int(attacker["sector"])
        sector = self.store.get_sector(sector_id)
        atk_lv = self.store.get_tech_levels(attacker["player_id"])
        def_lv = self.store.get_tech_levels(defender["player_id"])
        atk_ship = ship_stats(attacker, atk_lv)
        def_ship = ship_stats(defender, def_lv)
        result = resolve_battle_v2(attacker, defender, sector, atk_ship, def_ship)

        self.store.update_player_resources(attacker["player_id"], 0, 0, 0, 0, hp=result["attacker_hp"])
        self.store.update_player_resources(defender["player_id"], 0, 0, 0, 0, hp=result["defender_hp"])
        self.store.db.execute(
            "UPDATE players SET shield=? WHERE player_id=?",
            (int(result["attacker_shield_after"]), attacker["player_id"]),
        )
        self.store.db.execute(
            "UPDATE players SET shield=? WHERE player_id=?",
            (int(result["defender_shield_after"]), defender["player_id"]),
        )
        self.store.db.commit()

        if result["winner"] == attacker["player_id"]:
            self.store.claim_sector(sector_id, attacker["player_id"])

        self.store.record_battle(
            result["attacker"],
            result["defender"],
            result["winner"],
            result["damage_attacker"],
            result["damage_defender"],
            result["sector_id"],
            result["summary"],
        )

        player_damage = result["damage_attacker"] if player_id == attacker["player_id"] else result["damage_defender"]
        return {
            "event_type": "battle",
            "payload": {
                **result,
                "damage_taken_by_player": player_damage,
            },
        }

    def heal_tick(self, player_id: str) -> dict[str, Any] | None:
        p = self.store.get_player(player_id)
        if not p:
            return None
        hp = int(p["hp"])
        if hp >= MAX_HP:
            return None
        new_hp = min(MAX_HP, hp + 2)
        self.store.update_player_resources(player_id, 0, 0, 0, 0, hp=new_hp)
        return {
            "event_type": "repair_tick",
            "payload": {
                "player_id": player_id,
                "hp_before": hp,
                "hp_after": new_hp,
            },
        }

    def movement_tick(self, player_id: str) -> dict[str, Any] | None:
        p = self.store.get_player(player_id)
        if not p:
            return None
        x = float(p.get("pos_x", 0.0))
        y = float(p.get("pos_y", 0.0))
        vx = float(p.get("vel_x", 0.0))
        vy = float(p.get("vel_y", 0.0))

        vx += random.uniform(-0.25, 0.25)
        vy += random.uniform(-0.25, 0.25)
        vx = max(-2.0, min(2.0, vx))
        vy = max(-2.0, min(2.0, vy))
        x += vx
        y += vy

        if x < -120 or x > 120:
            vx *= -0.8
            x = max(-120, min(120, x))
        if y < -120 or y > 120:
            vy *= -0.8
            y = max(-120, min(120, y))

        self.store.set_player_motion(player_id, x, y, vx, vy)
        return {
            "event_type": "movement",
            "payload": {
                "player_id": player_id,
                "x": round(x, 3),
                "y": round(y, 3),
                "vx": round(vx, 3),
                "vy": round(vy, 3),
            },
        }

    def strategic_tick(self, player_id: str) -> TickResult:
        start = time.perf_counter()
        events: list[dict[str, Any]] = []
        heal = self.heal_tick(player_id)
        if heal:
            events.append(heal)
        # Shield regen: slow baseline, faster if you have crystal.
        p = self.store.get_player(player_id)
        if p:
            levels = self.store.get_tech_levels(player_id)
            stats = ship_stats(p, levels)
            shield_max = int(stats.get("shield_max", 0))
            shield = int(p.get("shield", 0))
            if shield < shield_max:
                use_crystal = int(p.get("crystal", 0)) > 0 and (shield_max - shield) > 6
                inc = 4 if use_crystal else 1
                if use_crystal:
                    self.store.update_player_resources(player_id, 0, 0, 0, -1)
                new_shield = min(shield_max, shield + inc)
                self.store.db.execute("UPDATE players SET shield=? WHERE player_id=?", (new_shield, player_id))
                self.store.db.commit()
                events.append(
                    {
                        "event_type": "shield_regen",
                        "payload": {"player_id": player_id, "before": shield, "after": new_shield},
                    }
                )
        movement = self.movement_tick(player_id)
        if movement:
            events.append(movement)
        tick_ms = (time.perf_counter() - start) * 1000
        return TickResult(events=events, tick_ms=tick_ms)
