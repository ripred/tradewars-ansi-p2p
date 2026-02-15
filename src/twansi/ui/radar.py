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
    timestamp: float | None = None,
) -> list[str]:
    width = max(12, width)
    height = max(6, height)
    grid = [["." for _ in range(width)] for _ in range(height)]
    cx, cy = width // 2, height // 2
    grid[cy][cx] = "@"

    z = max(0.25, min(4.0, zoom))
    ts = float(timestamp) if timestamp is not None else None
    for c in contacts[: max(1, (width * height) // 10)]:
        base_x = c.get("pos_x")
        base_y = c.get("pos_y")
        vx = float(c.get("vel_x", 0.0))
        vy = float(c.get("vel_y", 0.0))
        target_x = float(base_x if base_x is not None else c.get("x", 0.0))
        target_y = float(base_y if base_y is not None else c.get("y", 0.0))
        if ts is not None and base_x is not None and base_y is not None:
            motion_ts = float(c.get("motion_ts", 0.0) or 0.0)
            if motion_ts > 0:
                dt = max(0.0, min(10.0, ts - motion_ts))
                target_x = float(base_x) + vx * dt
                target_y = float(base_y) + vy * dt
        dx = target_x - center_x
        dy = target_y - center_y
        sx = int(cx + dx / z)
        sy = int(cy + dy / z)
        if 0 <= sx < width and 0 <= sy < height:
            grid[sy][sx] = "*"

    lines = ["".join(row) for row in grid]
    lines[0] = f"sec:{sector} z:{z:.2f}".ljust(width, "-")[:width]
    return lines
