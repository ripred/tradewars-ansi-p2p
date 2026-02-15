from __future__ import annotations

import curses


def read_key(stdscr: curses.window) -> str | None:
    try:
        ch = stdscr.getch()
    except Exception:
        return None
    if ch == -1:
        return None
    if ch in (curses.KEY_BACKSPACE, 127, 8):
        return "backspace"
    if ch in (10, 13):
        return "enter"
    if 0 <= ch < 256:
        return chr(ch)
    return None
