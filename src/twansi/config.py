from __future__ import annotations

import json
import os
import secrets
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

from twansi.policy import derive_shard_key, load_policy


@dataclass
class Profile:
    nick: str
    listen_host: str = "0.0.0.0"
    listen_port: int = 39000
    shard: str = "alpha"
    seed_peers: list[str] = field(default_factory=list)
    bootstrap_url: str = ""
    secret: str = ""
    shard_key: str = ""
    data_dir: str = ""
    db_path: str = ""

    def __post_init__(self) -> None:
        if not self.secret:
            self.secret = secrets.token_hex(32)
        if not self.shard_key:
            # Default shared auth key derived from repo policy epoch.
            # Operators can add a private salt via TWANSI_SHARD_SECRET to prevent casual spoofing.
            pol = load_policy()
            self.shard_key = derive_shard_key(self.shard, pol.protocol_epoch)
        if not self.bootstrap_url:
            self.bootstrap_url = os.environ.get(\"TWANSI_BOOTSTRAP_URL\", \"https://twansi.trentwyatt.com/bootstrap.json\")


def twansi_home() -> Path:
    root = os.environ.get("TWANSI_HOME")
    if root:
        p = Path(root).expanduser().resolve()
    else:
        p = Path.home() / ".twansi"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profile_path(home: Path | None = None) -> Path:
    h = home or twansi_home()
    return h / "profile.json"


def parse_listen(value: str) -> tuple[str, int]:
    host, port = value.rsplit(":", 1)
    return host, int(port)


def save_profile(profile: Profile, home: Path | None = None) -> Path:
    h = home or twansi_home()
    h.mkdir(parents=True, exist_ok=True)
    if not profile.data_dir:
        profile.data_dir = str(h)
    if not profile.db_path:
        profile.db_path = str(h / "twansi.db")
    p = profile_path(h)
    p.write_text(json.dumps(asdict(profile), indent=2), encoding="utf-8")
    return p


def load_profile(home: Path | None = None) -> Profile:
    p = profile_path(home)
    data = json.loads(p.read_text(encoding="utf-8"))
    return Profile(**data)
