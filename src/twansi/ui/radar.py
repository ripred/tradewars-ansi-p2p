from __future__ import annotations

from typing import Sequence


def build_radar(
    width: int,
    height: int,
    sector: int,
    center_x: float,
    center_y: float,
    contacts: Sequence[dict[str, float | str]],
    zoom: float,
) -> list[str]:
    width = max(12, width)
    height = max(6, height)
    grid = [["." for _ in range(width)] for _ in range(height)]
    cx, cy = width // 2, height // 2
    grid[cy][cx] = "@"

    z = max(0.25, min(4.0, zoom))
    for c in contacts[: max(1, (width * height) // 10)]:
        dx = float(c.get("x", 0.0)) - center_x
        dy = float(c.get("y", 0.0)) - center_y
        sx = int(cx + dx / z)
        sy = int(cy + dy / z)
        if 0 <= sx < width and 0 <= sy < height:
            grid[sy][sx] = "*"

    lines = ["".join(row) for row in grid]
    lines[0] = f"sec:{sector} z:{z:.2f}".ljust(width, "-")[:width]
    return lines
