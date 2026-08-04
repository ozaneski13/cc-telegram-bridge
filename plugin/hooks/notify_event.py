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


def api(env, method, path, payload=None, timeout=4):
    req = urllib.request.Request(
        f"http://127.0.0.1:{env.get('PORT', '8765')}{path}",
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        headers={"Content-Type": "application/json", "X-Bridge-Token": env.get("BRIDGE_SECRET", "")},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    try:
        return json.loads(body)
    except Exception:
        return {}


def start_daemon():
    exe = APP_HOME / "cc-telegram-bridge.exe"
    if not exe.exists():
        return False
    subprocess.Popen([str(exe)], cwd=str(APP_HOME), creationflags=0x00000208, close_fds=True)
    return True


def post_event(env, data):
    try:
        return api(env, "POST", "/event", data)
    except Exception:
        pass
    if not start_daemon():
        return None
    time.sleep(1.5)
    try:
        return api(env, "POST", "/event", data)
    except Exception:
        return None


def main():
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
    except Exception:
        return
    ev = data.get("hook_event_name")
    sid = data.get("session_id") or ""
    env = read_env()
    resp = post_event(env, data) or {}
    if ev in ("UserPromptSubmit", "SessionStart"):
        inject = resp.get("inject")
        if inject:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": ev, "additionalContext": inject}}, ensure_ascii=False))
        return
    if ev == "PreToolUse":
        ask = resp.get("ask")
        if not ask:
            return
        deadline = time.time() + int(ask.get("wait") or 0)
        while time.time() < deadline:
            try:
                r = api(env, "GET", f"/ask-poll?cid={ask['cid']}", None, timeout=30)
            except Exception:
                return
            answers = r.get("answers")
            if answers:
                if ask.get("mode") == "deny":
                    lines = "; ".join(f"{q} -> {a}" for q, a in answers.items())
                    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": "The user answered from Telegram: " + lines +
                                                  ". Do not ask again — continue with these answers."}}
                else:
                    ti = dict(data.get("tool_input") or {})
                    ti["answers"] = answers
                    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                                  "updatedInput": ti}}
                print(json.dumps(out, ensure_ascii=False))
                return
            if not r.get("keep"):
                return
        return
    if ev == "Stop":
        hold = int(resp.get("hold") or 0)
        if hold <= 0 or not sid:
            return
        deadline = time.time() + hold
        while time.time() < deadline:
            try:
                r = api(env, "GET", f"/hold?sid={sid}", None, timeout=30)
            except Exception:
                return
            if r.get("reply"):
                reason = ("[Telegram] The user sent this follow-up from their phone:\n" + r["reply"] +
                          "\nTreat it as a normal user message and act on it.")
                print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
                return
            if not r.get("keep"):
                return
    return


if __name__ == "__main__":
    main()
    sys.exit(0)
