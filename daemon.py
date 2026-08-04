import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
LOGS = BASE / "logs"
SPIKE = BASE / "spike"
STATE_PATH = BASE / "state.json"
INBOX_PATH = BASE / "inbox.jsonl"
CURSOR_PATH = BASE / "inbox.cursor"


def load_env():
    env = {}
    try:
        for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


ENV = load_env()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or ENV.get("BOT_TOKEN", "")
OWNER_ID = int(ENV.get("TELEGRAM_OWNER_ID", "0") or "0")
SECRET = ENV.get("BRIDGE_SECRET", "")
PORT = int(ENV.get("PORT", "8765") or "8765")
IGNORE_CWD = [s.strip().lower() for s in ENV.get("IGNORE_CWD_SUBSTRINGS", "cc-telegram-bridge").split(",") if s.strip()]

LOCK = threading.Lock()
PENDING = {}
LAST_SENT = {}
GLOBAL_SENDS = []
CCD_SESSIONS_DIR = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code-sessions"
CCD_ID_CACHE = {}


def resolve_ccd_id(cli_sid):
    if cli_sid in CCD_ID_CACHE:
        return CCD_ID_CACHE[cli_sid]
    try:
        for p in CCD_SESSIONS_DIR.rglob("local_*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("cliSessionId") == cli_sid:
                ccd = d.get("sessionId") or p.stem
                CCD_ID_CACHE[cli_sid] = ccd
                return ccd
    except Exception:
        pass
    return None


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with open(LOGS / "daemon.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        sys.stdout.write(line.encode("ascii", "replace").decode() + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"msg_map": {}, "recent": [], "last_session": None, "chat_id": None, "inbox_seq": 0, "dry_seq": 0}


STATE = load_state()


def save_state():
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def telegram(method, payload):
    if not BOT_TOKEN:
        STATE["dry_seq"] = STATE.get("dry_seq", 0) - 1
        with open(LOGS / "outbox.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "method": method, "payload": payload}, ensure_ascii=False) + "\n")
        return {"ok": True, "result": {"message_id": STATE["dry_seq"]}}
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=70) as r:
        return json.loads(r.read().decode("utf-8"))


def last_assistant_text(transcript_path):
    try:
        p = Path(transcript_path)
        size = p.stat().st_size
        with open(p, "rb") as f:
            f.seek(max(0, size - 262144))
            chunk = f.read().decode("utf-8", errors="replace")
        lines = chunk.split("\n")
        if size > 262144:
            lines = lines[1:]
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "assistant":
                continue
            content = (obj.get("message") or {}).get("content") or []
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            joined = "\n".join(t for t in texts if t).strip()
            if joined:
                return joined if len(joined) <= 700 else "…" + joined[-700:]
    except Exception:
        pass
    return "(no summary available)"


def format_questions(tool_input):
    parts = []
    for q in tool_input.get("questions", []) or []:
        parts.append(q.get("question", "?"))
        for i, opt in enumerate(q.get("options", []) or [], 1):
            desc = (opt.get("description") or "")[:80]
            parts.append(f"  {i}. {opt.get('label', '?')}" + (f" — {desc}" if desc else ""))
    return "\n".join(parts) or "(question unreadable)"


def notify(sid, cwd, kind, text):
    h = hashlib.md5(text.encode("utf-8", "replace")).hexdigest()
    with LOCK:
        PENDING[sid] = {"due": time.time() + 3, "kind": kind, "hash": h, "text": text, "cwd": cwd}


def handle_event(data):
    try:
        with open(SPIKE / "hooklog.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "raw": data}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    ev = data.get("hook_event_name")
    sid = data.get("session_id")
    cwd = data.get("cwd") or ""
    tp = data.get("transcript_path") or ""
    if not sid or not ev:
        return
    if any(s in cwd.lower() for s in IGNORE_CWD):
        return
    if ev == "Stop":
        if data.get("stop_hook_active"):
            return
        text = (data.get("last_assistant_message") or "").strip()
        if text:
            text = text if len(text) <= 700 else "…" + text[-700:]
        else:
            text = last_assistant_text(tp)
        running_bg = [t for t in data.get("background_tasks") or [] if t.get("status") == "running"]
        icon = f"🔄({len(running_bg)} bg) " if running_bg else "✅ "
        notify(sid, cwd, "stop", icon + text)
    elif ev == "Notification":
        notify(sid, cwd, "notify", "⏳ " + (data.get("message") or "waiting for input"))
    elif ev == "PreToolUse":
        tool = data.get("tool_name")
        ti = data.get("tool_input") or {}
        if tool == "AskUserQuestion":
            notify(sid, cwd, "question", "❓ Question:\n" + format_questions(ti))
        elif tool == "ExitPlanMode":
            notify(sid, cwd, "plan", "📋 Plan awaiting approval:\n" + last_assistant_text(tp))


def update_recent(sid, cwd):
    rec = [r for r in STATE.get("recent", []) if r.get("session_id") != sid]
    rec.insert(0, {"session_id": sid, "cwd": cwd, "ts": time.time()})
    STATE["recent"] = rec[:20]


def record_sent(mid, sid, cwd, kind):
    STATE["msg_map"][str(mid)] = {"session_id": sid, "cwd": cwd, "kind": kind, "ts": time.time()}
    keys = list(STATE["msg_map"].keys())
    for k in keys[:-200]:
        del STATE["msg_map"][k]
    STATE["last_session"] = sid
    update_recent(sid, cwd)
    save_state()


def deliver(sid, item):
    proj = Path(item["cwd"]).name if item["cwd"] else "?"
    body = (f"[{proj} #{sid[:8]}]\n" + item["text"])[:3900]
    payload = {"text": body}
    with LOCK:
        chat = STATE.get("chat_id")
    if BOT_TOKEN and not chat:
        log("no chat bound yet; dropping notification (DM the bot once)")
        return
    if chat:
        payload["chat_id"] = chat
    err = None
    for delay in (0, 2, 8, 30):
        if delay:
            time.sleep(delay)
        try:
            r = telegram("sendMessage", payload)
            if r.get("ok"):
                with LOCK:
                    record_sent(r["result"]["message_id"], sid, item["cwd"], item["kind"])
                return
            err = r
        except Exception as e:
            err = e
    log(f"send failed after retries: {err}")


def send_loop():
    while True:
        time.sleep(0.5)
        now = time.time()
        due = []
        with LOCK:
            while GLOBAL_SENDS and now - GLOBAL_SENDS[0] > 60:
                GLOBAL_SENDS.pop(0)
            for sid in list(PENDING.keys()):
                item = PENDING[sid]
                if item["due"] > now:
                    continue
                last = LAST_SENT.get(sid)
                if item["kind"] == "stop" and last and last[1] == item["hash"] and now - last[0] < 10:
                    del PENDING[sid]
                    continue
                if last and now - last[0] < 5:
                    item["due"] = last[0] + 5
                    continue
                if len(GLOBAL_SENDS) >= 20:
                    item["due"] = now + 5
                    continue
                GLOBAL_SENDS.append(now)
                LAST_SENT[sid] = (now, item["hash"])
                del PENDING[sid]
                due.append((sid, item))
        for sid, item in due:
            deliver(sid, item)


def humanize(ts):
    d = int(time.time() - ts)
    if d < 3600:
        return f"{d // 60}m"
    if d < 86400:
        return f"{d // 3600}h"
    return f"{d // 86400}d"


def sessions_list():
    with LOCK:
        rec = list(STATE.get("recent", []))
        last = STATE.get("last_session")
    if not rec:
        return "no notifications yet"
    lines = []
    for i, r in enumerate(rec, 1):
        proj = Path(r["cwd"]).name if r.get("cwd") else "?"
        mark = " *" if r["session_id"] == last else ""
        lines.append(f"{i}. {proj} #{r['session_id'][:8]} — {humanize(r['ts'])}{mark}")
    return "\n".join(lines)


def reply_chat(text):
    with LOCK:
        chat = STATE.get("chat_id")
    if not chat:
        return None
    try:
        return telegram("sendMessage", {"chat_id": chat, "text": text[:3900]})
    except Exception as e:
        log(f"reply_chat failed: {e}")
        return None


def queue_inbox(session_id, cwd, text):
    lag = 0
    try:
        cursor = int(CURSOR_PATH.read_text().strip() or "0") if CURSOR_PATH.exists() else 0
        size = INBOX_PATH.stat().st_size if INBOX_PATH.exists() else 0
        lag = size - cursor
    except Exception:
        pass
    with LOCK:
        STATE["inbox_seq"] = STATE.get("inbox_seq", 0) + 1
        seq = STATE["inbox_seq"]
        save_state()
    deliver_id = resolve_ccd_id(session_id) or session_id
    with open(INBOX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": seq, "ts": time.time(), "session_id": deliver_id, "cwd": cwd, "text": text}, ensure_ascii=False) + "\n")
    proj = Path(cwd).name if cwd else "?"
    conf = f"→ {proj} #{session_id[:8]}"
    if lag > 0:
        conf += "\n⚠️ bridge session looks behind — reply queued"
    r = reply_chat(conf)
    if r and r.get("ok"):
        with LOCK:
            record_sent(r["result"]["message_id"], session_id, cwd, "confirm")


def handle_update(u):
    msg = u.get("message")
    if not msg:
        return
    frm = (msg.get("from") or {}).get("id")
    if not OWNER_ID or frm != OWNER_ID:
        return
    chat_id = (msg.get("chat") or {}).get("id")
    with LOCK:
        if STATE.get("chat_id") != chat_id:
            STATE["chat_id"] = chat_id
            save_state()
    text = (msg.get("text") or "").strip()
    if not text:
        reply_chat("text messages only")
        return
    if text.split()[0] == "/sessions":
        reply_chat(sessions_list())
        return
    if text.split()[0] == "/use":
        arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
        with LOCK:
            rec = list(STATE.get("recent", []))
        target = None
        if arg.isdigit() and 1 <= int(arg) <= len(rec):
            target = rec[int(arg) - 1]
        else:
            for r in rec:
                if r["session_id"].startswith(arg) and arg:
                    target = r
                    break
        if not target:
            reply_chat("not found — list with /sessions")
            return
        with LOCK:
            STATE["last_session"] = target["session_id"]
            save_state()
        proj = Path(target["cwd"]).name if target.get("cwd") else "?"
        reply_chat(f"active: {proj} #{target['session_id'][:8]}")
        return
    target = None
    rt = msg.get("reply_to_message")
    if rt:
        with LOCK:
            m = STATE["msg_map"].get(str(rt.get("message_id")))
        if m:
            target = {"session_id": m["session_id"], "cwd": m.get("cwd", "")}
    if not target:
        with LOCK:
            last = STATE.get("last_session")
            rec = {r["session_id"]: r for r in STATE.get("recent", [])}
        if last:
            target = {"session_id": last, "cwd": rec.get(last, {}).get("cwd", "")}
    if not target:
        reply_chat("no active session — reply to a notification or use /sessions")
        return
    queue_inbox(target["session_id"], target["cwd"], text)


def poll_loop():
    if not BOT_TOKEN:
        log("dry-run: no BOT_TOKEN, telegram polling disabled")
        return
    offset = 0
    while True:
        try:
            r = telegram("getUpdates", {"timeout": 50, "offset": offset})
            for u in r.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                try:
                    handle_update(u)
                except Exception as e:
                    log(f"update error: {e}")
        except Exception as e:
            log(f"poll error: {e}")
            time.sleep(5)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if SECRET and self.headers.get("X-Bridge-Token") != SECRET:
            self.send_response(403)
            self.end_headers()
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n)
        except Exception:
            body = b""
        self.send_response(200)
        self.end_headers()
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}
        if self.path == "/event":
            try:
                handle_event(data)
            except Exception as e:
                log(f"event error: {e}")
        elif self.path == "/deliver-status":
            reply_chat("⚠️ " + str(data.get("text") or "delivery status"))
        elif self.path == "/shutdown":
            log("shutdown requested")
            threading.Thread(target=self.server.shutdown, daemon=True).start()


class Server(ThreadingHTTPServer):
    allow_reuse_address = False


def main():
    LOGS.mkdir(exist_ok=True)
    SPIKE.mkdir(exist_ok=True)
    try:
        server = Server(("127.0.0.1", PORT), Handler)
    except OSError:
        log(f"port {PORT} already in use — another instance running, exiting")
        return
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=send_loop, daemon=True).start()
    log(f"daemon up on 127.0.0.1:{PORT} dry_run={not BOT_TOKEN} owner={OWNER_ID or 'UNSET'}")
    server.serve_forever()


if __name__ == "__main__":
    main()
