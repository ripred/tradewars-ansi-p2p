from __future__ import annotations

from typing import Any


def player_summary(player: dict[str, Any]) -> list[str]:
    return [
        f"{player.get('nick','?')}  [{player.get('player_id','')[:8]}]",
        f"Doctrine: {player.get('doctrine','assault')}",
        f"HP: {player.get('hp',0)}    Sector: {player.get('sector',0)}",
        f"Credits: {player.get('credits',0)}",
        f"Ore: {player.get('ore',0)}  Gas: {player.get('gas',0)}  Crystal: {player.get('crystal',0)}",
        f"Alliance: {player.get('alliance_id') or '-'}",
    ]


def metrics_summary(metrics: dict[str, Any]) -> list[str]:
    return [
        f"Peers: {metrics.get('peer_count',0)}",
        f"Events Seen: {metrics.get('events_seen',0)}",
        f"Packets Pending: {metrics.get('pending_packets',0)}",
        f"Radar Zoom: {metrics.get('radar_zoom',1.0):.2f}",
        f"Netsplit: {'YES' if metrics.get('netsplit', False) else 'NO'}",
        f"Merges: {metrics.get('merge_count',0)}",
        f"Tick ms: {metrics.get('tick_ms', 0):.2f}",
    ]
