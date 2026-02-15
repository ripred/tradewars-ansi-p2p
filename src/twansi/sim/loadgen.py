from __future__ import annotations

import asyncio
import json
import random


async def _bot(host: str, port: int, actions: int) -> None:
    for _ in range(actions):
        reader, writer = await asyncio.open_connection(host, port)
        cmd = {"cmd": "act", "action": random.choice(["mine", "scan", "attack"]) }
        writer.write((json.dumps(cmd) + "\n").encode("utf-8"))
        await writer.drain()
        await reader.readline()
        writer.close()
        await writer.wait_closed()
        await asyncio.sleep(random.uniform(0.02, 0.2))


async def run_load(host: str, port: int, bots: int = 12, actions: int = 100) -> None:
    await asyncio.gather(*[_bot(host, port, actions) for _ in range(bots)])
