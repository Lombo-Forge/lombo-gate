# How it is built

## Contents

- [The shape](#the-shape)
- [The rules](#the-rules)
- [Safe by default](#safe-by-default)
- [Not built](#not-built)

## The shape

```
Seerr, Sonarr  <--  api.py  -->  cli.py  -->  core.py (decides)
                                    |
                                    +-->  notify.py  -->  your webhook
                                    +-->  state.py   (which held requests you were told about)
```

`core.py` never touches the network, the disk or the clock.

## The rules

- A movie is approved. 4K and unknown kinds are left waiting without an alert.
- A TV request is held when it asks for more than `MAX_SEASONS` seasons **or** its estimate is over `MAX_GB`.
  Exactly at a limit passes.
- No season list means every season except specials.
- Estimate: episodes x runtime (40 minutes if unknown) x Sonarr's preferred MB per minute for `QUALITY`, capped by
  its maximum.
- A season Seerr does not list, or no episodes at all, means the size is unknown: held.
- If Seerr, Sonarr or one request cannot be read, that request is left waiting and tried again.

## Safe by default

- `DRY_RUN` is true until set to false. `plan` and dry run approve nothing, alert nothing and write nothing.
- The only change it can make is `POST /api/v1/request/{id}/approve`.
- Redirects are refused: urllib would turn the approving POST into a GET that "succeeds".
- A held request is remembered only after its alert was accepted, so a failed webhook is retried.
- Names in alerts cannot ping a chat (`@` is broken up).

## Not built

Content rules, pausing approvals when disks are low, size limits for movies.
