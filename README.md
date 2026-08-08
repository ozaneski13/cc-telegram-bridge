# cc-telegram-bridge

Control your **Claude Code Desktop** sessions from Telegram.

- When Claude finishes an answer, asks a question, or waits for you — you get a Telegram message.
- You reply on your phone — your reply goes straight into the right session, and Claude keeps working.
- When you are at your PC, nothing buzzes: notifications are held for a few minutes and cancelled if you react in the app.
- Multiple-choice questions arrive as tappable buttons, and you can check your plan usage or switch model / effort / fast mode from the phone.

Everything uses official Claude Code mechanisms (a plugin, hooks, and the desktop app's own tools). No patched binaries.

*Türkçe dokümantasyon: [README.tr.md](README.tr.md) · Picking this up on a new machine? [docs/RESUME.md](docs/RESUME.md)*

---

## How it behaves

| Situation | What happens |
|---|---|
| You are at the PC | Notifications wait 3 minutes (`NOTIFY_GRACE_SECONDS`). If you type anything in the app during that time, they are cancelled — your phone stays silent. |
| You are away | After the grace period, the notification arrives on Telegram: `[session title #id]` + a summary of what Claude said. |
| You reply from Telegram | "Live mode" turns on. Your reply is injected directly into the session and Claude continues. Follow-up answers reach your phone instantly (no grace delay). Sessions briefly wait at each turn end (`HOLD_SECONDS`, default 10 min) to catch your next reply. |
| Claude asks a multiple-choice question while you are on the phone | It arrives with one inline button per option (plus "type an answer" for free text; multi-select supported). Tap and the session continues — the question never has to be answered at the PC. At the PC it simply opens in the app as usual; nothing waits. |
| You come back to the PC | The moment you type anything in the app, live mode ends and everything returns to normal desk behavior. A question waiting on your phone is cancelled and opens in the app instead. |
| You message a session that has been idle a long time | The message is queued. It is delivered automatically the next time that session wakes up (you type in it, or the app restarts). If you want instant delivery even then, see [Optional: bridge session](#optional-bridge-session). |

Notification icons: `✅` answer finished · `🔄(N bg)` still working in background · `⏳` waiting for input · `❓` multiple-choice question · `📋` plan awaiting approval.

---

## Requirements

- Windows 10/11
- [Claude Code Desktop](https://claude.com/claude-code), logged in
- A Telegram account
- Python 3.10+ on `PATH` — the daemon and the hook run straight from the `.py` sources; nothing is compiled or packed

---

## Setup — step by step

**1. Get the code and install:**

```powershell
git clone https://github.com/ozaneski13/cc-telegram-bridge.git
cd cc-telegram-bridge
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` does everything local: finds your Python, installs the Claude Code plugin (writing your interpreter's path into its hook config), sets up autostart, and starts the background daemon with `pythonw`. You can re-run it any time; it is safe.

**2. Create your Telegram bot:**

1. In Telegram, open [@BotFather](https://t.me/BotFather) and send `/newbot`.
2. Give it a name, then a username ending in `bot` (e.g. `my_claude_bot`).
3. BotFather replies with a **token** like `123456789:AAH...` — copy it.

**3. Find your numeric Telegram id:**

1. Open [@userinfobot](https://t.me/userinfobot) and press Start.
2. It replies with your id, e.g. `412587349`.

**4. Put both into the `.env` file** (in the project folder):

```
BOT_TOKEN=123456789:AAH...
TELEGRAM_OWNER_ID=412587349
```

This file stays on your machine only — it is gitignored and never leaves your PC.

**5. Restart the daemon** so it picks up the token:

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

(`setup.ps1` restarts it for you. To do it by hand: end the `pythonw` process, then `pythonw daemon.py`.)

**6. Send your bot one DM** (anything, e.g. "hi"). This binds the chat. Only messages from your id are accepted; everyone else is silently ignored.

**7. Restart the Claude Code Desktop app once.** The plugin loads when a session starts, so chats that were already open before the install stay silent until reopened. One app restart fixes all of them at once.

**8. Test:** open a chat, ask something, then don't touch the app. After the grace period (3 min) the answer should appear on your phone. Swipe-reply to it — Claude should continue with your reply.

That's the whole setup. From now on everything is automatic: the daemon starts at logon, and any Claude activity restarts it if it ever stops.

---

## Daily use

| You send on Telegram | What happens |
|---|---|
| Swipe-reply to a notification | Your text goes to that exact session |
| A plain message | Goes to the most recently notified session |
| `/sessions` | Lists your chats from the app, numbered, with their model and effort (`*` = current target) |
| `/use 2`, `/use a1b2`, `/use drift` | Switches the target for plain messages (number, id, or title) |
| `/usage` | Your plan limits: 5-hour and weekly windows with reset times |
| `/status` | Current defaults, target chat, and usage in one message |
| `/model opus\|sonnet\|fable\|haiku [#chat\|N\|global]` | Sets the model (append `[1m]` for 1M context) |
| `/effort low\|medium\|high\|xhigh [#chat\|N\|global]` | Sets the reasoning effort |
| `/fast on\|off` | Toggles fast mode |
| `/help` | Command list |

**Scope rules.** `/model` and `/effort` change one chat. Name it inline — `/model fable #a1b2c3d4`, `/model fable 6` (the number from `/sessions`), or by title — or omit it to use the current target chat. Add `global` — `/model fable global` — to change the default for **new** chats instead. `/fast` is global only.

A per-chat change is stored in that chat's saved state, so it applies the next time the chat is opened. The desktop app rewrites its own state for the chat you are actively using, so a chat that is open right now will overwrite the change — close it first, or use `global`.

**There is no way to switch a running chat's model instantly from here.** Writing its state is overwritten by the app, and injected messages reach the session as plain text without going through the client's slash-command handling, so `/model` cannot be triggered remotely. To steer a live session from your phone, use Anthropic's own Remote Control (claude.ai/code or the Claude mobile app).

`/usage` reads your plan limits with the login already stored on your machine — nothing extra to configure.

Delivery confirmations you get back: `⚡ →` delivered live · `→ ... (session idle)` queued for when the session wakes.

---

## Optional: bridge session

Live mode covers active conversations. If you also want **instant** delivery into sessions that have been idle longer than the hold window, open one dedicated relay session:

1. In Claude Code, open a new session **in the `cc-telegram-bridge` folder** (so it doesn't notify about itself).
2. Type `/cc-telegram-bridge` and leave it open.

If it's closed, nothing breaks — queued messages are still delivered when the target session wakes up.

---

## Managing the daemon

| Action | Command |
|---|---|
| Is it running? | `curl.exe http://127.0.0.1:8765/health` → `ok` |
| Stop | `curl.exe -X POST http://127.0.0.1:8765/shutdown -H "X-Bridge-Token: <BRIDGE_SECRET from .env>"` |
| Start | `pythonw daemon.py` (or just use Claude — the hook starts it automatically) |
| Apply code changes | re-run `setup.ps1` (it restarts the daemon and re-installs the plugin) |
| Disable the plugin | `claude plugin disable cc-telegram-bridge@skills-dir` |

---

## Configuration (`.env`)

| Key | Meaning | Default |
|---|---|---|
| `BOT_TOKEN` | Your bot's token from BotFather | — |
| `TELEGRAM_OWNER_ID` | Your numeric Telegram id; only this id is accepted | — |
| `BRIDGE_SECRET` | Shared secret between hooks and daemon (auto-generated) | — |
| `PORT` | Local port, 127.0.0.1 only | `8765` |
| `NOTIFY_GRACE_SECONDS` | How long notifications wait while you may be at the PC; `0` = near-immediate | `180` |
| `HOLD_SECONDS` | How long sessions wait for your next phone reply in live mode | `600` |
| `ASK_WAIT_SECONDS` | How long a multiple-choice question waits for your button tap (live mode only) | `300` |
| `ASK_ANSWER_MODE` | `input` pre-fills the tool's answers; `deny` returns the answer as feedback text instead | `input` |
| `IGNORE_CWD_SUBSTRINGS` | Comma-separated folder-name parts whose sessions never notify | `cc-telegram-bridge` |

Restart the daemon after changing `.env`.

---

## Moving to another PC, or reinstalling Windows

**Back up exactly two files** — everything else is either in this repository or regenerated by `setup.ps1`:

| File | Why | If you lose it |
|---|---|---|
| `.env` | your bot token, your Telegram id, the shared secret | Create a new bot with @BotFather and re-fill `.env`; the secret is regenerated automatically |
| `state.json` *(optional)* | which Telegram chat is bound, and recent targets | Nothing breaks — DM the bot once and it rebinds |

Not worth keeping: `logs/`, `inbox.jsonl`, `inbox.cursor`, `spike/`. The bot itself lives on Telegram's servers and survives any reinstall.

**Then, on the new machine:**

1. On the **old** PC, if it still exists: stop the daemon (the shutdown command above, or end its `pythonw` process) and delete `shell:startup\cc-telegram-bridge.lnk`. Two machines polling one bot token conflict and cause duplicate notifications.
2. `git clone` the repository and drop your `.env` next to `daemon.py`.
3. Run `setup.ps1`, then restart the Claude Code Desktop app once. Nothing is tied to a username or folder location.

---

## Is this safe to run?

This tool sits between your code assistant and a chat app, so it deserves scrutiny. Everything below is verifiable from the source in about a minute — please check rather than take my word for it.

**Verify it yourself:**

```bash
grep -hE "^import |^from " daemon.py plugin/hooks/notify_event.py | sort -u   # dependencies
grep -ohE "https?://[a-zA-Z0-9./_-]+" daemon.py plugin/hooks/notify_event.py  # every outbound address
grep -nE "subprocess|os.system|eval\(|exec\(|shell=True" daemon.py plugin/hooks/notify_event.py
grep -nE "open\(.*['\"]w|write_text|os.replace" daemon.py                     # every file it writes
```

What those commands show, and what it means:

- **No dependencies.** Python standard library only — nothing is pulled from PyPI at runtime, so there is no supply chain to trust. About 1,300 lines total, small enough to read end to end.
- **No binaries anywhere.** Nothing is compiled or packed: your Python interpreter runs the `.py` files you just read, so what executes is exactly what you can audit. (This is also why Windows Defender is happy — see [Troubleshooting](#troubleshooting).)
- **Three network destinations, ever:** `127.0.0.1` (hooks → daemon), `api.telegram.org` (your bot), and `api.anthropic.com/api/oauth/usage` (only for `/usage`). No telemetry, no analytics, no third-party endpoint.
- **It never executes anything you send.** The only process it ever launches is its own daemon executable — no shell, no `eval`, no command built from a message. Telegram text is carried as text.
- **It writes to a fixed set of paths:** its own folder (state, queue, logs), the `model`/`effort` field of a named chat's saved state, and — only for `global`/`/fast` — the `model`, `effortLevel` and `fastMode` keys of `~/.claude/settings.json`, backed up to `.bridge-bak` and validated before replacing. Any other value is rejected.
- **Only your numeric Telegram id is accepted;** everything else is dropped silently, so a stranger who finds your bot gets nothing. The local HTTP endpoint listens on loopback only and requires a shared secret.
- **Your bot token never leaves `.env`,** which is gitignored. The daemon holds no other credential; `/usage` reads the OAuth token Claude Code already stored on your machine and sends it only to Anthropic.

**What it genuinely exposes — decide if you accept it:**

- Summaries of Claude's answers are sent to Telegram, so they pass through Telegram's servers and are stored in your chat history. Telegram bot messages are not end-to-end encrypted. Mute sensitive projects with `IGNORE_CWD_SUBSTRINGS`.
- A reply you send from Telegram becomes a user message in a session running with your permissions. If you use Claude Code in a permissive mode, that message can lead to file changes — so anyone with access to your unlocked Telegram account has that reach too. The bot token itself is equally sensitive: whoever holds it can read what you send to the bot.
- The daemon trusts local processes that hold the shared secret. Anything already running as your user could read `.env` anyway, so this is not a new boundary — but it is not a defence against a compromised machine either.

## Limitations

- Multiple-choice questions are answerable from Telegram (inline buttons). Plan-approval and permission dialogs are not — they notify only, and your reply arrives as a normal message.
- If a question still opens in the app after you tap a button, set `ASK_ANSWER_MODE=deny` and restart the daemon.
- Reply injection needs Claude Code Desktop. Notifications alone work with anything that runs Claude Code hooks.
- Windows-only as shipped (PowerShell scripts, Startup shortcut); the daemon itself is portable Python.

## Troubleshooting

**Windows Defender flagged the bridge.** Earlier versions shipped a PyInstaller-packed `.exe`, and Defender's machine-learning heuristics scored it as a trojan: a self-installing single-file binary that opens a socket, polls a remote server, and launches processes looks exactly like a remote-access tool from the outside. It was a false positive on our own build — but rather than ask you to add an antivirus exclusion, the packing was removed entirely. The daemon and the hook now run as plain `.py` files under your own Python interpreter, which is signed and trusted, so there is nothing for the heuristic to score. If you are upgrading from a version that had `cc-telegram-bridge.exe`, delete it, delete `Startup\cc-telegram-bridge.lnk`, and run `setup.ps1` again.

**Notifications stopped after an update.** Plugins load when a session starts. Restart the Claude Code Desktop app once so every open chat picks up the current hooks.

**A chat never notifies.** Check that its folder name is not matched by `IGNORE_CWD_SUBSTRINGS`, then confirm the daemon is up with the health check above.

## Platform notes

[docs/platform-notes.md](docs/platform-notes.md) records what was measured about Claude Code Desktop while building this — how hooks and plugins load, the two session-id spaces, what a delivered message is and is not, and several things that turned out to be impossible. Worth reading before extending the bridge or building something similar.

## Security

Found something? See [SECURITY.md](SECURITY.md) — sensitive reports go through GitHub's private vulnerability reporting.

## License

[MIT](LICENSE) — © 2026 Ozan Eşki.
