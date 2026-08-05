$ErrorActionPreference = "Stop"
$App = Split-Path -Parent $MyInvocation.MyCommand.Path

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py)
{
    Write-Host "ERROR: Python 3.10+ not found on PATH. Install it from python.org, then re-run setup.ps1."
    exit 1
}
$PythonExe = $py.Source
$PythonwExe = Join-Path (Split-Path -Parent $PythonExe) "pythonw.exe"
if (-not (Test-Path $PythonwExe)) { $PythonwExe = $PythonExe }
Write-Host "[1/5] Python: $PythonExe"

$Port = "8765"
$EnvFile = Join-Path $App ".env"
if (-not (Test-Path $EnvFile)) { Copy-Item (Join-Path $App ".env.example") $EnvFile }
$m = Select-String -Path $EnvFile -Pattern "^PORT=(\d+)" | Select-Object -First 1
if ($m) { $Port = $m.Matches[0].Groups[1].Value }
if (-not (Select-String -Path $EnvFile -Pattern "^BRIDGE_SECRET=." -Quiet))
{
    $bytes = New-Object byte[] 16
    (New-Object Security.Cryptography.RNGCryptoServiceProvider).GetBytes($bytes)
    $secret = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    Add-Content -Encoding Ascii $EnvFile "BRIDGE_SECRET=$secret"
}

$Dest = Join-Path $env:USERPROFILE ".claude\skills\cc-telegram-bridge"
New-Item -ItemType Directory -Force (Split-Path -Parent $Dest) | Out-Null
if (Test-Path $Dest) { Remove-Item -Recurse -Force $Dest }
Copy-Item -Recurse (Join-Path $App "plugin") $Dest
$tpl = Join-Path $Dest "hooks\hooks.json.template"
$hooks = (Get-Content $tpl -Raw) -replace "__PYTHON__", ($PythonExe -replace '\\', '\\\\')
[System.IO.File]::WriteAllText((Join-Path $Dest "hooks\hooks.json"), $hooks)
Remove-Item $tpl
[System.IO.File]::WriteAllText((Join-Path $Dest "hooks\home.txt"), $App)
Write-Host "[2/5] Plugin installed: $Dest"

$Startup = [Environment]::GetFolderPath("Startup")
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut((Join-Path $Startup "cc-telegram-bridge.lnk"))
$sc.TargetPath = $PythonwExe
$sc.Arguments = '"' + (Join-Path $App "daemon.py") + '"'
$sc.WorkingDirectory = $App
$sc.Save()
Write-Host "[3/5] Autostart installed: Startup\cc-telegram-bridge.lnk"

$up = $false
try
{
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/health" | Out-Null
    $up = $true
}
catch {}
if (-not $up)
{
    Start-Process $PythonwExe -ArgumentList ('"' + (Join-Path $App "daemon.py") + '"') -WorkingDirectory $App
    Start-Sleep 3
    try
    {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/health" | Out-Null
        $up = $true
    }
    catch {}
}
if ($up) { Write-Host "[4/5] Daemon running (port $Port)" }
else { Write-Host "[4/5] WARNING: daemon did not start - run: pythonw daemon.py" }

if (Select-String -Path $EnvFile -Pattern "^BOT_TOKEN=." -Quiet)
{
    Write-Host "[5/5] Setup complete. New Claude Code sessions will notify you on Telegram."
}
else
{
    Write-Host "[5/5] Setup complete BUT .env has no BOT_TOKEN (dry-run mode)."
    Write-Host "      -> Get a token from @BotFather, set BOT_TOKEN=... and TELEGRAM_OWNER_ID=... in .env,"
    Write-Host "      -> restart the daemon, then DM your bot once."
}
Write-Host ""
Write-Host "NOTE: If you migrated from another PC, stop the daemon there and remove its Startup shortcut;"
Write-Host "two machines polling the same bot token conflict (Telegram 409) and you will get duplicate notifications."
