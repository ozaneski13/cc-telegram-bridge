# Security Policy

This is a single-maintainer hobby project. Reports are handled on a best-effort basis, there is no bounty, and there are no guaranteed response times — but security reports are read first and taken seriously.

## Reporting a vulnerability

**For anything sensitive, use GitHub's private vulnerability reporting:** open the repository's **Security** tab → **Report a vulnerability**. That channel is private between you and the maintainer.

Please do not open a public issue for an unfixed vulnerability.

A useful report includes: what an attacker can do, the steps to reproduce it, and the affected file or command. Proof-of-concept code is welcome but not required.

For anything that is not a vulnerability — a bug, a question, an idea — a normal GitHub issue is the right place.

## Supported versions

Only the current `main` branch is supported. There are no maintained release branches; fixes land on `main` and are picked up the next time you `git pull` and re-run `setup.ps1`.

## Scope

**In scope** — the code in this repository:

- `daemon.py` — the local HTTP endpoint, Telegram polling, command handling, and the files it writes
- `plugin/hooks/notify_event.py` and `plugin/hooks/hooks.json` — the hook forwarder that runs inside your Claude Code sessions
- `setup.ps1` — installation, plugin generation, autostart

Examples of what is worth reporting: a way for someone other than the configured Telegram user to reach a session; command or path injection through a message; the shared secret or bot token leaking into a log, a repository file, or a network request; the settings writer corrupting or over-writing more than the documented keys.

**Out of scope** — things this project cannot defend:

- Telegram itself. Bot messages are not end-to-end encrypted and pass through Telegram's servers; this is a documented property of the design, not a bug.
- A compromised machine or user account. Any process running as you can read `.env`, so the local shared secret is a guard against accident, not against local malware.
- Claude Code and the Claude Code Desktop app themselves — report those to Anthropic.
- The consequences of your own replies. A message you send is delivered as a user message into a session running with your permissions; that is the purpose of the tool.

## Hardening advice

- Keep `.env` to yourself; it is gitignored, and its bot token is as sensitive as a password. Rotate it with `/revoke` in @BotFather if it is ever exposed, then update `.env` and restart the daemon.
- Add sensitive project folders to `IGNORE_CWD_SUBSTRINGS` so their sessions never notify.
- Lock the phone that holds your Telegram account — it can reach your sessions.
- Before trusting a build, read the source and compile it yourself; no executables are distributed here.
