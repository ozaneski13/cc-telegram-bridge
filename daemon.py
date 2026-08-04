import hashlib
import json
import os
import sys
import threading
import time
import urllib.parse
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
HOLD_SECONDS = int(ENV.get("HOLD_SECONDS", "600") or "600")
NOTIFY_GRACE = int(ENV.get("NOTIFY_GRACE_SECONDS", "180") or "180")
ASK_WAIT = int(ENV.get("ASK_WAIT_SECONDS", "300") or "300")
ASK_MODE = (ENV.get("ASK_ANSWER_MODE", "input") or "input").strip().lower()
IGNORE_CWD = [s.strip().lower() for s in ENV.get("IGNORE_CWD_SUBSTRINGS", "cc-telegram-bridge").split(",") if s.strip()]

LOCK = threading.Lock()
PENDING = {}
LAST_SENT = {}
GLOBAL_SENDS = []
HOLDS = {}
HOT_PENDING = {}
SESS_STATE = {}
ASKS = {}
ASK_SEQ = [0]
CCD_SESSIONS_DIR = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude-code-sessions"
CCD_ID_CACHE = {}
HOME = Path(os.environ.get("USERPROFILE") or Path.home())
SETTINGS_PATH = HOME / ".claude" / "settings.json"
CREDS_PATH = HOME / ".claude" / ".credentials.json"
MODEL_IDS = {"opus": "claude-opus-5", "sonnet": "claude-sonnet-5", "fable": "claude-fable-5",
             "haiku": "claude-haiku-4-5-20251001"}
EFFORTS = ("low", "medium", "high", "xhigh")


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
        s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    for k, v in (("msg_map", {}), ("recent", []), ("last_session", None), ("chat_id", None),
                 ("inbox_seq", 0), ("dry_seq", 0), ("last_tg", 0), ("last_local", 0), ("pending", {})):
        s.setdefault(k, v)
    return s


STATE = load_state()


def save_state():
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def remote_active():
    return STATE.get("last_tg", 0) > STATE.get("last_local", 0)


