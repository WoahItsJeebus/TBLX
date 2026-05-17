from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from trackerblox.config import FONT_CONFIG


FONT_FACE = FONT_CONFIG["face"]


class SettingsWindow(QDialog):
    def __init__(self, on_save: Callable[[dict[str, str]], None], on_hide: Callable[[], None]) -> None:
        super().__init__()
        self.setWindowTitle("Trackerblox Settings")
        self.setFixedSize(440, 320)

        self._on_save = on_save
        self._on_hide = on_hide

        self._launch_on_startup = QCheckBox("Launch Trackerblox on Windows startup")
        self._hide_to_tray = QCheckBox("Hide to system tray when window is closed")
        self._idle_threshold = QLineEdit("300")
        self._idle_threshold.setMaximumWidth(100)

        self._build_layout()
        self.hide()

    def present(self, settings: dict[str, str]) -> None:
        self._launch_on_startup.setChecked(settings.get("launch_on_startup", "0") == "1")
        self._hide_to_tray.setChecked(settings.get("hide_to_tray_on_close", "0") == "1")
        self._idle_threshold.setText(settings.get("idle_threshold_seconds", "300"))
        self.show()
        self.raise_()
        self.activateWindow()

    def hide(self) -> None:  # type: ignore[override]
        super().hide()

    def destroy(self) -> None:
        self.close()
        self.deleteLater()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self._on_hide()

    def _build_layout(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #0F1720; color: #E6EDF3; }
            QLabel { color: #E6EDF3; }
            QFrame#Panel { background: #15202B; border-radius: 12px; }
            QPushButton {
                background: #223142;
                color: #ECF4FA;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font: 600 10pt "%s";
            }
            QPushButton:hover { background: #2A3D50; }
            QLineEdit {
                background: #0D141C;
                color: #E6EDF3;
                border: 1px solid #2B4053;
                border-radius: 8px;
                padding: 6px 8px;
                font: 10pt "%s";
            }
            """ % (FONT_FACE, FONT_FACE)
        )

        shell = QVBoxLayout()
        shell.setContentsMargins(20, 20, 20, 20)
        shell.setSpacing(14)
        self.setLayout(shell)

        title = QLabel("Settings")
        title.setFont(QFont(FONT_FACE, 18, 600))
        shell.addWidget(title)

        panel = QVBoxLayout()
        panel.setContentsMargins(18, 18, 18, 18)
        panel.setSpacing(12)

        panel.addWidget(self._launch_on_startup)
        panel.addWidget(self._hide_to_tray)

        idle_label = QLabel("Idle threshold (seconds)")
        idle_label.setFont(QFont(FONT_FACE, 10))
        panel.addWidget(idle_label)
        panel.addWidget(self._idle_threshold, alignment=Qt.AlignmentFlag.AlignLeft)

        note = QLabel(
            "Startup registration is not wired yet. This setting is persisted for future implementation."
        )
        note.setWordWrap(True)
        note.setFont(QFont(FONT_FACE, 10))
        panel.addWidget(note)

        panel_widget = QFrame()
        panel_widget.setObjectName("Panel")
        panel_widget.setLayout(panel)
        shell.addWidget(panel_widget, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self._on_hide)
        actions.addWidget(cancel)

        save = QPushButton("Save")
        save.clicked.connect(self._save)
        actions.addWidget(save)

        shell.addLayout(actions)

    def _save(self) -> None:
        payload = {
            "launch_on_startup": "1" if self._launch_on_startup.isChecked() else "0",
            "hide_to_tray_on_close": "1" if self._hide_to_tray.isChecked() else "0",
            "idle_threshold_seconds": self._idle_threshold.text().strip() or "300",
        }
        self._on_save(payload)
