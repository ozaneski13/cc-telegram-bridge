# cc-telegram-bridge

Control your **Claude Code Desktop** sessions from Telegram.

- When Claude finishes an answer, asks a question, or waits for you — you get a Telegram message.
- You reply on your phone — your reply goes straight into the right session, and Claude keeps working.
- When you are at your PC, nothing buzzes: notifications are held for a few minutes and cancelled if you react in the app.
- Multiple-choice questions arrive as tappable buttons, and you can check your plan usage or switch model / effort / fast mode from the phone.

Everything uses official Claude Code mechanisms (a plugin, hooks, and the desktop app's own tools). No patched binaries.

*Türkçe dokümantasyon: [README.tr.md](README.tr.md)*

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
- Python 3.10+ (used once, to build the two executables)

---

## Setup — step by step

**1. Get the code and install:**

```powershell
git clone https://github.com/ozaneski13/cc-telegram-bridge.git
cd cc-telegram-bridge
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` does everything local: builds the executables (first run only), installs the Claude Code plugin, sets up autostart, and starts the background daemon. You can re-run it any time; it is safe.

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
taskkill /IM cc-telegram-bridge.exe /F
.\cc-telegram-bridge.exe
```

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
| `/sessions` | Lists recent sessions, numbered (`*` = current target) |
| `/use 2` or `/use a1b2` | Switches the target for plain messages |
| `/usage` | Your plan limits: 5-hour and weekly windows with reset times |
| `/status` | Current defaults, target chat, and usage in one message |
| `/model opus\|sonnet\|fable\|haiku` | Sets the model (append `[1m]` for 1M context) |
| `/effort low\|medium\|high\|xhigh` | Sets the reasoning effort |
| `/fast on\|off` | Toggles fast mode |
| `/help` | Command list |

`/model`, `/effort` and `/fast` write your Claude Code settings, so they apply to **sessions started afterwards**. `/model` and `/effort` are additionally stamped on the current target chat, which takes effect the next time you open that chat. `/usage` reads your plan limits with the login already stored on your machine — nothing extra to configure.

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
| Start | run `cc-telegram-bridge.exe` (or just use Claude — hooks auto-start it) |
| Rebuild after code changes | `powershell -ExecutionPolicy Bypass -File build.ps1` then re-run `setup.ps1` |
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

## Moving to another PC (same Claude account)

1. On the **old** PC: `taskkill /IM cc-telegram-bridge.exe /F` and delete `shell:startup\cc-telegram-bridge.lnk`. (Two PCs polling one bot token conflict and cause duplicate notifications.)
2. Copy the project folder to the new PC — or `git clone` it and copy just your `.env` (and optionally `state.json`, which keeps the chat binding).
3. On the **new** PC run `setup.ps1`, then restart the Claude app once. Done — nothing is tied to a username or folder location.

---

## Security & privacy

- The daemon listens on **127.0.0.1 only**; hook calls are authenticated with a shared secret.
- `/usage` reads the OAuth token Claude Code already stores locally and sends it only to Anthropic's own API. `/model`, `/effort` and `/fast` edit only those three keys in `~/.claude/settings.json`, keep a `.bridge-bak` copy, and validate the file before replacing it.
- Only your Telegram id is accepted — there is nothing a stranger can do by finding your bot.
- Your bot token lives only in your local `.env` (gitignored). No secrets are stored anywhere else.
- **Summaries of Claude's answers travel through Telegram's servers.** For sensitive projects, add the folder name to `IGNORE_CWD_SUBSTRINGS`.
- No binaries ship in this repo; you build both executables locally from readable, stdlib-only Python.

## Limitations

- Multiple-choice questions are answerable from Telegram (inline buttons). Plan-approval and permission dialogs are not — they notify only, and your reply arrives as a normal message.
- If a question still opens in the app after you tap a button, set `ASK_ANSWER_MODE=deny` and restart the daemon.
- Reply injection needs Claude Code Desktop. Notifications alone work with anything that runs Claude Code hooks.
- Windows-only as shipped (PowerShell scripts, Startup shortcut); the daemon itself is portable Python.

## License

[MIT](LICENSE) — © 2026 Ozan Eşki.
