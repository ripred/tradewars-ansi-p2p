from __future__ import annotations

import curses


class Palette:
    @staticmethod
    def init() -> None:
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)
        curses.init_pair(6, curses.COLOR_BLUE, -1)

    TITLE = 1
    GOOD = 2
    WARN = 3
    BAD = 4
    EVENT = 5
    RADAR = 6
