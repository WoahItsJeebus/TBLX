from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayController:
    def __init__(
        self,
        icon: QIcon,
        on_open_dashboard: Callable[[], None],
        on_toggle_pause: Callable[[], None],
        on_export: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_quit: Callable[[], None],
        is_paused_provider: Callable[[], bool],
    ) -> None:
        self._on_open_dashboard = on_open_dashboard
        self._on_toggle_pause = on_toggle_pause
        self._on_export = on_export
        self._on_open_settings = on_open_settings
        self._on_quit = on_quit
        self._is_paused_provider = is_paused_provider
        self._icon = QSystemTrayIcon(icon)
        self._icon.setToolTip("Trackerblox")
        self._menu = self._build_menu()
        self._icon.setContextMenu(self._menu)

    def start(self) -> None:
        self._icon.show()

    def stop(self) -> None:
        self._icon.hide()

    def refresh_menu(self) -> None:
        self._pause_action.setChecked(self._is_paused_provider())

    def show_message(self, title: str, message: str, timeout_ms: int = 5000) -> None:
        self._icon.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            timeout_ms,
        )

    def _build_menu(self) -> QMenu:
        menu = QMenu()

        open_action = QAction("Open Dashboard", menu)
        open_action.triggered.connect(self._on_open_dashboard)
        menu.addAction(open_action)

        self._pause_action = QAction("Pause Tracking", menu)
        self._pause_action.setCheckable(True)
        self._pause_action.setChecked(self._is_paused_provider())
        self._pause_action.triggered.connect(self._on_toggle_pause)
        menu.addAction(self._pause_action)

        export_action = QAction("Export Data", menu)
        export_action.triggered.connect(self._on_export)
        menu.addAction(export_action)

        settings_action = QAction("Settings", menu)
        settings_action.triggered.connect(self._on_open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._on_quit)
        menu.addAction(quit_action)
        return menu
