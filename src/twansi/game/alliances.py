from __future__ import annotations

import time
import uuid

from twansi.state.store_sqlite import Store


def create_alliance(store: Store, name: str, owner_player_id: str) -> str:
    alliance_id = uuid.uuid4().hex[:12]
    store.create_alliance(alliance_id, name, owner_player_id)
    return alliance_id


def join_alliance(store: Store, alliance_id: str, player_id: str) -> None:
    store.db.execute(
        "INSERT OR REPLACE INTO alliance_members(alliance_id,player_id,role) VALUES(?,?,?)",
        (alliance_id, player_id, "member"),
    )
    store.db.execute("UPDATE players SET alliance_id=? WHERE player_id=?", (alliance_id, player_id))
    store.db.commit()


def player_alliance(store: Store, player_id: str) -> str | None:
    row = store.db.execute("SELECT alliance_id FROM players WHERE player_id=?", (player_id,)).fetchone()
    if not row:
        return None
    return row[0]


def deterministic_alliance_id(owner_player_id: str, name: str, shard: str, epoch: int) -> str:
    import hashlib

    material = f"twansi-alliance|{shard}|{int(epoch)}|{owner_player_id}|{name}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:12]
