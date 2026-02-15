from __future__ import annotations

import curses
import time
from collections import deque
from typing import Any, Callable

from .input import read_key
from .layout import split_rect
from .palette import Palette
from .panels import metrics_summary, player_summary
from .radar import build_radar


class Dashboard:
    def __init__(self, state_cb: Callable[[], dict[str, Any]], command_cb: Callable[[str], None]):
        self.state_cb = state_cb
        self.command_cb = command_cb
        self.events: deque[str] = deque(maxlen=200)
        self.show_help = True

    def push_event(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.events.appendleft(f"[{stamp}] {text}")

    def run(self) -> None:
        curses.wrapper(self._loop)

    def _draw_box(self, win: curses.window, title: str, color_pair: int) -> None:
        win.box()
        win.attron(curses.color_pair(color_pair))
        win.addnstr(0, 2, f" {title} ", win.getmaxyx()[1] - 4)
        win.attroff(curses.color_pair(color_pair))

    def _draw_lines(self, win: curses.window, lines: list[str], color_pair: int = 0) -> None:
        h, w = win.getmaxyx()
        for i, line in enumerate(lines[: h - 2]):
            if color_pair:
                win.attron(curses.color_pair(color_pair))
            win.addnstr(i + 1, 1, line.ljust(w - 2), w - 2)
            if color_pair:
                win.attroff(curses.color_pair(color_pair))

    def _loop(self, stdscr: curses.window) -> None:
        stdscr.nodelay(True)
        stdscr.timeout(0)
        curses.curs_set(0)
        Palette.init()
        last = 0.0

        while True:
            key = read_key(stdscr)
            if key:
                if key == "q":
                    self.command_cb("quit")
                    return
                if key == "h":
                    self.show_help = not self.show_help
                elif key in ("+", "="):
                    self.command_cb("zoom_in")
                elif key == "-":
                    self.command_cb("zoom_out")
                else:
                    self.command_cb(key)

            now = time.time()
            if now - last < 1 / 20:
                time.sleep(0.005)
                continue
            last = now

            state = self.state_cb()
            for ev in state.get("new_events", []):
                self.push_event(ev)

            max_y, max_x = stdscr.getmaxyx()
            rects = split_rect(max_y, max_x)
            stdscr.erase()

            py, px, ph, pw = rects["player"]
            my, mx, mh, mw = rects["metrics"]
            ry, rx, rh, rw = rects["radar"]
            ey, ex, eh, ew = rects["events"]

            w_player = stdscr.derwin(ph, pw, py, px)
            w_metrics = stdscr.derwin(mh, mw, my, mx)
            w_radar = stdscr.derwin(rh, rw, ry, rx)
            w_events = stdscr.derwin(eh, ew, ey, ex)

            self._draw_box(w_player, "CAPTAIN", Palette.TITLE)
            self._draw_lines(w_player, player_summary(state.get("player", {})), Palette.GOOD)

            self._draw_box(w_metrics, "DASHBOARD", Palette.TITLE)
            mlines = metrics_summary(state.get("metrics", {}))
            prices = state.get("market", {}).get("prices", {})
            if prices:
                mlines.append(f"Market O:{prices.get('ore',0)} G:{prices.get('gas',0)} C:{prices.get('crystal',0)}")
            station = state.get("station", {})
            if station:
                sp = station.get("prices", {})
                st = station.get("stock", {})
                mlines.append(
                    f"Station(sec {station.get('sector_id','?')}) O:{sp.get('ore',0)}/{st.get('ore',0)} "
                    f"G:{sp.get('gas',0)}/{st.get('gas',0)} C:{sp.get('crystal',0)}/{st.get('crystal',0)}"
                )
            nav = state.get("nav", {}).get("warps", [])
            if nav:
                mlines.append("Warps: " + ",".join(str(x) for x in nav[:12]) + (" ..." if len(nav) > 12 else ""))
            tech_levels = state.get("tech", {}).get("levels", {})
            if tech_levels:
                mlines.append(
                    "Tech H:{ship_hull} W:{weapons} S:{shields} M:{mining} D:{defense_grid}".format(
                        ship_hull=tech_levels.get("ship_hull", 0),
                        weapons=tech_levels.get("weapons", 0),
                        shields=tech_levels.get("shields", 0),
                        mining=tech_levels.get("mining", 0),
                        defense_grid=tech_levels.get("defense_grid", 0),
                    )
                )
            ship = state.get("ship", {})
            if ship:
                mlines.append(
                    f"Ship HPmax:{ship.get('max_hp',0)} Cargo:{ship.get('cargo_used',0)}/{ship.get('cargo_capacity',0)} "
                    f"Spd:{ship.get('speed',1.0)}"
                )
            if self.show_help:
                mlines.extend(["", "Keys: q quit | m mine | a attack | s scan | i invite | d digest | b buy ore | n sell ore | u upgrade | j jump | +/- zoom | h help"])
            self._draw_lines(w_metrics, mlines, Palette.WARN)

            self._draw_box(w_radar, "RADAR", Palette.TITLE)
            player = state.get("player", {})
            radar_lines = build_radar(
                max(8, rw - 2),
                max(4, rh - 2),
                player.get("sector", 0),
                float(player.get("pos_x", 0.0)),
                float(player.get("pos_y", 0.0)),
                state.get("contacts", []),
                float(state.get("metrics", {}).get("radar_zoom", 1.0)),
            )
            self._draw_lines(w_radar, radar_lines, Palette.RADAR)

            self._draw_box(w_events, "EVENTS", Palette.TITLE)
            self._draw_lines(w_events, list(self.events)[: max(1, eh - 2)], Palette.EVENT)

            stdscr.refresh()
