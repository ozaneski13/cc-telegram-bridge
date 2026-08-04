## What this changes

<!-- One or two sentences. Link the issue if there is one. -->

## How it was tested

<!-- There is no automated suite; say what you actually exercised, e.g. a notification with the grace period, a reply reaching the right session, the daemon killed mid-session. -->

## Checklist

- [ ] Standard library only — no new runtime dependency
- [ ] Hooks still fail silent and exit 0 when the daemon is unreachable
- [ ] No new outbound destination, or the README security section is updated in this PR
- [ ] No new file write target, or it is validated and documented
- [ ] README (and README.tr.md) updated if behaviour changed
- [ ] No real tokens, secrets, chat ids, or personal paths in the diff
