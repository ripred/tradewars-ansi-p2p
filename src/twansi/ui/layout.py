from __future__ import annotations


def split_rect(max_y: int, max_x: int) -> dict[str, tuple[int, int, int, int]]:
    top_h = max(10, max_y // 2)
    left_w = max(32, max_x // 2)
    return {
        "player": (0, 0, top_h, left_w),
        "metrics": (0, left_w, top_h, max_x - left_w),
        "radar": (top_h, 0, max_y - top_h, left_w),
        "events": (top_h, left_w, max_y - top_h, max_x - left_w),
    }
