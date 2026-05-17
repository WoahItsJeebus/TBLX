from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DashboardStats:
    today_seconds: int = 0
    week_seconds: int = 0
    month_seconds: int = 0
    lifetime_seconds: int = 0
    roblox_player_seconds: int = 0
    studio_seconds: int = 0
    active_seconds: int = 0
    afk_seconds: int = 0
    longest_session_seconds: int = 0
    sessions_recorded: int = 0


@dataclass(slots=True)
class TrackerSnapshot:
    status: str = "Starting"
    active_process: str = "Not tracking yet"
    active_window: str = "Waiting for tracker implementation"
    last_input_age_seconds: int | None = None


def format_duration(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"
