$ErrorActionPreference = "Stop"
$App = Split-Path -Parent $MyInvocation.MyCommand.Path

$DaemonExe = Join-Path $App "cc-telegram-bridge.exe"
$HookExe = Join-Path $App "plugin\hooks\notify_event.exe"
if (-not (Test-Path $DaemonExe) -or -not (Test-Path $HookExe))
{
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py)
    {
        Write-Host "[0/4] Executables missing - building with PyInstaller..."
        & (Join-Path $App "build.ps1")
    }
    else
    {
        Write-Host "[0/4] ERROR: executables missing and Python not found."
        Write-Host "      Install Python 3.10+ and run build.ps1, then re-run setup.ps1."
        exit 1
    }
}

$Port = "8765"
$EnvFile = Join-Path $App ".env"
if (-not (Test-Path $EnvFile)) { Copy-Item (Join-Path $App ".env.example") $EnvFile }
$m = Select-String -Path $EnvFile -Pattern "^PORT=(\d+)" | Select-Object -First 1
if ($m) { $Port = $m.Matches[0].Groups[1].Value }
$hasSecret = Select-String -Path $EnvFile -Pattern "^BRIDGE_SECRET=." -Quiet
if (-not $hasSecret)
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
[System.IO.File]::WriteAllText((Join-Path $Dest "hooks\home.txt"), $App)
Write-Host "[1/4] Plugin installed: $Dest"

$Startup = [Environment]::GetFolderPath("Startup")
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut((Join-Path $Startup "cc-telegram-bridge.lnk"))
$sc.TargetPath = $DaemonExe
$sc.WorkingDirectory = $App
$sc.Save()
Write-Host "[2/4] Autostart installed: Startup\cc-telegram-bridge.lnk"

$up = $false
try
{
    Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/health" | Out-Null
    $up = $true
}
catch {}
if (-not $up)
{
    Start-Process $DaemonExe -WorkingDirectory $App
    Start-Sleep 2
    try
    {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/health" | Out-Null
        $up = $true
    }
    catch {}
}
if ($up) { Write-Host "[3/4] Daemon running (port $Port)" }
else { Write-Host "[3/4] WARNING: daemon did not start - run cc-telegram-bridge.exe manually" }

$hasToken = Select-String -Path $EnvFile -Pattern "^BOT_TOKEN=." -Quiet
if ($hasToken)
{
    Write-Host "[4/4] Setup complete. New Claude Code sessions will notify; run /cc-telegram-bridge in a session to enable replies."
}
else
{
    Write-Host "[4/4] Setup complete BUT .env has no BOT_TOKEN (dry-run mode)."
    Write-Host "      -> Get a token from @BotFather, set BOT_TOKEN=... and TELEGRAM_OWNER_ID=... in .env,"
    Write-Host "      -> restart the daemon, then DM your bot once."
}
Write-Host ""
Write-Host "NOTE: If you migrated from another PC, stop the daemon there and remove its Startup shortcut;"
Write-Host "two machines polling the same bot token conflict (Telegram 409) and you will get duplicate notifications."
