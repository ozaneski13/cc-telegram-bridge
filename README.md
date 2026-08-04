# cc-telegram-bridge

Two-way Telegram bridge for **Claude Code Desktop** on Windows. Get a Telegram notification whenever *any* of your Claude Code sessions finishes a response, asks a question, or waits for input — and reply from your phone, routed back into the correct session.

```
Claude Code session (any) ──hook POST──> daemon (127.0.0.1:8765)
                                           ├─ Telegram sendMessage (notification)
                                           └─ getUpdates long-poll
Telegram reply ──> daemon ──append──> inbox.jsonl ──file watch──> bridge session
                                                     └─ send_message(target_session, text)
```

Everything runs through official Claude Code mechanisms: a [plugin](https://code.claude.com/docs/en/plugins) carries the hooks and the bridge skill, [hooks](https://code.claude.com/docs/en/hooks) push the events, and the desktop app's own session-management tool delivers replies as user turns. No patched binaries, no unofficial APIs.

## Features

- **All sessions, one bot** — hooks are global; every Claude Code Desktop session notifies, tagged `[session title #sessionid]`.
- **Live mode (zero-setup replies)** — once you message from Telegram, sessions hold briefly at each turn end (`HOLD_SECONDS`, default 10 min) and your replies are injected directly via the official Stop-hook `decision: block` mechanism. No bridge session, no daily setup. Typing anything locally instantly returns everything to normal desk behavior.
- **At-the-PC quietness** — notifications wait a grace period (`NOTIFY_GRACE_SECONDS`, default 3 min) before going to Telegram; if you react in the app meanwhile (type any prompt), pending notifications are cancelled. In live mode the grace is skipped, so phone conversations stay instant.
- **Event types** — response finished (`✅`), still working in background (`🔄(N bg)`), waiting for input (`⏳`), multiple-choice question (`❓`), plan awaiting approval (`📋`).
- **Reply routing** — swipe-reply to a notification to answer that exact session; plain messages go to the most recent one; `/sessions` and `/use` to switch targets.
- **Self-healing** — the hook forwarder starts the daemon if it is down; single-instance guard; everything fails silent so your sessions are never blocked.
- **Noise control** — per-session coalescing and dedupe, global rate cap, `IGNORE_CWD_SUBSTRINGS` to mute whole projects.
- **Dry-run mode** — without a bot token the daemon logs would-be messages to `logs/outbox.log`, so you can verify the pipeline before touching Telegram.

## Requirements

- Windows 10/11
- [Claude Code Desktop](https://claude.com/claude-code) (the bridge relays replies through the desktop app's session tools)
- A Telegram account
- Python 3.10+ **only to build** the two executables (not needed at runtime)

## Install

```powershell
git clone https://github.com/ozaneski13/cc-telegram-bridge.git
cd cc-telegram-bridge
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` is idempotent: it builds the executables if missing (via `build.ps1`), installs the plugin to `~/.claude/skills/cc-telegram-bridge` (auto-loads in new sessions as `cc-telegram-bridge@skills-dir`), records the app location in `home.txt`, creates a Startup shortcut, generates a `BRIDGE_SECRET` if absent, starts the daemon, and health-checks it.

## Activate Telegram

1. DM [@BotFather](https://t.me/BotFather), send `/newbot`, copy the token.
2. DM [@userinfobot](https://t.me/userinfobot) to get your numeric user id.
3. Put both into `.env` (`BOT_TOKEN=...`, `TELEGRAM_OWNER_ID=...`).
4. Restart the daemon (see table below).
5. Send your bot one DM — that binds the chat. Only messages from `TELEGRAM_OWNER_ID` are accepted; everything else is silently dropped.
6. Replies work out of the box (live mode). The optional `/cc-telegram-bridge` relay session is only needed if you want **instant** delivery into sessions that have been idle for longer than the hold window — otherwise such messages are queued and injected automatically the next time that session wakes (you type in it, or it restarts).

## Daily driving

| You send | What happens |
|---|---|
| swipe-reply to a notification | Your text lands in that notification's session as a user message |
| plain message | Goes to the most recently notified session |
| `/sessions` | Numbered list of recent sessions (`*` = current target) |
| `/use 2` or `/use a1b2` | Switch the current target |

Delivery confirmations: `⚡ →` injected live (session was holding or mid-turn); `→ ... (session idle ...)` queued — delivered when that session next wakes, or instantly if the optional bridge session is running.

## Operating the daemon

| Action | Command |
|---|---|
| Status | `curl.exe http://127.0.0.1:8765/health` → `ok` |
| Stop | `curl.exe -X POST http://127.0.0.1:8765/shutdown -H "X-Bridge-Token: <BRIDGE_SECRET>"` |
| Start | run `cc-telegram-bridge.exe` (or just use Claude — the hook auto-starts it) |
| Rebuild | `powershell -ExecutionPolicy Bypass -File build.ps1` |

## Configuration (`.env`)

See [.env.example](.env.example). `BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `BRIDGE_SECRET`, `PORT`, `IGNORE_CWD_SUBSTRINGS`. The daemon reads `.env` at startup — restart after changes. **Never commit `.env`** (it is gitignored).

## Moving to another PC (same Claude account)

1. **On the old PC:** stop the daemon (`taskkill /IM cc-telegram-bridge.exe /F`) and delete `shell:startup\cc-telegram-bridge.lnk`. Two machines polling one bot token conflict (Telegram 409) and produce duplicate notifications.
2. Copy the folder (or `git clone` and copy your `.env` across; copying `state.json` too preserves the chat binding).
3. Run `setup.ps1` on the new PC. Done — the install is location- and username-independent.

## Security & privacy

- The daemon binds **127.0.0.1 only**; hook requests are authenticated with an `X-Bridge-Token` shared secret.
- Only your numeric Telegram id is accepted; there is no pairing surface for strangers.
- Your bot token lives only in your local `.env`.
- **Conversation excerpts transit Telegram's servers.** If a project is sensitive, add its folder name to `IGNORE_CWD_SUBSTRINGS`.
- Executables are not shipped in the repo; you build them locally from the sources you can read (`daemon.py`, `plugin/hooks/notify_event.py` — stdlib only, no dependencies).

## Limitations

- Interactive UI prompts (question buttons, plan-approval dialogs, permission dialogs) cannot be remotely "clicked". Your Telegram text is delivered as a queued user message; exact behavior against a pending dialog is still being validated. Inline-keyboard answering is on the roadmap behind a feasibility spike.
- The reply relay requires the desktop app (an open bridge session); notifications alone work with any Claude Code flavor that runs hooks.
- Windows-only as shipped (paths, Startup shortcut, PowerShell scripts). The daemon itself is portable Python.

## Official alternatives

- [`telegram@claude-plugins-official`](https://github.com/anthropics/claude-plugins-official) (channels): binds **one dedicated CLI session** to Telegram — a phone-first assistant rather than a monitor for your existing sessions.
- Remote Control + the Claude mobile app: Anthropic's official remote monitoring/approval surface, not Telegram-based.

## License

[MIT](LICENSE) — © 2026 Ozan Eşki.

Türkçe dokümantasyon için: [README.tr.md](README.tr.md)
