from __future__ import annotations

import argparse
import json
import random
import socket
import time


def send_cmd(host: str, port: int, cmd: dict) -> dict:
    s = socket.create_connection((host, port), timeout=2.0)
    with s:
        s.sendall((json.dumps(cmd) + "\n").encode("utf-8"))
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(8192)
            if not chunk:
                break
            data += chunk
    if not data:
        return {"ok": False, "error": "no response"}
    return json.loads(data.decode("utf-8").strip())


def act(host: str, port: int, action: str, args: dict | None = None) -> dict:
    return send_cmd(host, port, {"cmd": "act", "action": action, "args": args or {}})


def run_bot(host: str, port: int, seconds: int, aggressiveness: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        obs = send_cmd(host, port, {"cmd": "observe"})
        if not obs.get("ok"):
            print(f"[err] observe: {obs.get('error')}")
            time.sleep(0.6)
            continue

        st = obs["result"]
        p = st.get("player", {}) or {}
        ap = int(p.get("ap", 0) or 0)
        sector_id = int(p.get("sector", 1) or 1)
        contacts = st.get("contacts") or []
        tech_tree = (st.get("tech") or {}).get("tree") or {}
        missions = st.get("missions") or []

        # 1) Try to claim missions in current sector.
        did = False
        for m in missions:
            if m.get("claimed"):
                continue
            if int(m.get("target_sector", 0) or 0) != sector_id:
                continue
            kind = str(m.get("kind", ""))
            if kind == "survey" and ap >= 1:
                r = act(host, port, "scan")
                print(f"[{'ok' if r.get('ok') else 'err'}] survey/scan")
                did = True
            elif kind == "supply" and ap >= 1:
                for res in ("ore", "gas", "crystal"):
                    if int(p.get(res, 0) or 0) >= 30:
                        r = act(host, port, "sell", {"resource": res, "qty": 10})
                        print(f"[{'ok' if r.get('ok') else 'err'}] supply/sell {res}")
                        did = True
                        break
            elif kind == "raid" and ap >= 3 and contacts:
                target = str((contacts[0] or {}).get("id", ""))[:8]
                r = act(host, port, "attack", {"target": target})
                print(f"[{'ok' if r.get('ok') else 'err'}] raid/attack {target}")
                did = True
            if did:
                break
        if did:
            time.sleep(random.uniform(0.25, 0.9))
            continue

        # 2) Upgrade when ready.
        if ap >= 2 and random.random() < 0.35:
            ready = [k for k, v in tech_tree.items() if isinstance(v, dict) and v.get("upgrade_ready")]
            if ready:
                r = act(host, port, "upgrade", {"domain": sorted(ready)[0]})
                print(f"[{'ok' if r.get('ok') else 'err'}] upgrade")
                time.sleep(random.uniform(0.25, 0.9))
                continue

        # 3) Combat occasionally if contacts are visible.
        if ap >= 3 and contacts and random.random() < aggressiveness:
            target = str((contacts[0] or {}).get("id", ""))[:8]
            r = act(host, port, "attack", {"target": target})
            print(f"[{'ok' if r.get('ok') else 'err'}] attack {target}")
            time.sleep(random.uniform(0.25, 0.9))
            continue

        # 4) Otherwise: mine, scan, or jump toward a mission target.
        roll = random.random()
        if ap >= 1 and roll < 0.55:
            r = act(host, port, "mine")
            print(f"[{'ok' if r.get('ok') else 'err'}] mine")
        elif roll < 0.8:
            r = act(host, port, "scan")
            print(f"[{'ok' if r.get('ok') else 'err'}] scan")
        else:
            target_sector = 0
            unclaimed = [m for m in missions if not m.get("claimed")]
            if unclaimed:
                target_sector = int(unclaimed[0].get("target_sector", 0) or 0)
            r = act(host, port, "jump", {"sector": target_sector})
            print(f"[{'ok' if r.get('ok') else 'err'}] jump")

        time.sleep(random.uniform(0.25, 1.1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="twansi agent bot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=39100)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--aggressiveness", type=float, default=0.35)
    args = parser.parse_args(argv)
    run_bot(args.host, args.port, args.seconds, args.aggressiveness)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

