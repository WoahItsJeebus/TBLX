from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QCloseEvent, QCursor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from trackerblox.config import DEV_CONFIG, FONT_CONFIG, STAT_CARD_DESCRIPTIONS, STAT_CARDS, TOOLTIP_CONFIG, UI_CONFIG
from trackerblox.models import DashboardStats, TrackerSnapshot, format_duration


FONT_FACE = FONT_CONFIG["face"]

SCOPE_OPTIONS: list[tuple[str, str]] = [
    ("Roblox Client", "roblox_player"),
    ("Roblox Studio", "roblox_studio"),
    ("Roblox Client + Studio", "both"),
]


class _HoverDescriptionTip(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setMaximumWidth(TOOLTIP_CONFIG["max_width"])
        self.setStyleSheet(
            """
            QFrame#HoverTipFrame {
                background: rgba(13, 20, 28, %d);
                border: %dpx solid #2B4053;
                border-radius: %dpx;
            }
            QLabel#HoverTipText {
                background: transparent;
                color: #EAF2F8;
                font: %dpt "%s";
            }
            """ % (
                TOOLTIP_CONFIG["background_alpha"],
                TOOLTIP_CONFIG["border_width"],
                TOOLTIP_CONFIG["radius"],
                TOOLTIP_CONFIG["font_size"],
                FONT_FACE,
            )
        )

        shell = QVBoxLayout(self)
        shell.setContentsMargins(1, 1, 1, 1)
        shell.setSpacing(0)

        self._frame = QFrame()
        self._frame.setObjectName("HoverTipFrame")
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(10, 8, 10, 8)
        frame_layout.setSpacing(0)

        self._label = QLabel()
        self._label.setObjectName("HoverTipText")
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(TOOLTIP_CONFIG["max_width"])
        frame_layout.addWidget(self._label)

        shell.addWidget(self._frame)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._label.setText(text)
        self._label.adjustSize()
        self.adjustSize()

    def adjustSize(self) -> None:  # type: ignore[override]
        self._label.adjustSize()
        self._frame.adjustSize()
        super().adjustSize()

    def sizeHint(self):  # type: ignore[override]
        return self._frame.sizeHint()


class DashboardWindow(QWidget):
    def __init__(
        self,
        on_refresh: Callable[[], None],
        on_export: Callable[[], None],
        on_settings: Callable[[], None],
        on_hide: Callable[[], None],
        on_scope_changed: Callable[[], None],
        on_dev: Callable[[], None] | None = None,
        on_relaunch: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("DashboardRoot")
        self.setWindowTitle(UI_CONFIG["window"]["title"])
        self.resize(UI_CONFIG["window"]["width"], UI_CONFIG["window"]["height"])
        self.setMinimumSize(UI_CONFIG["window"]["min_width"], UI_CONFIG["window"]["min_height"])

        self._on_hide = on_hide
        self._on_scope_changed = on_scope_changed
        self._stat_labels: dict[str, QLabel] = {}
        self._stat_cards: dict[str, QFrame] = {}
        self._stat_category_labels: dict[str, QLabel] = {}
        self._stat_card_frames: list[QFrame] = []
        self._stat_cat_labels: list[QLabel] = []
        self._status_value_labels: list[QLabel] = []
        self._stat_hover_tip = _HoverDescriptionTip()
        self._stat_hover_tip.hide()

        self._status_value = QLabel("Starting")
        self._process_value = QLabel("Waiting")
        self._window_value = QLabel("Waiting")
        self._input_value = QLabel("Waiting")
        self._session_count_value = QLabel("0 sessions recorded")
        self._scope_select = QComboBox()
        for label, key in SCOPE_OPTIONS:
            self._scope_select.addItem(label, userData=key)
        self._scope_select.setCurrentIndex(2)
        self._scope_select.currentIndexChanged.connect(self._handle_scope_changed)

        self._stats_base = DashboardStats()
        self._stats_base_monotonic: float = time.monotonic()
        self._stats_mode: str = "none"
        self._stats_app_field: str | None = None

        self._input_base_seconds: float = 0.0
        self._input_base_monotonic: float = time.monotonic()
        self._input_frozen_at_zero: bool = False

        self._input_timer = QTimer(self)
        self._input_timer.setInterval(UI_CONFIG["input_ticker_ms"])
        self._input_timer.timeout.connect(self._input_tick)

        self._status_panel: QFrame | None = None
        self._apply_styles()
        self._build_layout(on_refresh, on_export, on_settings, on_dev, on_relaunch)
        self._apply_scope_card_visibility()
        self._sync_dynamic_text_sizes()
        self._input_timer.start()
        self.hide()

    def present(self) -> None:
        self._sync_dynamic_text_sizes()
        self.show()
        self.raise_()
        self.activateWindow()

    def selected_scope_key(self) -> str:
        selected = self._scope_select.currentData()
        if isinstance(selected, str):
            return selected
        return "both"

    def update_data(self, stats: DashboardStats, snapshot: TrackerSnapshot, paused: bool) -> None:
        self._stats_base = stats
        self._stats_base_monotonic = time.monotonic()
        self._stats_mode = self._derive_stats_mode(snapshot, paused)
        self._stats_app_field = self._derive_stats_app_field(snapshot)
        self._render_stats(stats)

        status_text = "Paused" if paused else snapshot.status
        self._status_value.setText(status_text)
        self._process_value.setText(snapshot.active_process)
        self._window_value.setText(snapshot.active_window)

        waiting_for_roblox = snapshot.status == "Waiting for Roblox" or snapshot.active_process.startswith(
            "No Roblox process detected"
        )
        if waiting_for_roblox:
            self._input_frozen_at_zero = True
            self._input_base_seconds = 0.0
            self._input_base_monotonic = time.monotonic()
        elif snapshot.last_input_age_seconds is not None:
            self._input_frozen_at_zero = False
            self._input_base_seconds = float(snapshot.last_input_age_seconds)
            self._input_base_monotonic = time.monotonic()

        noun = "session" if stats.sessions_recorded == 1 else "sessions"
        self._session_count_value.setText(f"{stats.sessions_recorded} {noun} recorded")

        # Refresh sizing after live text changes so the labels keep fitting.
        self._update_stat_value_fonts()

    def destroy(self) -> None:
        self._input_timer.stop()
        self._stat_hover_tip.hide()
        self.close()
        self.deleteLater()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self._on_hide()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._update_status_wrap()
        self._update_stat_value_fonts()

    def _apply_styles(self) -> None:
        p = UI_CONFIG["palette"]
        b = UI_CONFIG["buttons"]
        status = UI_CONFIG["status_panel"]
        cards = UI_CONFIG["stat_cards"]
        self.setStyleSheet(
            f"""
            QWidget#DashboardRoot {{
                background: {p["root_bg"]};
                color: {p["root_fg"]};
            }}
            QLabel {{
                background: transparent;
            }}
            QFrame#StatusPanel {{
                background: {p["status_panel_bg"]};
                border-radius: {status["radius"]}px;
            }}
            QFrame#StatCard {{
                background: {p["stat_card_bg"]};
                border-radius: {cards["radius"]}px;
            }}
            QPushButton {{
                background: {p["button_bg"]};
                color: {p["button_fg"]};
                border: none;
                border-radius: {b["radius"]}px;
                padding: {b["padding_v"]}px {b["padding_h"]}px;
                font: 600 {b["font_size"]}pt "{FONT_FACE}";
            }}
            QPushButton:hover {{
                background: {p["button_hover_bg"]};
            }}
            QPushButton#DevButton {{
                background: #1A2B1A;
                color: #85C585;
            }}
            QPushButton#DevButton:hover {{
                background: #253525;
            }}
            QPushButton#RelaunchButton {{
                background: #1A2B22;
                color: #6FCF97;
            }}
            QPushButton#RelaunchButton:hover {{
                background: #243A2E;
            }}
            """
        )

    def _title_label(self, text: str, size: int, weight: int = 400, color: str = "#F3F6FA") -> QLabel:
        label = QLabel(text)
        font = QFont(FONT_FACE, pointSize=size, weight=weight)
        label.setFont(font)
        label.setStyleSheet(f"color: {color};")
        return label

    def _metric_value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setFont(QFont(FONT_FACE, 11))
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: #DCE7F0;")
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return label

    def _build_layout(
        self,
        on_refresh: Callable[[], None],
        on_export: Callable[[], None],
        on_settings: Callable[[], None],
        on_dev: Callable[[], None] | None,
        on_relaunch: Callable[[], None] | None,
    ) -> None:
        shell_cfg = UI_CONFIG["shell"]
        txt = UI_CONFIG["text"]
        p = UI_CONFIG["palette"]
        status_cfg = UI_CONFIG["status_panel"]
        cards_cfg = UI_CONFIG["stat_cards"]

        shell = QVBoxLayout()
        shell.setContentsMargins(shell_cfg["margin"], shell_cfg["margin"], shell_cfg["margin"], shell_cfg["margin"])
        shell.setSpacing(shell_cfg["spacing"])
        self.setLayout(shell)

        header = QHBoxLayout()
        header.setSpacing(shell_cfg["section_gap"])
        shell.addLayout(header)

        title_column = QVBoxLayout()
        title_column.setSpacing(6)
        title_column.addWidget(self._title_label("Trackerblox", txt["title_size"], 600, p["title_fg"]))
        title_column.addWidget(
            self._title_label(
                "Time Tracker for Roblox and Roblox Studio",
                txt["subtitle_size"],
                400,
                p["subtitle_fg"],
            )
        )
        scope_row = QHBoxLayout()
        scope_row.setSpacing(8)
        scope_label = self._title_label("View", txt["subtitle_size"], 600, p["muted_fg"])
        self._scope_select.setMinimumWidth(180)
        self._scope_select.setFont(QFont(FONT_FACE, txt["subtitle_size"]))
        scope_row.addWidget(scope_label)
        scope_row.addWidget(self._scope_select)
        scope_row.addStretch(1)
        title_column.addLayout(scope_row)
        title_column.addStretch(1)
        header.addLayout(title_column, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        action_buttons: list[tuple[str, Callable[[], None]]] = []
        if DEV_CONFIG["show_dev_button"] and on_dev is not None:
            action_buttons.append(("Developer", on_dev))
        if DEV_CONFIG["show_dev_button"] and on_relaunch is not None:
            action_buttons.append(("Relaunch", on_relaunch))
        action_buttons += [
            ("Refresh", on_refresh),
            ("Export", on_export),
            ("Settings", on_settings),
            ("Hide", self._on_hide),
        ]
        for text, cb in action_buttons:
            button = QPushButton(text)
            if text == "Developer":
                button.setObjectName("DevButton")
            elif text == "Relaunch":
                button.setObjectName("RelaunchButton")
            button.clicked.connect(cb)
            actions.addWidget(button)
        header.addLayout(actions)

        status_panel = QFrame()
        status_panel.setObjectName("StatusPanel")
        status_panel.setMinimumHeight(status_cfg["min_height"])
        status_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        status_layout = QGridLayout(status_panel)
        status_layout.setContentsMargins(
            status_cfg["padding_h"],
            status_cfg["padding_v"],
            status_cfg["padding_h"],
            status_cfg["padding_v"],
        )
        status_layout.setHorizontalSpacing(status_cfg["h_spacing"])
        status_layout.setVerticalSpacing(status_cfg["v_spacing"])
        shell.addWidget(status_panel, 1)
        self._status_panel = status_panel

        title = QLabel("Tracker Status")
        title.setFont(QFont(FONT_FACE, txt["status_title_size"], 600))
        title.setStyleSheet(f"color: {p['root_fg']};")
        status_layout.addWidget(title, 0, 0)

        self._session_count_value.setFont(QFont(FONT_FACE, txt["status_body_size"]))
        self._session_count_value.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._session_count_value.setStyleSheet(f"color: {p['root_fg']};")
        status_layout.addWidget(self._session_count_value, 0, 1)

        rows = [
            ("State", self._status_value),
            ("Active Process", self._process_value),
            ("Window", self._window_value),
            ("Input", self._input_value),
        ]

        for index, (label_text, value_label) in enumerate(rows, start=1):
            label = QLabel(label_text)
            label.setFont(QFont(FONT_FACE, txt["status_body_size"]))
            label.setStyleSheet(f"color: {p['root_fg']};")
            label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            status_layout.addWidget(label, index, 0)

            value_label.setFont(QFont(FONT_FACE, txt["status_body_size"]))
            value_label.setStyleSheet(f"color: {p['root_fg']};")
            value_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            value_label.setWordWrap(True)
            status_layout.addWidget(value_label, index, 1)
            self._status_value_labels.append(value_label)

        status_layout.setColumnStretch(0, 1)
        status_layout.setColumnStretch(1, 1)
        for row_index in range(1, len(rows) + 1):
            status_layout.setRowStretch(row_index, 1)

        cards_grid = QGridLayout()
        cards_grid.setHorizontalSpacing(cards_cfg["h_spacing"])
        cards_grid.setVerticalSpacing(cards_cfg["v_spacing"])
        cards_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        shell.addLayout(cards_grid, 0)

        for index, (field_name, label_text) in enumerate(STAT_CARDS):
            row = index // 3
            column = index % 3
            description = STAT_CARD_DESCRIPTIONS.get(field_name)

            card = QFrame()
            card.setObjectName("StatCard")
            card.setMinimumHeight(cards_cfg["min_height"])
            card.setMaximumHeight(cards_cfg.get("max_height", cards_cfg["min_height"]))
            card.setMouseTracking(True)
            card.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
            card.setProperty("stat_description", description)
            card.installEventFilter(self)
            self._stat_card_frames.append(card)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(
                cards_cfg["padding_h"],
                cards_cfg["padding_v"],
                cards_cfg["padding_h"],
                cards_cfg["padding_v"],
            )
            card_layout.setSpacing(cards_cfg["inner_spacing"])

            label = QLabel(label_text)
            label.setStyleSheet(f"color: {p['muted_fg']};")
            label.setFont(QFont(FONT_FACE, txt["stat_label_size"], 600))
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            card_layout.addWidget(label)
            self._stat_category_labels[field_name] = label
            self._stat_cat_labels.append(label)

            value = QLabel("0s")
            value.setStyleSheet(f"color: {p['bright_fg']};")
            value.setFont(QFont(FONT_FACE, cards_cfg["value_font_size"], 600))
            value.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            value.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            card_layout.addWidget(value, 1)
            self._stat_labels[field_name] = value
            self._stat_cards[field_name] = card

            cards_grid.addWidget(card, row, column)

        self._update_status_wrap()

    def _input_tick(self) -> None:
        if self._input_frozen_at_zero:
            self._input_value.setText("Last input 0s ago")
            return

        elapsed = time.monotonic() - self._input_base_monotonic
        current = self._input_base_seconds + elapsed
        if current < 60:
            display = f"Last input {current:.1f}s ago"
        else:
            mins = int(current // 60)
            secs = current % 60
            display = f"Last input {mins}m {secs:04.1f}s ago"
        self._input_value.setText(display)
        self._update_interpolated_stats()

    def _render_stats(self, stats: DashboardStats) -> None:
        for field_name, _label in STAT_CARDS:
            self._stat_labels[field_name].setText(format_duration(getattr(stats, field_name)))

    def _derive_stats_mode(self, snapshot: TrackerSnapshot, paused: bool) -> str:
        if paused:
            return "none"

        status_lower = snapshot.status.lower()
        if "paused" in status_lower or "waiting" in status_lower or "starting" in status_lower:
            return "none"
        if "idle" in status_lower or "background" in status_lower:
            return "afk"
        if "tracking" in status_lower:
            return "active"
        return "none"

    def _derive_stats_app_field(self, snapshot: TrackerSnapshot) -> str | None:
        proc_lower = snapshot.active_process.lower()
        if "roblox player" in proc_lower:
            return "roblox_player_seconds"
        if "roblox studio" in proc_lower:
            return "studio_seconds"
        return None

    def _update_interpolated_stats(self) -> None:
        if self._stats_mode == "none":
            return

        # Compute whole seconds elapsed since the last DB snapshot was received.
        # We add directly onto a copy of the frozen base — never accumulate onto
        # a previously-interpolated value, so there is no compounding.
        extra = int(max(0.0, time.monotonic() - self._stats_base_monotonic))
        if extra <= 0:
            return

        selected_scope = self.selected_scope_key()
        is_matching_scope = (
            selected_scope == "both"
            or (selected_scope == "roblox_player" and self._stats_app_field == "roblox_player_seconds")
            or (selected_scope == "roblox_studio" and self._stats_app_field == "studio_seconds")
        )
        scope_extra = extra if is_matching_scope else 0

        b = self._stats_base
        stats = DashboardStats(
            today_seconds=b.today_seconds + scope_extra,
            week_seconds=b.week_seconds + scope_extra,
            month_seconds=b.month_seconds + scope_extra,
            lifetime_seconds=b.lifetime_seconds + scope_extra,
            roblox_player_seconds=b.roblox_player_seconds + (scope_extra if self._stats_app_field == "roblox_player_seconds" else 0),
            studio_seconds=b.studio_seconds + (scope_extra if self._stats_app_field == "studio_seconds" else 0),
            active_seconds=b.active_seconds + (scope_extra if self._stats_mode == "active" else 0),
            afk_seconds=b.afk_seconds + (scope_extra if self._stats_mode == "afk" else 0),
            longest_session_seconds=b.longest_session_seconds,
            sessions_recorded=b.sessions_recorded,
        )
        self._render_stats(stats)

    def _handle_scope_changed(self, _index: int) -> None:
        self._apply_scope_card_visibility()
        self._update_stat_value_fonts()
        self._on_scope_changed()

    def _apply_scope_card_visibility(self) -> None:
        show_app_split = self.selected_scope_key() == "both"
        for field_name in ("roblox_player_seconds", "studio_seconds"):
            card = self._stat_cards.get(field_name)
            if card is not None:
                card.setVisible(show_app_split)

    def _update_status_wrap(self) -> None:
        if self._status_panel is None:
            return
        panel_width = self._status_panel.width()
        target = max(180, (panel_width // 2) - 40)
        for label in self._status_value_labels:
            label.setMaximumWidth(target)

    def _sync_dynamic_text_sizes(self) -> None:
        if self.layout() is not None:
            self.layout().activate()
        self._update_status_wrap()
        self._update_stat_value_fonts()

    def get_text_size(
        self,
        available_height: int,
        *,
        min_size: int,
        max_size: int,
        weight: int = 600,
    ) -> int:
        low = min_size
        high = max_size
        best = min_size

        while low <= high:
            candidate = (low + high) // 2
            metrics = QFontMetrics(QFont(FONT_FACE, candidate, weight))
            if metrics.height() <= available_height:
                best = candidate
                low = candidate + 1
            else:
                high = candidate - 1

        return best

    def _update_stat_value_fonts(self) -> None:
        if not self._stat_card_frames:
            return
        cards_cfg = UI_CONFIG["stat_cards"]
        min_height = cards_cfg["min_height"]
        max_height = cards_cfg.get("max_height", min_height)
        card_height = self._stat_card_frames[0].height()
        if card_height <= 0:
            card_height = max_height
        card_height = max(min_height, min(card_height, max_height))

        # Measure how much vertical space remains for the value label after
        # the category label and padding are accounted for. Use font metrics so
        # this works before the widget is shown.
        if self._stat_cat_labels:
            cat_metrics = QFontMetrics(self._stat_cat_labels[0].font())
            cat_height = cat_metrics.height()
        else:
            cat_height = 20

        available = max(
            24,
            card_height
            - 2 * cards_cfg["padding_v"]
            - cat_height
            - cards_cfg["inner_spacing"],
        )
        font_size = self.get_text_size(
            available,
            min_size=10,
            max_size=48,
            weight=600,
        )
        for label in self._stat_labels.values():
            font = label.font()
            if font.pointSize() != font_size:
                font.setPointSize(font_size)
                label.setFont(font)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        description = watched.property("stat_description") if hasattr(watched, "property") else None
        if description:
            event_type = event.type()
            if event_type in (QEvent.Type.Enter, QEvent.Type.HoverEnter, QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                self._show_stat_hover_tip(str(description), QCursor.pos())
            elif event_type in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
                self._stat_hover_tip.hide()
        return super().eventFilter(watched, event)

    def _show_stat_hover_tip(self, text: str, global_pos) -> None:
        self._stat_hover_tip.setText(text)
        self._stat_hover_tip.adjustSize()

        offset_x = 18
        offset_y = 22
        tip_size = self._stat_hover_tip.sizeHint()
        x = global_pos.x() + offset_x
        y = global_pos.y() + offset_y

        self._stat_hover_tip.move(x, y)
        self._stat_hover_tip.show()
