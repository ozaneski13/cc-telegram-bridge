# Platform notes

What was actually measured about Claude Code and Claude Code Desktop while building this bridge, including the things that turned out to be impossible. Recorded so nobody — including future me — burns hours re-discovering them.

Measured on Claude Code 2.1.x with the Windows desktop app. Behaviour may change; each item says how it was verified so you can re-check.

## Hooks

**Hook config is re-read continuously; plugins are not.** A hook added to `settings.json` fired on the very next turn of a session that had been open for hours — no restart needed. A hook shipped inside a *plugin* is different: plugins load when a session starts, so chats opened before the install stay silent until the app is restarted. This asymmetry is the single most confusing thing during setup.

**`Stop` carries the assistant's own message.** The payload includes `last_assistant_message` with the full final text, plus `background_tasks`, `permission_mode`, `effort`, `cwd`, `transcript_path` and `session_id`. Reading the transcript file is only a fallback.

**`Stop` fires while background work is still running.** The main turn ends — and emits `Stop` — while spawned subagents or background shells are still going, with those listed in `background_tasks`. A notifier that says "finished" on every `Stop` will lie; check for `status: "running"` entries first. Subagent completions do *not* reach `Stop` (there is a separate `SubagentStop` event).

**`cwd` can change within one session.** Two `Stop` events from the same session reported different working directories after a `cd`. Use `session_id` as the identity and treat `cwd` as a label.

**`Stop` with `decision: "block"` continues the session.** Returning `{"decision": "block", "reason": "..."}` from a Stop hook makes the session keep going and treat the reason as new input. This is the mechanism behind live mode: the hook holds at turn end, waits for a remote reply, and injects it. Verified headlessly end to end.

**Hooks can inject context on `UserPromptSubmit` and `SessionStart`** via `hookSpecificOutput.additionalContext` — used here to deliver messages that arrived while a chat was asleep.

**Hook stdin is UTF-8, and Windows Python will not assume that.** `json.load(sys.stdin)` mangles non-ASCII text (cp125x decoding); read bytes instead: `json.loads(sys.stdin.buffer.read().decode("utf-8"))`. The failure is silent — the pipeline works and only the characters are wrong.

## Sessions and identity

**There are two id spaces.** Hooks report the CLI session id; the desktop app's own session tools expect their `local_...` id. The mapping lives in the app's session store, where each record has both (`cliSessionId` and `sessionId`). Passing a CLI id to the app's messaging tool returns "Session not found".

**A message delivered into another session is plain text, not input.** It arrives wrapped in a `<cross-session-message …>` envelope and never passes through the client's slash-command handling — so `/model`, `/clear` and friends cannot be triggered remotely this way. Verified by sending `/model opus` into a session: it appeared as a user turn, the model did not change.

**The app owns the active chat's stored state.** Writing `model` or `effort` into the session store works for a chat that is not in use, and is silently overwritten for the chat you are actively using: the app rewrites that record at the end of every turn. Measured directly — a value written at 17:11 was back to the app's own at 17:13.

**Conclusion for remote control:** changing model/effort remotely is possible for *new* chats (via settings) and for *closed* chats (via their stored state), and impossible for a running one. Anthropic's own Remote Control is the supported way to steer a live session from elsewhere.

## Testing constraints

**Headless sessions have a smaller tool set.** In `claude -p` runs the interactive question tool is absent — the model answers "I don't have access to an AskUserQuestion tool". Anything that depends on interactive tools cannot be validated headlessly; it needs a real session and a human.

**Use a real HTTP client for local POSTs in tests.** Git-Bash/MSYS mangles JSON arguments to `curl.exe` in ways that fail quietly; Python's `urllib` in a here-doc is reliable.

## Windows packaging

**Do not ship a PyInstaller one-file build of a tool like this.** Windows Defender's ML heuristics classified it as `Trojan:Win32/Bearfoos.A!ml` and quarantined the executable, its Startup shortcut and the running processes. Nothing was wrong with the code — the behaviour profile (self-installing single-file binary + socket + remote polling + process spawning) is what a remote-access tool looks like. Running the `.py` sources under the user's own signed interpreter removes the trigger entirely, and makes the executing code identical to the reviewable code. Adding an antivirus exclusion would have been the wrong fix.

**PowerShell 5.1 reads BOM-less UTF-8 scripts as ANSI.** A `.ps1` containing non-ASCII characters fails to parse, with mojibake visible in the error. Keep install scripts ASCII-only, or save them with a BOM.
