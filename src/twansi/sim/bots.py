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


def run_bot(host: str, port: int, seconds: int, aggressiveness: float) -> None:
    end = time.time() + seconds
    actions = ["mine", "scan", "attack", "observe"]
    while time.time() < end:
        choice = random.random()
        if choice < aggressiveness:
            action = "attack"
        elif choice < 0.55:
            action = "mine"
        elif choice < 0.8:
            action = "scan"
        else:
            action = "observe"
        if action == "observe":
            resp = send_cmd(host, port, {"cmd": "observe"})
        else:
            resp = send_cmd(host, port, {"cmd": "act", "action": action})
        status = "ok" if resp.get("ok") else "err"
        print(f"[{status}] {action}: {resp.get('result') or resp.get('error')}")
        time.sleep(random.uniform(0.25, 1.2))


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
