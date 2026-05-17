from __future__ import annotations

# ---------------------------------------------------------------------------
# UI appearance — tune these values to adjust the dashboard layout and
# colour scheme without touching layout / logic code.
# ---------------------------------------------------------------------------

UI_CONFIG: dict = {
    "window": {
        "title": "Trackerblox Dashboard",
        "width": 1040,
        "height": 640,
        "min_width": 920,
        "min_height": 400,
    },
    "palette": {
        "root_bg": "#0F1720",
        "root_fg": "#DCE7F0",
        "status_panel_bg": "#15202B",
        "stat_card_bg": "#1D2C3A",
        "button_bg": "#223142",
        "button_hover_bg": "#2A3D50",
        "button_fg": "#ECF4FA",
        "title_fg": "#F3F6FA",
        "subtitle_fg": "#8FA6BA",
        "muted_fg": "#89A1B6",
        "bright_fg": "#F8FBFF",
    },
    "shell": {
        "margin": 24,
        "spacing": 18,
        "section_gap": 12,
    },
    "buttons": {
        "radius": 14,
        "padding_v": 10,
        "padding_h": 18,
        "font_size": 10,
    },
    "status_panel": {
        "radius": 16,
        "padding_h": 18,
        "padding_v": 18,
        "h_spacing": 20,
        "v_spacing": 8,
        "min_height": 120,
    },
    "stat_cards": {
        "radius": 14,
        "h_spacing": 12,
        "v_spacing": 12,
        "padding_h": 18,
        "padding_v": 16,
        "inner_spacing": 8,
        "min_height": 80,
		"max_height": 80,
        "value_font_size": 16,
    },
    "text": {
        "title_size": 24,
        "subtitle_size": 11,
        "status_title_size": 13,
        "status_body_size": 11,
        "stat_label_size": 10,
    },
    "input_ticker_ms": 100,
}

# Shared font family used across the UI.
FONT_CONFIG: dict = {
    "face": "Segoe UI",
}

# Hover description popup styling.
TOOLTIP_CONFIG: dict = {
    "max_width": 280,
    "border_width": 1.2,
    "radius": 10,
    "font_size": 10,
    "padding_h": 10,
    "padding_v": 8,
    "background_alpha": 235,
}

# Stat cards rendered on the dashboard, in display order (left-to-right,
# top-to-bottom).  Each entry: (DashboardStats field name, display label).
STAT_CARDS: list[tuple[str, str]] = [
    ("today_seconds",           "Today"),
    ("week_seconds",            "This Week"),
    ("month_seconds",           "This Month"),
    ("lifetime_seconds",        "Lifetime"),
    ("roblox_player_seconds",   "Roblox Player"),
    ("studio_seconds",          "Studio"),
    ("active_seconds",          "Active Time"),
    ("afk_seconds",             "AFK Time"),
    ("longest_session_seconds", "Longest Session"),
]

STAT_CARD_DESCRIPTIONS: dict[str, str] = {
    "today_seconds": "Total tracked time recorded today.",
    "week_seconds": "Total tracked time recorded this week.",
    "month_seconds": "Total tracked time recorded this month.",
    "lifetime_seconds": "Total tracked time recorded across the entire database.",
    "roblox_player_seconds": "Time recorded while Roblox Player was being tracked.",
    "studio_seconds": "Time recorded while Roblox Studio was being tracked.",
    "active_seconds": "Time counted as active while Roblox was focused and receiving input.",
    "afk_seconds": "Time counted while Roblox was running but the session was idle.",
    "longest_session_seconds": "The longest single tracked session in the database.",
}

# ---------------------------------------------------------------------------
# Developer tools
# ---------------------------------------------------------------------------

DEV_CONFIG: dict = {
    # Show the Developer button in the dashboard header.
    # Set to False to hide it for a clean production-style UI.
    "show_dev_button": False,
}

# One clear action per stat pill (first 9) plus a separate "all sessions"
# entry (last one).  Each tuple: (action_key, button_label, confirm_message).
DEV_CLEAR_ACTIONS: list[tuple[str, str, str]] = [
    (
        "today",
        "Today",
        "Delete all sessions recorded today.",
    ),
    (
        "week",
        "This Week",
        "Delete all sessions recorded this week.",
    ),
    (
        "month",
        "This Month",
        "Delete all sessions recorded this month.",
    ),
    (
        "lifetime",
        "Lifetime",
        "Delete ALL sessions in the database.",
    ),
    (
        "roblox_player",
        "Roblox Player",
        "Delete all Roblox Player sessions.",
    ),
    (
        "studio",
        "Roblox Studio",
        "Delete all Roblox Studio sessions.",
    ),
    (
        "active_time",
        "Active Time",
        "Reset active-seconds to 0 on every session.",
    ),
    (
        "afk_time",
        "AFK Time",
        "Reset AFK-seconds to 0 on every session.",
    ),
    (
        "longest_session",
        "Longest Session",
        "Delete the single session with the most tracked time.",
    ),
    # --- extra entry for the "Sessions Recorded" status field ---
    (
        "all_sessions",
        "All Sessions",
        "Delete ALL recorded sessions (same as Lifetime).",
    ),
]