def ccd_info(cli_sid):
    c = CCD_ID_CACHE.get(cli_sid)
    if c and c.get("path"):
        try:
            d = json.loads(Path(c["path"]).read_text(encoding="utf-8"))
            return d.get("sessionId"), d.get("title")
        except Exception:
            pass
    if c and not c.get("path") and time.time() - c.get("checked", 0) < 60:
        return None, None
    try:
        for p in CCD_SESSIONS_DIR.rglob("local_*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("cliSessionId") == cli_sid:
                CCD_ID_CACHE[cli_sid] = {"path": str(p), "checked": time.time()}
                return d.get("sessionId"), d.get("title")
    except Exception:
        pass
    CCD_ID_CACHE[cli_sid] = {"path": None, "checked": time.time()}
    return None, None


def resolve_ccd_id(cli_sid):
    return ccd_info(cli_sid)[0]


def session_label(sid, cwd):
    title = None
    try:
        title = ccd_info(sid)[1]
    except Exception:
        pass
    return title or (Path(cwd).name if cwd else "?")


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


def read_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_settings(d):
    try:
        text = json.dumps(d, indent=2, ensure_ascii=False)
        json.loads(text)
        SETTINGS_PATH.with_suffix(".json.bridge-bak").write_text(SETTINGS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)
        return True
    except Exception as e:
        log(f"settings write failed: {e}")
        return False


def session_file(cli_sid):
    ccd_info(cli_sid)
    c = CCD_ID_CACHE.get(cli_sid) or {}
    return Path(c["path"]) if c.get("path") else None


def patch_session(cli_sid, field, value):
    p = session_file(cli_sid)
    if not p or not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        d[field] = value
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        return True
    except Exception as e:
        log(f"session patch failed: {e}")
        return False


def list_ccd_sessions(limit=10):
    out = []
    try:
        for p in CCD_SESSIONS_DIR.rglob("local_*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("isArchived") or not d.get("cliSessionId"):
                continue
            out.append({"cli": d["cliSessionId"], "local": d.get("sessionId"), "title": d.get("title") or "",
                        "cwd": d.get("cwd") or "", "model": d.get("model") or "", "effort": d.get("effort") or "",
                        "ts": (d.get("lastActivityAt") or 0) / 1000.0, "path": str(p)})
    except Exception as e:
        log(f"session scan failed: {e}")
    out.sort(key=lambda r: r["ts"], reverse=True)
    return out[:limit]


def bar(pct):
    filled = max(0, min(10, round(pct / 10)))
    return "█" * filled + "░" * (10 - filled)


def local_time(iso):
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso).astimezone().strftime("%a %H:%M")
    except Exception:
        return "?"


def usage_text():
    try:
        tok = json.loads(CREDS_PATH.read_text(encoding="utf-8"))["claudeAiOauth"]["accessToken"]
    except Exception:
        return "usage unavailable — could not read local Claude credentials"
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage",
                                 headers={"Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return f"usage unavailable ({type(e).__name__}) — open Claude Code once to refresh the login"
    lines = ["📊 Usage"]
    names = {"session": "5-hour", "weekly_all": "week (all)", "weekly_scoped": "week"}
    for lim in d.get("limits") or []:
        name = names.get(lim.get("kind"), lim.get("kind", "?"))
        scope = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        if scope:
            name = f"week ({scope})"
        pct = int(lim.get("percent") or 0)
        flag = " ⚠️" if (lim.get("severity") or "") in ("warning", "critical") else ""
        lines.append(f"{name}: {bar(pct)} {pct}% · resets {local_time(lim.get('resets_at') or '')}{flag}")
    ex = d.get("extra_usage") or {}
    if ex.get("is_enabled"):
        lines.append(f"extra credits: {ex.get('utilization', 0):.0f}% of {ex.get('monthly_limit')}")
    return "\n".join(lines)


def status_text():
    s = read_settings() or {}
    with LOCK:
        last = STATE.get("last_session")
        rec = {r["session_id"]: r for r in STATE.get("recent", [])}
    target = "none"
    if last:
        target = f"{session_label(last, rec.get(last, {}).get('cwd', ''))} #{last[:8]}"
    return ("⚙️ Defaults for new sessions\n"
            f"model: {s.get('model', 'default')}\n"
            f"effort: {s.get('effortLevel', 'default')}\n"
            f"fast mode: {'on' if s.get('fastMode') else 'off'}\n"
            f"target chat: {target}\n\n" + usage_text())


def parse_target_arg(arg):
    parts = arg.split()
    value = parts[0].lower() if parts else ""
    rest = " ".join(parts[1:]).strip()
    if rest.lower() in ("global", "default", "new", "all"):
        return value, True, None, None
    if rest:
        t = resolve_target(rest.lstrip("#"))
        if not t:
            return value, False, None, f"chat not found: {rest} — list them with /sessions"
        return value, False, t, None
    with LOCK:
        last = STATE.get("last_session")
    if last:
        row = resolve_target(last[:8])
        if row:
            return value, False, row, None
    return value, False, None, None


def apply_to_chat(row, field, value, shown):
    if not patch_session(row["cli"], field, value):
        return "could not write that chat's saved state"
    name = row["title"] or (Path(row["cwd"]).name if row["cwd"] else "?")
    msg = (f"{name} #{row['cli'][:8]} → {field} {shown}\n"
           "saved into that chat's state: it will use this the next time you open the chat, not while it is already open")
    if time.time() - row["ts"] < 120:
        msg += ("\n⚠️ that chat was active moments ago. The app rewrites its own state at the end of every turn, "
                "so this will be erased before it ever reopens — close the chat first, or use 'global' for new chats.")
    return msg


def apply_default(field, value):
    s = read_settings()
    if s is None:
        return "settings.json unreadable"
    s[field] = value
    return None if write_settings(s) else "could not write settings"


MODEL_USAGE = "usage: /model opus|sonnet|fable|haiku [#chatid | N | global]  (add [1m] for 1M context)"
EFFORT_USAGE = "usage: /effort low|medium|high|xhigh [#chatid | N | global]"


def set_model(arg):
    key, is_global, row, err = parse_target_arg(arg)
    base = key[:-4] if key.endswith("[1m]") else key
    if base not in MODEL_IDS:
        return MODEL_USAGE
    if err:
        return err
    if is_global:
        cur = str((read_settings() or {}).get("model") or "")
        val = base + ("[1m]" if key.endswith("[1m]") or cur.endswith("[1m]") else "")
        e = apply_default("model", val)
        return e or f"default model → {val} (applies to new chats)"
    if not row:
        return "no target chat — add #chatid, or pick one with /sessions and /use N (or add 'global')"
    return apply_to_chat(row, "model", MODEL_IDS[base], base)


def set_effort(arg):
    lvl, is_global, row, err = parse_target_arg(arg)
    if lvl not in EFFORTS:
        return EFFORT_USAGE
    if err:
        return err
    if is_global:
        e = apply_default("effortLevel", lvl)
        return e or f"default effort → {lvl} (applies to new chats)"
    if not row:
        return "no target chat — add #chatid, or pick one with /sessions and /use N (or add 'global')"
    return apply_to_chat(row, "effort", lvl, lvl)


def set_fast(arg):
    s = read_settings()
    if s is None:
        return "settings.json unreadable"
    a = arg.strip().lower()
    if a in ("on", "1", "true"):
        val = True
    elif a in ("off", "0", "false"):
        val = False
    elif a == "":
        val = not bool(s.get("fastMode"))
    else:
        return "usage: /fast on|off"
    s["fastMode"] = val
    if not write_settings(s):
        return "could not write settings"
    return f"fast mode → {'on' if val else 'off'} (new sessions)"


HELP_TEXT = ("Commands\n"
             "/usage — plan limits\n"
             "/status — defaults + target chat + usage\n"
             "/sessions — recent chats (model/effort shown)\n"
             "/use N — switch target chat\n"
             "/model fable #chatid — that chat (or N, or 'global' for new chats)\n"
             "/effort high #chatid — same targeting\n"
             "/fast on|off\n\n"
             "Reply to a notification to answer that chat; a plain message goes to the target chat.")


def ask_keyboard(cid, qidx, q, selected):
    rows = []
    for i, opt in enumerate(q.get("options") or []):
        mark = "✅ " if i in selected else ""
        rows.append([{"text": (mark + str(opt.get("label", "?")))[:60], "callback_data": f"{cid}|{qidx}|{i}"}])
    if q.get("multiSelect"):
        rows.append([{"text": "✔️ Done", "callback_data": f"{cid}|{qidx}|d"}])
    rows.append([{"text": "✍️ Type an answer", "callback_data": f"{cid}|{qidx}|t"}])
    return {"inline_keyboard": rows}


def ask_text(a, qidx):
    q = a["questions"][qidx]
    head = f"[{a['label']}] ❓ {qidx + 1}/{len(a['questions'])}\n{q.get('question', '?')}"
    body = "\n".join(f"• {o.get('label', '?')}: {(o.get('description') or '')[:90]}" for o in (q.get("options") or []))
    return (head + ("\n" + body if body else ""))[:3900]


def ask_send(cid):
    a = ASKS.get(cid)
    if not a or not STATE.get("chat_id"):
        return
    qidx = a["idx"]
    try:
        r = telegram("sendMessage", {"chat_id": STATE["chat_id"], "text": ask_text(a, qidx),
                                     "reply_markup": ask_keyboard(cid, qidx, a["questions"][qidx], a["selected"])})
        if r.get("ok"):
            a["msg_id"] = r["result"]["message_id"]
    except Exception as e:
        log(f"ask_send failed: {e}")


def ask_close(cid, note):
    a = ASKS.get(cid)
    if not a or not a.get("msg_id") or not STATE.get("chat_id"):
        return
    try:
        telegram("editMessageText", {"chat_id": STATE["chat_id"], "message_id": a["msg_id"],
                                     "text": (ask_text(a, a["idx"]) + "\n\n" + note)[:3900]})
    except Exception as e:
        log(f"ask_close failed: {e}")


def ask_cancel_for_session(sid, note):
    for cid in [c for c, a in ASKS.items() if a["sid"] == sid and not a["done"]]:
        a = ASKS[cid]
        a["done"] = True
        a["answers"] = None
        a["event"].set()
        ask_close(cid, note)


def ask_advance(cid):
    a = ASKS[cid]
    q = a["questions"][a["idx"]]
    labels = [str((q.get("options") or [])[i].get("label", "")) for i in sorted(a["selected"])]
    a["answers"][q.get("question", "")] = ", ".join(labels) if labels else ""
    ask_close(cid, "→ " + (", ".join(labels) or "(empty)"))
    a["idx"] += 1
    a["selected"] = set()
    a["msg_id"] = None
    if a["idx"] >= len(a["questions"]):
        a["done"] = True
        a["event"].set()
    else:
        ask_send(cid)


def handle_callback(cq):
    if (cq.get("from") or {}).get("id") != OWNER_ID:
        return
    try:
        telegram("answerCallbackQuery", {"callback_query_id": cq.get("id")})
    except Exception:
        pass
    parts = (cq.get("data") or "").split("|")
    if len(parts) != 3:
        return
    cid, qidx, choice = parts[0], parts[1], parts[2]
    with LOCK:
        STATE["last_tg"] = time.time()
        save_state()
        a = ASKS.get(cid)
        if not a or a["done"] or str(a["idx"]) != qidx:
            return
        q = a["questions"][a["idx"]]
        if choice == "t":
            a["await_text"] = True
            reply = "send your answer as a normal message"
        elif choice == "d":
            ask_advance(cid)
            return
        elif choice.isdigit():
            i = int(choice)
            if i >= len(q.get("options") or []):
                return
            if q.get("multiSelect"):
                a["selected"].symmetric_difference_update({i})
                try:
                    telegram("editMessageReplyMarkup", {"chat_id": STATE["chat_id"], "message_id": a["msg_id"],
                                                        "reply_markup": ask_keyboard(cid, a["idx"], q, a["selected"])})
                except Exception:
                    pass
                return
            a["selected"] = {i}
            ask_advance(cid)
            return
        else:
            return
    reply_chat(reply)


def ask_take_text(text):
    with LOCK:
        for cid, a in ASKS.items():
            if a["done"] or not a.get("await_text"):
                continue
            q = a["questions"][a["idx"]]
            a["answers"][q.get("question", "")] = text
            a["await_text"] = False
            ask_close(cid, "→ " + text[:100])
            a["idx"] += 1
            a["selected"] = set()
            a["msg_id"] = None
            if a["idx"] >= len(a["questions"]):
                a["done"] = True
                a["event"].set()
            else:
                ask_send(cid)
            return True
    return False


def ask_start(sid, cwd, questions):
    with LOCK:
        if not remote_active() or not STATE.get("chat_id"):
            return None
        ASK_SEQ[0] += 1
        cid = str(ASK_SEQ[0])
        ASKS[cid] = {"sid": sid, "label": session_label(sid, cwd), "questions": questions, "idx": 0,
                     "selected": set(), "answers": {}, "done": False, "await_text": False,
                     "event": threading.Event(), "deadline": time.time() + ASK_WAIT, "msg_id": None}
        ask_send(cid)
    return {"cid": cid, "wait": ASK_WAIT, "mode": ASK_MODE}


def ask_poll(cid):
    with LOCK:
        a = ASKS.get(cid)
    if not a:
        return {"keep": False}
    a["event"].wait(timeout=25)
    with LOCK:
        if a["done"]:
            ASKS.pop(cid, None)
            return {"answers": a["answers"]} if a["answers"] else {"keep": False}
        if time.time() > a["deadline"]:
            a["done"] = True
            ASKS.pop(cid, None)
            ask_close(cid, "⌛ expired — answer in the app")
            return {"keep": False}
    return {"keep": True}


def notify(sid, cwd, kind, text):
    h = hashlib.md5(text.encode("utf-8", "replace")).hexdigest()
    with LOCK:
        delay = 3 if remote_active() else max(3, NOTIFY_GRACE)
        PENDING[sid] = {"due": time.time() + delay, "kind": kind, "hash": h, "text": text, "cwd": cwd}


def prune_pending_locked():
    try:
        cursor = int(CURSOR_PATH.read_text().strip() or "0") if CURSOR_PATH.exists() else 0
    except Exception:
        return
    changed = False
    for sid in list(STATE["pending"].keys()):
        kept = [p for p in STATE["pending"][sid] if p.get("off", 0) >= cursor]
        if len(kept) != len(STATE["pending"][sid]):
            changed = True
            if kept:
                STATE["pending"][sid] = kept
            else:
                del STATE["pending"][sid]
    if changed:
        save_state()


def pop_pending_locked(sid):
    prune_pending_locked()
    items = STATE["pending"].pop(sid, [])
    if not items:
        return ""
    save_state()
    texts = "\n".join("- " + p["text"] for p in items)
    return ("[Telegram] The user sent the following message(s) from their phone while this session was idle. "
            "Treat them as normal user messages and act on them:\n" + texts)


def release_holds_locked():
    for e in HOLDS.values():
        e["deadline"] = 0
        e["event"].set()


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
        return {}
    if any(s in cwd.lower() for s in IGNORE_CWD):
        return {}
    if ev == "UserPromptSubmit":
        with LOCK:
            STATE["last_local"] = time.time()
            SESS_STATE[sid] = "running"
            release_holds_locked()
            PENDING.clear()
            inject = pop_pending_locked(sid)
            save_state()
            ask_cancel_for_session(sid, "↩️ cancelled — answered at the PC")
        return {"inject": inject}
    if ev == "SessionStart":
        with LOCK:
            inject = pop_pending_locked(sid)
        return {"inject": inject}
    if ev == "Notification":
        notify(sid, cwd, "notify", "⏳ " + (data.get("message") or "waiting for input"))
        return {}
    if ev == "PreToolUse":
        tool = data.get("tool_name")
        ti = data.get("tool_input") or {}
        with LOCK:
            SESS_STATE[sid] = "asking"
        if tool == "AskUserQuestion":
            questions = ti.get("questions") or []
            if questions:
                started = ask_start(sid, cwd, questions)
                if started:
                    return {"ask": started}
            notify(sid, cwd, "question", "❓ Question:\n" + format_questions(ti))
        elif tool == "ExitPlanMode":
            notify(sid, cwd, "plan", "📋 Plan awaiting approval:\n" + last_assistant_text(tp))
        return {}
    if ev == "Stop":
        text = (data.get("last_assistant_message") or "").strip()
        if text:
            text = text if len(text) <= 700 else "…" + text[-700:]
        else:
            text = last_assistant_text(tp)
        running_bg = [t for t in data.get("background_tasks") or [] if t.get("status") == "running"]
        icon = f"🔄({len(running_bg)} bg) " if running_bg else "✅ "
        notify(sid, cwd, "stop", icon + text)
        hold = 0
        with LOCK:
            if remote_active():
                hold = HOLD_SECONDS
                entry = {"deadline": time.time() + hold, "event": threading.Event(), "reply": None}
                hp = HOT_PENDING.pop(sid, None)
                if hp:
                    entry["reply"] = "\n".join(hp)
                    entry["event"].set()
                HOLDS[sid] = entry
                SESS_STATE[sid] = "holding"
            else:
                SESS_STATE[sid] = "idle"
        return {"hold": hold}
    return {}


def hold_wait(sid):
    with LOCK:
        entry = HOLDS.get(sid)
    if not entry:
        return {"keep": False}
    entry["event"].wait(timeout=25)
    with LOCK:
        if entry.get("reply"):
            text = entry["reply"]
            entry["reply"] = None
            HOLDS.pop(sid, None)
            SESS_STATE[sid] = "running"
            return {"reply": text}
        if time.time() > entry["deadline"] or not remote_active():
            HOLDS.pop(sid, None)
            SESS_STATE[sid] = "idle"
            return {"keep": False}
        entry["event"].clear()
    return {"keep": True}


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
    proj = session_label(sid, item["cwd"])
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
    rows = list_ccd_sessions()
    with LOCK:
        last = STATE.get("last_session")
    if not rows:
        return "no chats found"
    short = {"claude-opus-5": "opus", "claude-fable-5": "fable", "claude-sonnet-5": "sonnet"}
    lines = []
    for i, r in enumerate(rows, 1):
        name = r["title"] or (Path(r["cwd"]).name if r["cwd"] else "?")
        mark = " *" if r["cli"] == last else ""
        model = short.get(r["model"], (r["model"] or "").replace("claude-", ""))
        lines.append(f"{i}. {name[:34]} #{r['cli'][:8]} · {model}/{r['effort']} · {humanize(r['ts'])}{mark}")
    return "\n".join(lines)


def resolve_target(arg):
    rows = list_ccd_sessions(20)
    if arg.isdigit() and 1 <= int(arg) <= len(rows):
        return rows[int(arg) - 1]
    for r in rows:
        if arg and (r["cli"].startswith(arg) or arg.lower() in (r["title"] or "").lower()):
            return r
    return None


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


def queue_cold(session_id, cwd, text):
    deliver_id = resolve_ccd_id(session_id) or session_id
    off = INBOX_PATH.stat().st_size if INBOX_PATH.exists() else 0
    with LOCK:
        STATE["inbox_seq"] = STATE.get("inbox_seq", 0) + 1
        seq = STATE["inbox_seq"]
        STATE["pending"].setdefault(session_id, []).append({"text": text, "off": off})
        save_state()
    with open(INBOX_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": seq, "ts": time.time(), "session_id": deliver_id, "cli_session_id": session_id, "cwd": cwd, "text": text}, ensure_ascii=False) + "\n")


def route_reply(session_id, cwd, text):
    proj = session_label(session_id, cwd)
    with LOCK:
        hold = HOLDS.get(session_id)
        if hold and time.time() <= hold["deadline"]:
            hold["reply"] = (hold["reply"] + "\n" + text) if hold.get("reply") else text
            hold["event"].set()
            mode = "live"
        elif SESS_STATE.get(session_id) == "running" and remote_active():
            HOT_PENDING.setdefault(session_id, []).append(text)
            mode = "live-soon"
        else:
            mode = "cold"
    if mode == "cold":
        queue_cold(session_id, cwd, text)
        conf = f"→ {proj} #{session_id[:8]} (session idle — delivered when it wakes, or via bridge)"
    elif mode == "live-soon":
        conf = f"⚡ → {proj} #{session_id[:8]} (delivered at end of current turn)"
    else:
        conf = f"⚡ → {proj} #{session_id[:8]}"
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
        STATE["last_tg"] = time.time()
        if STATE.get("chat_id") != chat_id:
            STATE["chat_id"] = chat_id
        now = time.time()
        for item in PENDING.values():
            item["due"] = min(item["due"], now)
        save_state()
    text = (msg.get("text") or "").strip()
    if not text:
        reply_chat("text messages only")
        return
    if ask_take_text(text):
        return
    cmd = text.split()[0].lower()
    arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
    if cmd in ("/help", "/start"):
        reply_chat(HELP_TEXT)
        return
    if cmd == "/usage":
        reply_chat(usage_text())
        return
    if cmd == "/status":
        reply_chat(status_text())
        return
    if cmd == "/model":
        reply_chat(set_model(arg) if arg else MODEL_USAGE)
        return
    if cmd == "/effort":
        reply_chat(set_effort(arg) if arg else EFFORT_USAGE)
        return
    if cmd == "/fast":
        reply_chat(set_fast(arg))
        return
    if cmd == "/sessions":
        reply_chat(sessions_list())
        return
    if cmd == "/use":
        target = resolve_target(arg)
        if not target:
            reply_chat("not found — list with /sessions")
            return
        with LOCK:
            STATE["last_session"] = target["cli"]
            update_recent(target["cli"], target["cwd"])
            save_state()
        name = target["title"] or (Path(target["cwd"]).name if target["cwd"] else "?")
        reply_chat(f"active: {name} #{target['cli'][:8]}")
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
    route_reply(target["session_id"], target["cwd"], text)


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
                    if u.get("callback_query"):
                        handle_callback(u["callback_query"])
                    else:
                        handle_update(u)
                except Exception as e:
                    log(f"update error: {e}")
        except Exception as e:
            log(f"poll error: {e}")
            time.sleep(5)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if SECRET and self.headers.get("X-Bridge-Token") != SECRET:
            self.send_response(403)
            self.end_headers()
            return
        if parsed.path == "/hold":
            sid = (urllib.parse.parse_qs(parsed.query).get("sid") or [""])[0]
            try:
                self._json(hold_wait(sid))
            except Exception as e:
                log(f"hold error: {e}")
                self._json({"keep": False})
            return
        if parsed.path == "/ask-poll":
            cid = (urllib.parse.parse_qs(parsed.query).get("cid") or [""])[0]
            try:
                self._json(ask_poll(cid))
            except Exception as e:
                log(f"ask-poll error: {e}")
                self._json({"keep": False})
            return
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
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            data = {}
        if self.path == "/event":
            try:
                resp = handle_event(data)
            except Exception as e:
                log(f"event error: {e}")
                resp = {}
            self._json(resp)
            return
        if self.path == "/deliver-status":
            self._json({})
            reply_chat("⚠️ " + str(data.get("text") or "delivery status"))
            return
        if self.path == "/debug-inbound":
            sid = data.get("sid") or ""
            with LOCK:
                STATE["last_tg"] = time.time()
                save_state()
            self._json({"ok": True})
            if sid:
                route_reply(sid, data.get("cwd") or "", data.get("text") or "")
            return
        if self.path == "/shutdown":
            self._json({})
            log("shutdown requested")
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self.send_response(404)
        self.end_headers()


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
    log(f"daemon up on 127.0.0.1:{PORT} dry_run={not BOT_TOKEN} owner={OWNER_ID or 'UNSET'} hold={HOLD_SECONDS}s grace={NOTIFY_GRACE}s ask={ASK_WAIT}s/{ASK_MODE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
