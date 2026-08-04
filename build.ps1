$ErrorActionPreference = "Stop"
$App = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $App

python -m pip install --quiet pyinstaller
python -m PyInstaller --onefile --noconsole --name cc-telegram-bridge daemon.py
python -m PyInstaller --onefile --name notify_event plugin/hooks/notify_event.py
Copy-Item -Force (Join-Path $App "dist\cc-telegram-bridge.exe") $App
Copy-Item -Force (Join-Path $App "dist\notify_event.exe") (Join-Path $App "plugin\hooks")
Write-Host "Build OK: cc-telegram-bridge.exe + plugin\hooks\notify_event.exe"
