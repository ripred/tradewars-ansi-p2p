from __future__ import annotations

import asyncio
import socket
from typing import Optional


class _QueueProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue[tuple[bytes, tuple[str, int]]]):
        self.queue = queue

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.queue.put_nowait((data, addr))


class UDPTransport:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.queue: asyncio.Queue[tuple[bytes, tuple[str, int]]] = asyncio.Queue(maxsize=10000)
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[_QueueProtocol] = None

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind((self.host, self.port))
        sock.setblocking(False)
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _QueueProtocol(self.queue),
            sock=sock,
        )
        self._transport = transport
        self._protocol = protocol

    async def recv(self) -> tuple[bytes, tuple[str, int]]:
        return await self.queue.get()

    def send(self, data: bytes, addr: tuple[str, int]) -> None:
        if self._transport is None:
            return
        self._transport.sendto(data, addr)

    def broadcast(self, data: bytes, port: int) -> None:
        self.send(data, ("255.255.255.255", port))

    async def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
