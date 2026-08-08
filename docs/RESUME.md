# Resume here

State of the project as of 2026-08-08, written so it can be picked up on a fresh machine with nothing but this repository.

## Getting it running again

1. Install Python 3.10+ (tick "Add to PATH") and Claude Code Desktop; sign in.
2. `git clone` this repository.
3. Create `.env` from `.env.example`. You need two values:
   - `BOT_TOKEN` — if you already have a bot, @BotFather → `/mybots` → your bot → **API Token** shows it again. Otherwise `/newbot`.
   - `TELEGRAM_OWNER_ID` — @userinfobot tells you your numeric id.
   - `BRIDGE_SECRET` is generated for you by `setup.ps1` if left empty.
4. `powershell -ExecutionPolicy Bypass -File setup.ps1`
5. Restart the Claude Code Desktop app once, then DM your bot.

Verify: ask something in any chat, don't touch the app, and the answer should reach Telegram after the grace period. Reply to it and the session should continue.

## What is done and verified

- Notifications for every session: answer finished, still working (`🔄`), waiting for input, question, plan approval. Grace period with local-typing cancellation.
- Live mode: replies injected through the Stop-hook `decision: block` mechanism, no relay session needed. Verified end to end.
- Cold queue: messages to sleeping chats are injected on their next wake via `additionalContext`.
- Multiple-choice questions as inline buttons, with multi-select and free-text; only while you are on the phone, never blocking at the PC. The Telegram half is verified live (tap → answer captured, message edited).
- `/usage`, `/status`, `/model`, `/effort`, `/fast`, `/sessions`, `/use`, `/help`.
- Runs from source under the user's Python — no packed binary (see the Defender note in `platform-notes.md`).

## Open items

1. **Does a tapped button actually close the question in the app?** The daemon captures the answer correctly, but the last link — the hook returning `updatedInput.answers` and the question never appearing in the app — was never observed, because headless sessions have no question tool. Test: message the bot (to enter live mode), then in a scratch chat ask Claude to pose a two-option question and tap a button. If the question still opens in the app, set `ASK_ANSWER_MODE=deny` in `.env` and restart the daemon.
2. **Does a per-chat `/model` apply when that chat is reopened?** The value is written to the chat's stored state and survives (measured), but the app reading it on open was not observed. Test on a chat that is closed; if it does not apply, drop the per-chat path and keep only `global`.
3. **`Notification` payload shape** — the daemon handles it, but a real idle/permission notification was never captured, only a synthetic one.
4. Plan approval (`ExitPlanMode`) is notify-only; approving remotely is not possible (a hook cannot leave plan mode).

## If you extend it

Read `platform-notes.md` first. It records what was measured — including three separate ways of changing a running chat's model, all of which failed, and why. Re-testing them is wasted time.

## Shape of the code

- `daemon.py` — one file: hook endpoint, Telegram long-poll, notification queue with grace/dedupe, live-mode hold, question flow, settings commands. State in `state.json`, queue in `inbox.jsonl`.
- `plugin/` — the Claude Code plugin: `hooks.json.template` (interpreter path filled in at install), `hooks/notify_event.py` (forwarder + the waiting logic), `SKILL.md` (the optional relay-session protocol).
- `setup.ps1` — the only installer: writes the plugin, the autostart shortcut, and starts the daemon.
