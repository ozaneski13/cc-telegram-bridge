import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def app_home():
    v = os.environ.get("CC_TG_BRIDGE_HOME")
    if v:
        return Path(v)
    here = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    try:
        t = (here / "home.txt").read_text(encoding="utf-8-sig").strip()
        if t:
            return Path(t)
    except Exception:
        pass
    return Path.home() / "Desktop" / "cc-telegram-bridge"


APP_HOME = app_home()


def read_env():
    env = {}
    try:
        for line in (APP_HOME / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def post(env, data):
    req = urllib.request.Request(
        f"http://127.0.0.1:{env.get('PORT', '8765')}/event",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Bridge-Token": env.get("BRIDGE_SECRET", "")},
    )
    urllib.request.urlopen(req, timeout=2).read()


def start_daemon():
    exe = APP_HOME / "cc-telegram-bridge.exe"
    if not exe.exists():
        return False
    subprocess.Popen([str(exe)], cwd=str(APP_HOME), creationflags=0x00000208, close_fds=True)
    return True


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    if data.get("hook_event_name") == "Stop" and data.get("stop_hook_active"):
        return
    env = read_env()
    try:
        post(env, data)
        return
    except Exception:
        pass
    if not start_daemon():
        return
    time.sleep(1.5)
    try:
        post(env, data)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
