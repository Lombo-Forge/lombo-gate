---
name: troubleshoot
description: Diagnose LomboGate problems from doctor output and logs. Use when the app fails to start, doctor shows FAIL, alerts do not arrive, or it does nothing.
---

# Troubleshoot LomboGate

Start with `lombo-gate doctor`. Each line says what failed.

| You see | It means | Fix |
|---|---|---|
| `[FAIL] settings: LOMBO_GATE_X ...` (exit 2) | A setting is missing or invalid. | Fix it in `.env`; restart. |
| `Seerr ...: HTTP 401` or `403` | Wrong API key. | Copy it again from Settings > General. |
| `... urlopen error` | The URL is not reachable from the container. | Use the service name or LAN address; check the shared network. |
| `HTTP 301` or `302` | The URL redirects (http to https, or a base path). | Use the final address. |
| `Sonarr has no quality called` | `LOMBO_GATE_QUALITY` matches no quality. | Use a name from Sonarr, Settings > Quality. |
| Estimates look far off | Sonarr sets no size for that quality. | Set `LOMBO_GATE_MB_PER_MIN` to what your downloads really are. |
| Big requests download anyway | That user has auto-approve. | `doctor` names them; turn it off in Seerr. |
| Nothing is approved | Dry run is on. | `plan`, then `LOMBO_GATE_DRY_RUN=false`. |
| `[FAIL] state: cannot write` | No writable volume. | Mount one at `/data`. |

Logs: `docker compose logs --tail 100 lombo-gate`. In loop mode a failed round is logged and the next
one still runs, so look for `[FAIL]` lines. When you report a bug, include `doctor` output with the
key and webhook URL removed.
