$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    throw 'Missing .venv\Scripts\python.exe. Create/activate your virtual environment first.'
}

# Ensure PyInstaller is available in the local venv.
& .\.venv\Scripts\python.exe -m pip install -r .\requirements-dev.txt

$distDir = Join-Path $root 'dist'
$workDir = Join-Path $root 'build\pyinstaller-standalone'

$arguments = @(
    '--noconfirm'
    '--clean'
    '--onefile'
    '--windowed'
    '--name'
    'Trackerblox'
    '--distpath'
    $distDir
    '--workpath'
    $workDir
    '--specpath'
    $workDir
    'trackerblox\__main__.py'
)

& .\.venv\Scripts\python.exe -m PyInstaller @arguments

Write-Host ''
Write-Host 'Standalone build complete:' -ForegroundColor Green
Write-Host (Join-Path $distDir 'Trackerblox.exe')
Write-Host ''
Write-Host 'Note: The standalone exe uses its own data directory under LOCALAPPDATA\Trackerblox\data.'
Write-Host 'It does not package your development database from the workspace data\ folder.'