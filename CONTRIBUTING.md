# Contributing

Thanks for looking. This is a small, single-maintainer project — issues and pull requests are welcome, and reviews are best-effort rather than fast.

## Before a big change

Open an issue first if the change is substantial. Some constraints below are load-bearing, and a quick conversation is cheaper than a rewritten pull request.

## Project constraints

These are deliberate, and a change that breaks one will be sent back:

- **Standard library only.** No PyPI dependencies at runtime — this is what makes the tool auditable in a minute. PyInstaller is a build-time tool and stays out of the runtime path.
- **Hooks must fail silent and fast.** `plugin/hooks/notify_event.py` runs inside every Claude Code session. If the daemon is down, unreachable, or wrong, the hook must swallow the error and exit 0. A hook that raises, hangs, or prints stray output breaks the user's session — the one thing this project must never do.
- **No executables in the repository.** Users build them locally; that is a security property, not an oversight.
- **No new outbound destinations** beyond `127.0.0.1`, the Telegram bot API, and Anthropic's usage endpoint, unless the pull request explains why and the README's security section is updated in the same change.
- **Writes stay bounded.** The daemon writes its own folder, the model/effort fields of a named chat's saved state, and three documented keys in `~/.claude/settings.json`. New write targets need to be documented and validated the same way.

## Build and run

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1   # compile both executables
powershell -ExecutionPolicy Bypass -File setup.ps1   # install plugin, autostart, start daemon
```

For a faster loop, run the daemon straight from source instead of rebuilding: stop the executable, then `python daemon.py` in the project folder.

## Testing

There is no automated suite; the surfaces that matter are integration-shaped. Please state in the pull request what you exercised, ideally:

- a notification arriving with the grace period applied, and being cancelled by local typing
- a reply from Telegram reaching the correct session (live mode and the queued path)
- if you touched the question flow: buttons, multi-select, free text, and expiry
- the daemon being killed mid-session — sessions must be unaffected

`spike/SPIKES.md` records what has already been measured about the desktop app's behaviour, including several things that do *not* work. Read it before assuming a new approach is possible.

## Style

Match what is there: plain functions, no classes without a reason, no comments explaining what the code already says, and no abstraction until there is a second caller. User-visible strings in the bot and the README are in English.

## Commits and pull requests

Conventional commits in English (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`). Keep a pull request to one concern, and update the README in the same change when behaviour changes — documentation drift is the failure mode this project is most exposed to.

## Security

Do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md).
