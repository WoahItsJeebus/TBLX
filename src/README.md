# Trackerblox

Trackerblox is a Windows desktop time tracker for Roblox Player and Roblox Studio.

It runs in the system tray, records session data to local SQLite, and provides a PySide6 dashboard for viewing tracked time across daily, weekly, monthly, and lifetime ranges.

## Features

- Automatic detection of `RobloxPlayerBeta.exe` and `RobloxStudioBeta.exe`
- Active vs AFK tracking based on focus and input activity
- Dashboard cards for core stats (today, week, month, lifetime, app splits, active/AFK, longest session)
- Settings window (idle threshold, hide-to-tray behavior)
- CSV export
- Developer tools panel for clearing selected stat history
- Tray notifications for non-blocking success messages
- Single-instance protection on Windows

## Tech Stack

- PySide6
- sqlite3
- psutil
- pywin32

## Requirements

- Windows 10/11
- Python 3.11+

## Run From Source

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m trackerblox
```

## Build Standalone EXE

Use the standalone build script to create a distributable one-file executable:

```powershell
.\build-standalone.ps1
```

Output:

- `dist\Trackerblox.exe`

Notes:

- This build does not package your development database from the repository `data\` folder.
- Frozen builds use an isolated data location under `LOCALAPPDATA\Trackerblox\data`.

## Build Development Launcher EXE

The launcher build is for rapid local testing and does not bundle the app source.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\build-launcher.ps1
```

Output:

- `TrackerbloxLauncher.exe`

## Tracking Behavior

- A session starts when Roblox Player or Studio is detected.
- Active time increments when the tracked app is focused and receiving input.
- AFK time increments when the app is running but not actively interacted with.
- Last Input is scoped to the tracked Roblox session and stays at `0s` when no Roblox process is detected.

## Behavior Notes

- The app can be configured to hide to tray from Settings.

