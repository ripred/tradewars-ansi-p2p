from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Bootstrap:
    seeds: tuple[str, ...]
    shards: tuple[str, ...]
    updated_ts: float


def _parse_bootstrap(d: dict[str, Any]) -> Bootstrap:
    seeds = tuple(str(x) for x in (d.get("seeds") or []) if x)
    shards = tuple(str(x) for x in (d.get("shards") or []) if x)
    updated = float(d.get("updated_ts") or d.get("updated") or time.time())
    return Bootstrap(seeds=seeds, shards=shards, updated_ts=updated)


def read_cached(cache_path: Path, max_age_s: float = 3600.0) -> Bootstrap | None:
    try:
        st = cache_path.stat()
    except FileNotFoundError:
        return None
    if time.time() - st.st_mtime > max_age_s:
        return None
    try:
        d = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _parse_bootstrap(d)


def write_cached(cache_path: Path, b: Bootstrap) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"seeds": list(b.seeds), "shards": list(b.shards), "updated_ts": b.updated_ts}, indent=2),
        encoding="utf-8",
    )


def fetch_bootstrap(url: str, timeout_s: float = 2.5) -> Bootstrap:
    req = urllib.request.Request(url, headers={"User-Agent": "twansi/0.1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    d = json.loads(raw.decode("utf-8"))
    return _parse_bootstrap(d)


def merge_seeds(existing: list[str], new_seeds: tuple[str, ...], max_total: int = 64) -> list[str]:
    # Preserve ordering of existing seeds, append new ones.
    out: list[str] = []
    seen: set[str] = set()
    for s in existing + list(new_seeds):
        s = str(s).strip()
        if not s or s in seen:
            continue
        out.append(s)
        seen.add(s)
        if len(out) >= max_total:
            break
    return out


def dns_srv_seeds(domain: str, service: str = "_twansi", proto: str = "_udp") -> tuple[str, ...]:
    # Optional dependency: dnspython. If not present, return empty.
    try:
        import dns.resolver  # type: ignore
    except Exception:
        return ()

    name = f"{service}.{proto}.{domain}".rstrip(".")
    try:
        answers = dns.resolver.resolve(name, "SRV")
    except Exception:
        return ()

    seeds: list[str] = []
    for r in answers:
        try:
            host = str(r.target).rstrip(".")
            port = int(r.port)
            seeds.append(f"{host}:{port}")
        except Exception:
            continue
    return tuple(seeds)
