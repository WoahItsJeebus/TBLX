from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import threading

import psutil
import win32api
import win32gui
import win32process

from trackerblox.models import TrackerSnapshot
from trackerblox.services.database import StatsDatabase


TARGET_PROCESS_NAMES = {
    "robloxplayerbeta.exe": "roblox_player",
    "robloxstudiobeta.exe": "roblox_studio",
}

APP_LABELS = {
    "roblox_player": "Roblox Player",
    "roblox_studio": "Roblox Studio",
}


@dataclass(slots=True)
class TrackedProcess:
    app_name: str
    process_name: str
    pid: int
    created_at: float


@dataclass(slots=True)
class WindowState:
    title: str = "No active window"
    process_id: int | None = None


class ActivityTracker:
    def __init__(
        self,
        database: StatsDatabase,
        idle_threshold_seconds: int = 300,
        active_input_window_seconds: int = 5,
        poll_interval_seconds: float = 1.0,
        process_provider: Callable[[], list[TrackedProcess]] | None = None,
        window_provider: Callable[[], WindowState] | None = None,
        input_idle_provider: Callable[[], int | None] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self._running = False
        self._paused = False
        self._idle_threshold_seconds = idle_threshold_seconds
        self._active_input_window_seconds = active_input_window_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._process_provider = process_provider or self._list_target_processes
        self._window_provider = window_provider or self._get_foreground_window
        self._input_idle_provider = input_idle_provider or self._get_last_input_age_seconds
        self._now_provider = now_provider or datetime.now
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_session_id: int | None = None
        self._current_process: TrackedProcess | None = None
        self._last_sample_at: datetime | None = None
        self._elapsed_carry_seconds: float = 0.0
        self._target_input_age_seconds: int = 0
        self._last_target_input_sample_age: int | None = None
        self._snapshot = TrackerSnapshot(status="Stopped")

    @property
    def is_paused(self) -> bool:
        return self._paused

    def configure(self, idle_threshold_seconds: int, active_input_window_seconds: int | None = None) -> None:
        with self._lock:
            self._idle_threshold_seconds = max(1, idle_threshold_seconds)
            if active_input_window_seconds is not None:
                self._active_input_window_seconds = max(1, active_input_window_seconds)

    def start(self) -> None:
        with self._lock:
            if self._running:
                return

            self._running = True
            self._paused = False
            self._last_sample_at = self._now_provider()
            self._elapsed_carry_seconds = 0.0
            self._target_input_age_seconds = 0
            self._last_target_input_sample_age = None
            self._snapshot = TrackerSnapshot(status="Starting")
            self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, name="activity-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running and self._thread is None:
                return

            self._running = False
            self._stop_event.set()

        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)

        with self._lock:
            self._finalize_session(self._now_provider())
            self._snapshot = TrackerSnapshot(status="Stopped")
            self._target_input_age_seconds = 0
            self._last_target_input_sample_age = None
            self._thread = None

    def reset_current_session(self) -> None:
        """Discard the current session reference without writing to the DB.

        Call after clearing session data so the tracker creates a fresh
        session on the next poll cycle.
        """
        with self._lock:
            self._current_session_id = None
            self._current_process = None

    def pause(self) -> None:
        with self._lock:
            if self._paused:
                return

            self._paused = True
            now = self._now_provider()
            self._finalize_session(now)
            self._last_sample_at = now
            self._elapsed_carry_seconds = 0.0
            self._last_target_input_sample_age = None
            self._snapshot = TrackerSnapshot(
                status="Paused",
                active_process="Tracking paused",
                active_window="Resume to continue recording",
            )

    def resume(self) -> None:
        with self._lock:
            self._paused = False
            self._last_sample_at = self._now_provider()
            self._elapsed_carry_seconds = 0.0
            self._target_input_age_seconds = 0
            self._last_target_input_sample_age = None

    def sample_once(self) -> None:
        now = self._now_provider()
        tracked_processes = self._process_provider()
        window_state = self._window_provider()
        input_age = self._input_idle_provider()

        with self._lock:
            elapsed_seconds = self._get_elapsed_seconds(now)
            self._last_sample_at = now

            if self._paused:
                self._snapshot = TrackerSnapshot(
                    status="Paused",
                    active_process="Tracking paused",
                    active_window="Resume to continue recording",
                    last_input_age_seconds=self._target_input_age_seconds,
                )
                return

            current_process = self._select_process(tracked_processes, window_state.process_id)
            if current_process is None:
                self._finalize_session(now)
                self._target_input_age_seconds = 0
                self._last_target_input_sample_age = None
                self._snapshot = TrackerSnapshot(
                    status="Waiting for Roblox",
                    active_process="No Roblox process detected",
                    active_window=window_state.title,
                    last_input_age_seconds=self._target_input_age_seconds,
                )
                return

            if self._current_process is None or self._current_process.pid != current_process.pid:
                self._finalize_session(now)
                self._current_session_id = self.database.start_session(
                    app_name=current_process.app_name,
                    source_process=current_process.process_name,
                    window_title=window_state.title,
                    started_at=now,
                )
                self._current_process = current_process
                elapsed_seconds = 0
                self._last_target_input_sample_age = None

            is_target_focused = window_state.process_id == current_process.pid
            is_idle = self._is_idle(input_age)
            if is_target_focused:
                if (
                    input_age is not None
                    and self._last_target_input_sample_age is not None
                    and input_age < self._last_target_input_sample_age
                ):
                    self._target_input_age_seconds = 0
                else:
                    self._target_input_age_seconds += elapsed_seconds
                self._last_target_input_sample_age = input_age
            else:
                self._target_input_age_seconds += elapsed_seconds
                self._last_target_input_sample_age = None

            is_active_input = (
                is_target_focused
                and input_age is not None
                and input_age < self._active_input_window_seconds
            )
            if self._current_session_id is not None and elapsed_seconds > 0:
                active_seconds = elapsed_seconds if is_active_input else 0
                afk_seconds = elapsed_seconds - active_seconds
                self.database.add_session_time(
                    session_id=self._current_session_id,
                    active_seconds=active_seconds,
                    afk_seconds=afk_seconds,
                    window_title=window_state.title if is_target_focused else None,
                )

            self._snapshot = TrackerSnapshot(
                status=self._build_status(current_process, is_target_focused, is_active_input),
                active_process=f"{APP_LABELS[current_process.app_name]} ({current_process.process_name}, PID {current_process.pid})",
                active_window=window_state.title,
                last_input_age_seconds=self._target_input_age_seconds,
            )

    def get_snapshot(self) -> TrackerSnapshot:
        with self._lock:
            return TrackerSnapshot(
                status=self._snapshot.status,
                active_process=self._snapshot.active_process,
                active_window=self._snapshot.active_window,
                last_input_age_seconds=self._snapshot.last_input_age_seconds,
            )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.sample_once()
            self._stop_event.wait(self._poll_interval_seconds)

    def _finalize_session(self, ended_at: datetime) -> None:
        if self._current_session_id is None:
            self._current_process = None
            return

        self.database.end_session(self._current_session_id, ended_at)
        self._current_session_id = None
        self._current_process = None

    def _get_elapsed_seconds(self, now: datetime) -> int:
        if self._last_sample_at is None:
            return 0
        delta_seconds = (now - self._last_sample_at).total_seconds() + self._elapsed_carry_seconds
        if delta_seconds <= 0:
            return 0

        whole_seconds = int(delta_seconds)
        self._elapsed_carry_seconds = delta_seconds - whole_seconds
        return whole_seconds

    def _is_idle(self, input_age: int | None) -> bool:
        return input_age is not None and input_age > self._idle_threshold_seconds

    def _select_process(
        self,
        tracked_processes: list[TrackedProcess],
        foreground_process_id: int | None,
    ) -> TrackedProcess | None:
        if not tracked_processes:
            return None

        process_by_pid = {process.pid: process for process in tracked_processes}
        if foreground_process_id in process_by_pid:
            return process_by_pid[foreground_process_id]

        if self._current_process and self._current_process.pid in process_by_pid:
            return process_by_pid[self._current_process.pid]

        return min(tracked_processes, key=lambda process: (process.created_at, process.pid))

    def _build_status(self, process: TrackedProcess, is_target_focused: bool, is_active: bool) -> str:
        label = APP_LABELS[process.app_name]
        if is_target_focused and is_active:
            return f"Tracking {label}"
        if is_target_focused:
            return f"{label} idle"
        return f"{label} running in background"

    def _list_target_processes(self) -> list[TrackedProcess]:
        matches: list[TrackedProcess] = []
        for process in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                process_name = (process.info.get("name") or "").lower()
                app_name = TARGET_PROCESS_NAMES.get(process_name)
                if not app_name:
                    continue

                matches.append(
                    TrackedProcess(
                        app_name=app_name,
                        process_name=process.info.get("name") or process_name,
                        pid=int(process.info["pid"]),
                        created_at=float(process.info.get("create_time") or 0.0),
                    )
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue

        return matches

    def _get_foreground_window(self) -> WindowState:
        try:
            window_handle = win32gui.GetForegroundWindow()
            if not window_handle:
                return WindowState(title="No active window")

            title = win32gui.GetWindowText(window_handle).strip() or "Untitled window"
            _thread_id, process_id = win32process.GetWindowThreadProcessId(window_handle)
            return WindowState(title=title, process_id=process_id or None)
        except Exception:
            return WindowState(title="Active window unavailable")

    def _get_last_input_age_seconds(self) -> int | None:
        try:
            current_ticks = getattr(win32api, "GetTickCount64", win32api.GetTickCount)()
            last_input_ticks = win32api.GetLastInputInfo()
            return max(0, int((current_ticks - last_input_ticks) / 1000))
        except Exception:
            return None
