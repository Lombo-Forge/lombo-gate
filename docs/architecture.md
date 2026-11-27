# How it is built

## Contents

- [What it will do](#what-it-will-do)
- [The shape](#the-shape)
- [Why it is split this way](#why-it-is-split-this-way)
- [Safe by default](#safe-by-default)
- [Settings](#settings)
- [Alerts](#alerts)
- [Adding a Jellyfin call](#adding-a-jellyfin-call)

## What it will do

Planned, not built.

Every round it reads the requests that are waiting in Seerr and decides, for each one, to approve it or to leave it
waiting for the admin.

- A TV request for more than a set number of seasons, or with an estimated size over a set limit, is held.
- The size is a rough estimate: episodes x runtime x the preferred size per minute that Sonarr holds for the quality.
- Everything else is approved. 4K requests are left waiting. Movies are not size-checked.
- Both limits apply: more than the season limit **or** over the size limit holds the request.
- A request that cannot be checked stays waiting. If the app is down, nothing is approved.
- It only works for people who do **not** have Seerr's auto-approve permission; `doctor` will say who still has it.
- Out of scope at first: content rules and pausing approvals when disks are low.

| Planned setting | Meaning |
|---|---|
| `LOMBO_GATE_SEERR_URL`, `LOMBO_GATE_SEERR_API_KEY` | Where the requests are |
| `LOMBO_GATE_SONARR_URL`, `LOMBO_GATE_SONARR_API_KEY` | Quality sizes for the estimate |
| `LOMBO_GATE_MAX_SEASONS`, `LOMBO_GATE_MAX_GB` | Above either one, the request waits |

The template's Jellyfin client is a placeholder here: the app may not need Jellyfin at all.

## The shape

```
Jellyfin  <--  jellyfin.py  -->  cli.py  -->  core.py (decides)
                                    |
                                    +-->  notify.py  -->  your webhook
```

`cli.py` fetches data, hands it to `core.decide()`, then acts on the answer. `core.py` never
touches the network, the disk or the clock.

## Why it is split this way

Rules are the part that changes most and breaks most quietly. Because `decide()` takes plain data
and returns plain data, a test is two lines and needs no server. The I/O layers are thin and are
tested once, against a fake Jellyfin on localhost (`tests/conftest.py`).

## Safe by default

- `DRY_RUN` is true until the person sets it to false.
- `plan` never changes anything and never alerts.
- `doctor` separates "Jellyfin is unreachable" from "the key was refused", so the fix is obvious.
- A bad setting stops the app at start-up and names the variable.
- In `--loop` mode one failed round is printed and the next one still runs.

## Settings

Every setting is an environment variable with the `LOMBO_GATE_` prefix, validated in `config.py`.
To add one: read it in `config.py` with a clear error, add a line to `.env.example`, and add a test.

## Alerts

`notify.send(url, message)` posts JSON with the text under `content` and `text`, which Discord,
Slack and many bridges accept. Nothing is hard-coded to a service. If you want ntfy, Gotify or
email, run an Apprise-style bridge and point the webhook at it.

## Adding a Jellyfin call

Add a method to `Jellyfin` in `jellyfin.py` that calls `self._get(path)`, add the path to the
fake in `tests/conftest.py`, and test it. The Jellyfin API reference for your server version is at
`https://your-server/api-docs/swagger`. Check a new call against a throwaway Jellyfin before
relying on it.
