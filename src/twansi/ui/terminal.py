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
        try:
            win.box()
            win.attron(curses.color_pair(color_pair))
            win.addnstr(0, 2, f" {title} ", max(0, win.getmaxyx()[1] - 4))
            win.attroff(curses.color_pair(color_pair))
        except curses.error:
            pass

    def _draw_lines(self, win: curses.window, lines: list[str], color_pair: int = 0) -> None:
        h, w = win.getmaxyx()
        for i, line in enumerate(lines[: h - 2]):
            if color_pair:
                win.attron(curses.color_pair(color_pair))
            try:
                win.addnstr(i + 1, 1, line.ljust(max(0, w - 2)), max(0, w - 2))
            except curses.error:
                # Terminal can be resized smaller than our layout; avoid crashing.
                pass
            if color_pair:
                win.attroff(curses.color_pair(color_pair))

    @staticmethod
    def _format_seconds(value: float) -> str:
        value = max(0.0, value)
        if value >= 60.0:
            mins = int(value // 60)
            secs = int(value % 60)
            return f"{mins}m{secs:02d}s"
        return f"{value:4.1f}s"

    @staticmethod
    def _draw_progress_bar(
        win: curses.window, row: int, label: str, percent: float, suffix: str, color_pair: int
    ) -> None:
        h, w = win.getmaxyx()
        if row >= h - 1 or w < 10:
            return
        percent = max(0.0, min(1.0, percent))
        label_field = label[:12].ljust(12)
        prefix = f"{label_field} "
        suffix_text = suffix or ""
        available = max(4, w - len(prefix) - len(suffix_text) - 6)
        fill = int(round(percent * available))
        fill = min(available, max(0, fill))
        empty = available - fill
        bar = "[" + "#" * fill + "." * empty + "]"

        try:
            win.addnstr(row, 1, prefix, max(0, min(len(prefix), w - 2)))
        except curses.error:
            pass

        bar_col = 1 + len(prefix)
        try:
            win.attron(curses.color_pair(color_pair) | curses.A_BOLD)
            win.addnstr(row, bar_col, bar, max(0, min(len(bar), w - 2 - len(prefix))))
        except curses.error:
            pass
        finally:
            win.attroff(curses.color_pair(color_pair) | curses.A_BOLD)

        if suffix_text:
            suffix_col = bar_col + len(bar) + 1
            if suffix_col < w - 1:
                try:
                    win.attron(curses.A_DIM)
                    win.addnstr(row, suffix_col, suffix_text, max(0, w - suffix_col - 1))
                except curses.error:
                    pass
                finally:
                    win.attroff(curses.A_DIM)

    def _draw_progress_bars(self, win: curses.window, bars: list[tuple[str, float, str, int]]) -> None:
        h, _ = win.getmaxyx()
        start_row = max(1, h - len(bars) - 1)
        for idx, (label, percent, suffix, color) in enumerate(bars):
            self._draw_progress_bar(win, start_row + idx, label, percent, suffix, color)

    def _build_progress_bars(self, metrics: dict[str, Any], player: dict[str, Any]) -> list[tuple[str, float, str, int]]:
        bars: list[tuple[str, float, str, int]] = []
        ap = int(player.get("ap", 0) or 0)
        ap_max = int(metrics.get("ap_max", 200) or 200)
        ap_next = float(metrics.get("ap_next_in", 0.0) or 0.0)
        if ap_max > 0:
            ap_pct = min(1.0, max(0.0, ap / ap_max))
        else:
            ap_pct = 1.0
        if ap >= ap_max:
            ap_suffix = f"{ap}/{ap_max} full"
        else:
            ap_suffix = f"{ap}/{ap_max} ({self._format_seconds(ap_next)} to next)"
        bars.append(("AP", ap_pct, ap_suffix, Palette.GOOD))
        timers = metrics.get("timers", {})
        timer_specs = [
            ("Resource", "resource", Palette.RADAR),
            ("Strategic", "strategic", Palette.WARN),
            ("Movement", "movement", Palette.EVENT),
        ]
        for label, key, color in timer_specs:
            timer = timers.get(key)
            if not timer:
                continue
            remaining = float(timer.get("remaining", 0.0) or 0.0)
            period = float(timer.get("period", 1.0) or 1.0)
            progress = 1.0 - min(1.0, max(0.0, remaining / period)) if period > 0 else 1.0
            suffix = f"{self._format_seconds(remaining)}"
            bars.append((label, progress, suffix, color))
        return bars

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
            stdscr.erase()

            # Compact fallback for tiny panes (e.g. tmux splits). Avoid negative/too-small windows.
            if max_y < 18 or max_x < 56:
                self._draw_box(stdscr, "TWANSI (resize for full HUD)", Palette.TITLE)
                state = self.state_cb()
                for ev in state.get("new_events", []):
                    self.push_event(ev)
                lines = []
                lines.extend(player_summary(state.get("player", {})))
                lines.append("")
                lines.extend(metrics_summary(state.get("metrics", {})))
                lines.append("")
                lines.append("Events:")
                lines.extend(list(self.events)[: max(0, max_y - len(lines) - 3)])
                self._draw_lines(stdscr, lines, Palette.WARN)
                stdscr.refresh()
                continue

            rects = split_rect(max_y, max_x)
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
            metrics = state.get("metrics", {})
            mlines = metrics_summary(metrics)
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
            port = state.get("port", None)
            if port:
                pc = port.get("port_class", "?")
                prices = port.get("prices", {})
                mlines.append(
                    f"Port {pc}  O:{prices.get('ore',{}).get('bid',0)}/{prices.get('ore',{}).get('ask',0)} "
                    f"G:{prices.get('gas',{}).get('bid',0)}/{prices.get('gas',{}).get('ask',0)} "
                    f"C:{prices.get('crystal',{}).get('bid',0)}/{prices.get('crystal',{}).get('ask',0)}"
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
                mlines.extend(
                    [
                        "",
                        "Keys: q quit | m mine | a attack | s scan | i invite | d digest | b/n ore buy/sell | f/r gas buy/sell | c/v crystal buy/sell | u upgrade | j jump | g defense | +/- zoom | h help",
                    ]
                )
            bars = self._build_progress_bars(metrics, state.get("player", {}))
            reserved_rows = len(bars) + 1 if bars else 0
            text_limit = max(0, mh - 2 - reserved_rows)
            self._draw_lines(w_metrics, mlines[:text_limit], Palette.WARN)
            if bars:
                self._draw_progress_bars(w_metrics, bars)

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
                timestamp=state.get("timestamp"),
            )
            self._draw_lines(w_radar, radar_lines, Palette.RADAR)

            self._draw_box(w_events, "EVENTS", Palette.TITLE)
            self._draw_lines(w_events, list(self.events)[: max(1, eh - 2)], Palette.EVENT)

            stdscr.refresh()
