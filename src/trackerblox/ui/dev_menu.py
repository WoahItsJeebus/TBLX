from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from trackerblox.config import DEV_CLEAR_ACTIONS, FONT_CONFIG


FONT_FACE = FONT_CONFIG["face"]


class DevMenuWindow(QDialog):
    def __init__(
        self,
        on_clear: Callable[[str], None],
        on_hide: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setWindowTitle("Developer Tools")
        self.setFixedWidth(520)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)

        self._on_clear = on_clear
        self._on_hide = on_hide

        self._build_layout()
        self.hide()

    def present(self) -> None:
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
            QDialog {
                background: #0F1720;
                color: #DCE7F0;
            }
            QLabel {
                background: transparent;
                color: #DCE7F0;
            }
            QLabel#SectionHeader {
                color: #8FA6BA;
                font: 700 8pt "%s";
            }
            QFrame#Divider {
                background: #1E2F3E;
                max-height: 1px;
                min-height: 1px;
            }
            QPushButton {
                background: #223142;
                color: #ECF4FA;
                border: none;
                border-radius: 10px;
                padding: 8px 12px;
                font: 600 9pt "%s";
            }
            QPushButton:hover {
                background: #2A3D50;
            }
            QPushButton#DangerButton {
                background: #3B1A1A;
                color: #F08080;
            }
            QPushButton#DangerButton:hover {
                background: #4D2020;
            }
            QPushButton#DangerButtonWide {
                background: #3B1A1A;
                color: #F08080;
                padding: 10px 12px;
            }
            QPushButton#DangerButtonWide:hover {
                background: #4D2020;
            }
            """ % (FONT_FACE, FONT_FACE)
        )

        shell = QVBoxLayout()
        shell.setContentsMargins(20, 20, 20, 20)
        shell.setSpacing(14)
        self.setLayout(shell)

        # Title
        title = QLabel("Developer Tools")
        title.setFont(QFont(FONT_FACE, 14, 600))
        shell.addWidget(title)

        # ── Section: stat-card clears ──────────────────────────────────────
        stat_header = QLabel("CLEAR STAT HISTORY")
        stat_header.setObjectName("SectionHeader")
        shell.addWidget(stat_header)

        # 3-column grid, one button per stat card (first 9 DEV_CLEAR_ACTIONS)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        shell.addLayout(grid)

        stat_actions = DEV_CLEAR_ACTIONS[:-1]  # everything except the trailing "all_sessions"
        for index, (key, label, description) in enumerate(stat_actions):
            row = index // 3
            col = index % 3
            btn = QPushButton(f"Clear {label}")
            btn.setObjectName("DangerButton")
            btn.clicked.connect(
                lambda checked=False, k=key, d=description: self._confirm_and_clear(k, d)
            )
            grid.addWidget(btn, row, col)

        # ── Divider ────────────────────────────────────────────────────────
        divider = QFrame()
        divider.setObjectName("Divider")
        shell.addWidget(divider)

        # ── Section: sessions recorded ─────────────────────────────────────
        sessions_header = QLabel("RECORDED SESSIONS")
        sessions_header.setObjectName("SectionHeader")
        shell.addWidget(sessions_header)

        all_key, all_label, all_desc = DEV_CLEAR_ACTIONS[-1]
        all_btn = QPushButton(f"Clear {all_label}")
        all_btn.setObjectName("DangerButtonWide")
        all_btn.clicked.connect(
            lambda checked=False, k=all_key, d=all_desc: self._confirm_and_clear(k, d)
        )
        shell.addWidget(all_btn)

        # ── Footer ─────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._on_hide)
        footer.addWidget(close_btn)
        shell.addLayout(footer)

    def _confirm_and_clear(self, action_key: str, description: str) -> None:
        result = QMessageBox.question(
            self,
            "Confirm Clear",
            f"{description}\n\nThis cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._on_clear(action_key)
