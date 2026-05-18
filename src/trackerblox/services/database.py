from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from trackerblox.models import DashboardStats


DEFAULT_SETTINGS = {
    "launch_on_startup": "0",
    "idle_threshold_seconds": "300",
    "hide_to_tray_on_close": "0",
    "window_visible": "1",
}


class StatsDatabase:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name TEXT NOT NULL,
                    source_process TEXT,
                    window_title TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    active_seconds INTEGER NOT NULL DEFAULT 0,
                    afk_seconds INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

            for key, value in DEFAULT_SETTINGS.items():
                connection.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )

        self.close_stale_sessions()

    def close_stale_sessions(self) -> None:
        """Mark all sessions that were left open (no ended_at) as closed.

        Sets ended_at = started_at so they keep their accumulated
        active_seconds / afk_seconds but are no longer treated as live.
        """
        with self._connect() as connection:
            connection.execute(
                "UPDATE sessions SET ended_at = started_at WHERE ended_at IS NULL"
            )

    # -------------------------------------------------------------------------
    # Developer / data-management helpers
    # -------------------------------------------------------------------------

    def clear_today_sessions(self) -> int:
        """Delete sessions that started today. Returns number of rows deleted."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions "
                "WHERE date(started_at) = date('now', 'localtime')"
            )
            return cursor.rowcount

    def clear_week_sessions(self) -> int:
        """Delete sessions that started this week. Returns rows deleted."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions "
                "WHERE date(started_at) >= date('now', 'localtime', 'weekday 0', '-6 days')"
            )
            return cursor.rowcount

    def clear_month_sessions(self) -> int:
        """Delete sessions that started this calendar month. Returns rows deleted."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions "
                "WHERE strftime('%Y-%m', started_at) = strftime('%Y-%m', 'now', 'localtime')"
            )
            return cursor.rowcount

    def clear_all_sessions(self) -> int:
        """Delete every session row. Returns rows deleted."""
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sessions")
            return cursor.rowcount

    def clear_roblox_player_sessions(self) -> int:
        """Delete all Roblox Player sessions. Returns rows deleted."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE app_name = 'roblox_player'"
            )
            return cursor.rowcount

    def clear_studio_sessions(self) -> int:
        """Delete all Roblox Studio sessions. Returns rows deleted."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM sessions WHERE app_name = 'roblox_studio'"
            )
            return cursor.rowcount

    def clear_active_seconds(self) -> None:
        """Reset active_seconds to 0 on every session."""
        with self._connect() as connection:
            connection.execute("UPDATE sessions SET active_seconds = 0")

    def clear_afk_seconds(self) -> None:
        """Reset afk_seconds to 0 on every session."""
        with self._connect() as connection:
            connection.execute("UPDATE sessions SET afk_seconds = 0")

    def clear_longest_session(self) -> int:
        """Delete the single session with the highest tracked time. Returns 1 or 0."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM sessions
                WHERE id = (
                    SELECT id FROM sessions
                    ORDER BY active_seconds + afk_seconds DESC
                    LIMIT 1
                )
                """
            )
            return cursor.rowcount

    def start_session(
        self,
        app_name: str,
        source_process: str,
        window_title: str | None,
        started_at: datetime,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO sessions (app_name, source_process, window_title, started_at)
                VALUES (?, ?, ?, ?)
                """,
                (app_name, source_process, window_title, self._format_timestamp(started_at)),
            )
            return int(cursor.lastrowid)

    def add_session_time(
        self,
        session_id: int,
        active_seconds: int,
        afk_seconds: int,
        window_title: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET active_seconds = active_seconds + ?,
                    afk_seconds = afk_seconds + ?,
                    window_title = COALESCE(?, window_title)
                WHERE id = ?
                """,
                (active_seconds, afk_seconds, window_title, session_id),
            )

    def end_session(self, session_id: int, ended_at: datetime, window_title: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions
                SET ended_at = ?,
                    window_title = COALESCE(?, window_title)
                WHERE id = ?
                """,
                (self._format_timestamp(ended_at), window_title, session_id),
            )

    def fetch_settings(self) -> dict[str, str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT key, value FROM settings").fetchall()
        stored = {row[0]: row[1] for row in rows}
        return {**DEFAULT_SETTINGS, **stored}

    def save_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def save_settings(self, settings: dict[str, str]) -> None:
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                settings.items(),
            )

    def get_dashboard_stats(self, scope: str = "both") -> DashboardStats:
        scope_where = ""
        query_params: tuple[str, ...] = ()
        if scope == "roblox_player":
            scope_where = "WHERE app_name = ?"
            query_params = ("roblox_player",)
        elif scope == "roblox_studio":
            scope_where = "WHERE app_name = ?"
            query_params = ("roblox_studio",)

        with self._connect() as connection:
            stats_row = connection.execute(
                f"""
                SELECT
                    COALESCE(SUM(CASE
                        WHEN date(started_at) = date('now', 'localtime')
                        THEN tracked_seconds ELSE 0 END), 0) AS today_seconds,
                    COALESCE(SUM(CASE
                        WHEN date(started_at) >= date('now', 'localtime', 'weekday 0', '-6 days')
                        THEN tracked_seconds ELSE 0 END), 0) AS week_seconds,
                    COALESCE(SUM(CASE
                        WHEN strftime('%Y-%m', started_at) = strftime('%Y-%m', 'now', 'localtime')
                        THEN tracked_seconds ELSE 0 END), 0) AS month_seconds,
                    COALESCE(SUM(tracked_seconds), 0) AS lifetime_seconds,
                    COALESCE(SUM(CASE WHEN app_name = 'roblox_player' THEN tracked_seconds ELSE 0 END), 0) AS roblox_player_seconds,
                    COALESCE(SUM(CASE WHEN app_name = 'roblox_studio' THEN tracked_seconds ELSE 0 END), 0) AS studio_seconds,
                    COALESCE(SUM(active_seconds), 0) AS active_seconds,
                    COALESCE(SUM(afk_seconds), 0) AS afk_seconds,
                    COALESCE(MAX(tracked_seconds), 0) AS longest_session_seconds,
                    COUNT(*) AS sessions_recorded
                        ,COALESCE(SUM(CASE
                            WHEN strftime('%Y', started_at) = strftime('%Y', 'now', 'localtime')
                            THEN tracked_seconds ELSE 0 END), 0) AS year_seconds,
                        COALESCE(SUM(CASE
                            WHEN strftime('%Y', started_at) >= strftime('%Y', date('now', 'localtime', '-4 years'))
                            THEN tracked_seconds ELSE 0 END), 0) AS five_year_seconds
                FROM (
                    SELECT
                        app_name,
                        active_seconds,
                        afk_seconds,
                        MAX(active_seconds + afk_seconds, 0) AS tracked_seconds,
                        started_at
                    FROM sessions
                    {scope_where}
                )
                """,
                query_params,
            ).fetchone()

        return DashboardStats(*stats_row)

    def export_sessions_csv(self, export_path: Path) -> None:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    app_name,
                    source_process,
                    window_title,
                    started_at,
                    ended_at,
                    active_seconds,
                    afk_seconds
                FROM sessions
                ORDER BY started_at DESC
                """
            ).fetchall()

        with export_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.writer(output_file)
            writer.writerow(
                [
                    "id",
                    "app_name",
                    "source_process",
                    "window_title",
                    "started_at",
                    "ended_at",
                    "active_seconds",
                    "afk_seconds",
                ]
            )
            writer.writerows(rows)

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _format_timestamp(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")
