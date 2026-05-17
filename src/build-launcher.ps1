$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$arguments = @(
    '--noconfirm'
    '--onefile'
    '--windowed'
    '--name'
    'TrackerbloxLauncher'
    '--distpath'
    '.'
    '--workpath'
    'build\pyinstaller'
    '--specpath'
    'build\pyinstaller'
    'launcher.py'
)

& .\.venv\Scripts\python.exe -m PyInstaller @arguments