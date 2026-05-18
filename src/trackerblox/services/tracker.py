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

MOUSE_BUTTON_VK_CODES = (0x01, 0x02, 0x04, 0x05, 0x06)
KEYBOARD_VK_CODES = tuple(range(0x08, 0x100))


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


@dataclass(slots=True)
class _PerProcessState:
    process: TrackedProcess
    session_id: int
    target_input_age_seconds: int = 0


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
        self._sessions: dict[int, _PerProcessState] = {}
        self._last_sample_at: datetime | None = None
        self._elapsed_carry_seconds: float = 0.0
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
            self._sessions = {}
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
            self._finalize_all_sessions(self._now_provider())
            self._snapshot = TrackerSnapshot(status="Stopped")
            self._thread = None

    def reset_current_session(self) -> None:
        """Discard all current session references without writing to the DB.

        Call after clearing session data so the tracker opens fresh
        sessions on the next poll cycle.
        """
        with self._lock:
            self._sessions.clear()

    def pause(self) -> None:
        with self._lock:
            if self._paused:
                return

            self._paused = True
            now = self._now_provider()
            self._finalize_all_sessions(now)
            self._last_sample_at = now
            self._elapsed_carry_seconds = 0.0
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
            for state in self._sessions.values():
                state.target_input_age_seconds = 0

    def sample_once(self) -> None:
        now = self._now_provider()
        tracked_processes = self._process_provider()
        window_state = self._window_provider()

        with self._lock:
            elapsed_seconds = self._get_elapsed_seconds(now)
            self._last_sample_at = now

            if self._paused:
                display_state = next(iter(self._sessions.values()), None)
                self._snapshot = TrackerSnapshot(
                    status="Paused",
                    active_process="Tracking paused",
                    active_window="Resume to continue recording",
                    last_input_age_seconds=display_state.target_input_age_seconds if display_state else 0,
                )
                return

            process_by_pid: dict[int, TrackedProcess] = {p.pid: p for p in tracked_processes}
            current_pids = set(process_by_pid.keys())
            tracked_pids = set(self._sessions.keys())

            # Close sessions for processes that are no longer running.
            for pid in tracked_pids - current_pids:
                self._finalize_session_for_pid(pid, now)

            if not current_pids:
                self._snapshot = TrackerSnapshot(
                    status="Waiting for Roblox",
                    active_process="No Roblox process detected",
                    active_window=window_state.title,
                    last_input_age_seconds=0,
                )
                return

            # Open sessions for newly detected processes. Time is not added
            # on the first poll for a new session to avoid over-counting the
            # detection delay.
            new_pids = current_pids - tracked_pids
            for pid in new_pids:
                process = process_by_pid[pid]
                session_id = self.database.start_session(
                    app_name=process.app_name,
                    source_process=process.process_name,
                    window_title=window_state.title,
                    started_at=now,
                )
                self._sessions[pid] = _PerProcessState(
                    process=process,
                    session_id=session_id,
                )

            # Consume input-edge bits once per poll so they are credited to
            # whichever target process currently has focus.
            foreground_pid = window_state.process_id
            focused_pid = foreground_pid if foreground_pid in process_by_pid else None
            had_input_event = self._has_target_input_event() if focused_pid is not None else False

            for pid, state in self._sessions.items():
                if pid in new_pids:
                    # Skip time accumulation on the first sample for a new session.
                    continue

                is_focused = pid == focused_pid

                if is_focused and had_input_event:
                    state.target_input_age_seconds = 0
                else:
                    state.target_input_age_seconds += elapsed_seconds

                is_active = is_focused and state.target_input_age_seconds < self._active_input_window_seconds

                if elapsed_seconds > 0:
                    active_s = elapsed_seconds if is_active else 0
                    self.database.add_session_time(
                        session_id=state.session_id,
                        active_seconds=active_s,
                        afk_seconds=elapsed_seconds - active_s,
                        window_title=window_state.title if is_focused else None,
                    )

            # Snapshot: prefer the focused target; fall back to the first session.
            if focused_pid is not None and focused_pid in self._sessions:
                display_state = self._sessions[focused_pid]
            else:
                display_state = next(iter(self._sessions.values()))

            display_process = display_state.process
            is_display_focused = display_process.pid == focused_pid
            is_display_active = (
                is_display_focused
                and display_state.target_input_age_seconds < self._active_input_window_seconds
            )

            other_labels = [
                APP_LABELS[s.process.app_name]
                for pid, s in self._sessions.items()
                if pid != display_process.pid
            ]
            also_running = (" | Also running: " + ", ".join(other_labels)) if other_labels else ""

            self._snapshot = TrackerSnapshot(
                status=self._build_status(display_process, is_display_focused, is_display_active),
                active_process=(
                    f"{APP_LABELS[display_process.app_name]}"
                    f" ({display_process.process_name}, PID {display_process.pid})"
                    f"{also_running}"
                ),
                active_window=window_state.title,
                last_input_age_seconds=display_state.target_input_age_seconds,
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

    def _finalize_all_sessions(self, ended_at: datetime) -> None:
        for pid in list(self._sessions.keys()):
            self._finalize_session_for_pid(pid, ended_at)

    def _finalize_session_for_pid(self, pid: int, ended_at: datetime) -> None:
        state = self._sessions.pop(pid, None)
        if state is not None:
            self.database.end_session(state.session_id, ended_at)

    def _get_elapsed_seconds(self, now: datetime) -> int:
        if self._last_sample_at is None:
            return 0
        delta_seconds = (now - self._last_sample_at).total_seconds() + self._elapsed_carry_seconds
        if delta_seconds <= 0:
            return 0

        whole_seconds = int(delta_seconds)
        self._elapsed_carry_seconds = delta_seconds - whole_seconds
        return whole_seconds

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

    def _has_target_input_event(self) -> bool:
        """Detect keypresses/clicks since last poll while target window is focused.

        Uses `GetAsyncKeyState` edge bits so keyboard and mouse-button clicks
        count as input, but mouse movement does not.
        """
        try:
            for vk_code in MOUSE_BUTTON_VK_CODES:
                if win32api.GetAsyncKeyState(vk_code) & 0x1:
                    return True

            for vk_code in KEYBOARD_VK_CODES:
                if win32api.GetAsyncKeyState(vk_code) & 0x1:
                    return True
        except Exception:
            return False

        return False
