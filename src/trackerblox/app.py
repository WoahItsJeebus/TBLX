from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from trackerblox.config import UI_CONFIG
from trackerblox.services.database import StatsDatabase
from trackerblox.services.tracker import ActivityTracker
from trackerblox.services.tray import TrayController
from trackerblox.ui.app_icon import build_app_icon
from trackerblox.ui.dashboard import DashboardWindow
from trackerblox.ui.dev_menu import DevMenuWindow
from trackerblox.ui.settings import SettingsWindow


def _resolve_data_dir() -> Path:
    # Keep development data local to the repository, but isolate frozen builds
    # in AppData so packaged exes start with a clean, independent database.
    if getattr(sys, "frozen", False):
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "Trackerblox" / "data"
        return Path.home() / "AppData" / "Local" / "Trackerblox" / "data"

    return Path(__file__).resolve().parent.parent / "data"


class TrackerbloxApp:
    def __init__(self) -> None:
        self.qt_app = QApplication.instance() or QApplication([])
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.setApplicationName(UI_CONFIG["window"]["title"])
        self.qt_app.setApplicationDisplayName(UI_CONFIG["window"]["title"])
        self.qt_app.setOrganizationName("Trackerblox")
        self.app_icon = build_app_icon()
        self.qt_app.setWindowIcon(self.app_icon)

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(UI_CONFIG["window"]["title"])
        except Exception:
            pass

        data_dir = _resolve_data_dir()
        self.database = StatsDatabase(data_dir / "trackerblox.db")
        self.database.initialize()
        self.tracker = ActivityTracker(self.database)
        self._configure_tracker_from_settings()
        self._refresh_timer = QTimer()
        self._refresh_timer.setInterval(1000)
        self._refresh_timer.timeout.connect(self._refresh_loop)

        self.dashboard = DashboardWindow(
            on_refresh=self.refresh_dashboard,
            on_export=self.export_data,
            on_settings=self.open_settings,
            on_hide=self.hide_dashboard,
            on_scope_changed=self.refresh_dashboard,
            on_dev=self.open_dev_menu,
            on_relaunch=self.relaunch,
        )
        self.settings_window = SettingsWindow(
            on_save=self.save_settings,
            on_hide=self.hide_settings,
        )
        self.dev_menu = DevMenuWindow(
            on_clear=self._dev_clear_action,
            on_hide=self.hide_dev_menu,
        )
        self.tray = TrayController(
            icon=self.app_icon,
            on_open_dashboard=lambda: self._run_on_ui_thread(self.open_dashboard),
            on_toggle_pause=lambda: self._run_on_ui_thread(self.toggle_pause),
            on_export=lambda: self._run_on_ui_thread(self.export_data),
            on_open_settings=lambda: self._run_on_ui_thread(self.open_settings),
            on_quit=lambda: self._run_on_ui_thread(self.quit),
            is_paused_provider=lambda: self.tracker.is_paused,
        )

        self.dashboard.setWindowIcon(self.app_icon)
        self.settings_window.setWindowIcon(self.app_icon)
        self.dev_menu.setWindowIcon(self.app_icon)

    def start(self, show_dashboard: bool = False) -> None:
        self.tracker.start()
        self.tray.start()
        self.refresh_dashboard()
        self._refresh_timer.start()

        settings = self.database.fetch_settings()
        was_visible = settings.get("window_visible", "1") == "1"
        if show_dashboard and was_visible:
            self.open_dashboard()

        self.qt_app.exec()

    def open_dashboard(self) -> None:
        self.database.save_setting("window_visible", "1")
        self.dashboard.present()

    def hide_dashboard(self) -> None:
        settings = self.database.fetch_settings()
        if settings.get("hide_to_tray_on_close", "1") == "0":
            self.quit()
            return
        self.database.save_setting("window_visible", "0")
        self.dashboard.hide()

    def open_settings(self) -> None:
        self.settings_window.present(self.database.fetch_settings())

    def hide_settings(self) -> None:
        self.settings_window.hide()

    def open_dev_menu(self) -> None:
        self.dev_menu.present()

    def hide_dev_menu(self) -> None:
        self.dev_menu.hide()

    def relaunch(self) -> None:
        subprocess.Popen(
            [sys.executable, "-m", "trackerblox"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.quit()

    def save_settings(self, settings: dict[str, str]) -> None:
        try:
            idle_threshold = int(settings.get("idle_threshold_seconds", "300"))
            if idle_threshold <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.critical(None, "Invalid Setting", "Idle threshold must be a positive whole number.")
            return

        self.database.save_settings(settings)
        self.tracker.configure(idle_threshold_seconds=idle_threshold)
        self.hide_settings()
        self.tray.show_message(
            "Settings Saved",
            "Settings were saved to the local database.",
            5000,
        )

    def toggle_pause(self) -> None:
        if self.tracker.is_paused:
            self.tracker.resume()
        else:
            self.tracker.pause()

        self.tray.refresh_menu()
        self.refresh_dashboard()

    def refresh_dashboard(self) -> None:
        stats = self.database.get_dashboard_stats(scope=self.dashboard.selected_scope_key())
        snapshot = self.tracker.get_snapshot()
        self.dashboard.update_data(stats, snapshot, paused=self.tracker.is_paused)

    def export_data(self) -> None:
        export_path, _selected_filter = QFileDialog.getSaveFileName(
            None,
            "Export Session Data",
            "trackerblox-sessions.csv",
            "CSV Files (*.csv)",
        )
        if not export_path:
            return

        self.database.export_sessions_csv(Path(export_path))
        self.tray.show_message(
            "Export Complete",
            f"Session data exported to:\n{export_path}",
            5000,
        )

    def quit(self) -> None:
        self._refresh_timer.stop()

        self.tracker.stop()
        self.tray.stop()
        self.dashboard.destroy()
        self.settings_window.destroy()
        self.dev_menu.destroy()
        self.qt_app.quit()

    def _refresh_loop(self) -> None:
        self.refresh_dashboard()

    def _run_on_ui_thread(self, callback: callable) -> None:
        QTimer.singleShot(0, callback)

    def _configure_tracker_from_settings(self) -> None:
        settings = self.database.fetch_settings()
        try:
            idle_threshold = int(settings.get("idle_threshold_seconds", "300"))
        except ValueError:
            idle_threshold = 300

        self.tracker.configure(idle_threshold_seconds=idle_threshold)

    def _dev_clear_action(self, action: str) -> None:
        dispatch = {
            "today":          self.database.clear_today_sessions,
            "week":           self.database.clear_week_sessions,
            "month":          self.database.clear_month_sessions,
            "lifetime":       self.database.clear_all_sessions,
            "roblox_player":  self.database.clear_roblox_player_sessions,
            "studio":         self.database.clear_studio_sessions,
            "active_time":    self.database.clear_active_seconds,
            "afk_time":       self.database.clear_afk_seconds,
            "longest_session": self.database.clear_longest_session,
            "all_sessions":   self.database.clear_all_sessions,
        }
        handler = dispatch.get(action)
        if handler is not None:
            handler()
        self.tracker.reset_current_session()
        self.refresh_dashboard()
