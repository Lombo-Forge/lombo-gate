"""Command line: doctor, plan, run. Talks to the outside world; core.py decides.

lombo-gate doctor        check the settings, Seerr and Sonarr; exit 1 on any failure
lombo-gate plan          show what would happen to each waiting request; changes nothing, ever
lombo-gate run [--loop]  do it (approves and alerts only when DRY_RUN=false); --loop repeats
"""

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__, api, core, notify, state
from .api import Api, ApiError
from .config import Config, ConfigError, from_env


def _apis(cfg: Config) -> tuple[Api, Api]:
    return Api("Seerr", cfg.seerr_url, cfg.seerr_api_key), Api("Sonarr", cfg.sonarr_url, cfg.sonarr_api_key)


def _rate(cfg: Config, sonarr: Api) -> float:
    rate = core.mb_per_min(sonarr.get("/api/v3/qualitydefinition"), cfg.quality)
    if rate is None:
        raise ApiError(f"Sonarr has no size for the quality {cfg.quality!r}; check LOMBO_GATE_QUALITY")
    return rate


def _decide(cfg: Config, seerr: Api, sonarr: Api, request: dict[str, Any]) -> tuple[core.Decision, str]:
    """(decision, title). The title is only looked up for TV; it is only used in alerts."""
    quick = core.screen(request)
    media = request.get("media") or {}
    if quick:
        return quick, f"TMDB {media.get('tmdbId')}"
    show = seerr.get(f"/api/v1/tv/{int(media['tmdbId'])}")
    decision = core.judge_tv(request, show, _rate(cfg, sonarr), cfg.max_seasons, cfg.max_gb)
    return decision, str(show.get("name") or f"TMDB {media['tmdbId']}")


def run_once(cfg: Config, change: bool) -> int:
    """One round. change=False (plan, or dry run) approves, alerts and writes nothing. Returns failures."""
    seerr, sonarr = _apis(cfg)
    waiting = api.pending_requests(seerr)
    if not waiting:
        print("No requests are waiting.")
    told = state.load(cfg.state_file)
    still_held = told & {r.get("id") for r in waiting}
    failures = 0
    for r in waiting:
        who = str((r.get("requestedBy") or {}).get("displayName") or "Someone")
        try:
            decision, title = _decide(cfg, seerr, sonarr, r)
            label = f"request {int(r['id'])} ({who}, {title}): {decision.reason}"
            if decision.action == "approve":
                if change:
                    seerr.post(f"/api/v1/request/{int(r['id'])}/approve")
                print(f"{'approved' if change else 'would approve'} {label}")
                continue
            print(f"{'left waiting' if decision.action == 'wait' else 'holding'} {label}")
            if decision.action == "hold" and change and cfg.webhook_url and r["id"] not in told:
                notify.send(cfg.webhook_url, core.alert_text(who, title, decision.reason))
                still_held.add(r["id"])
        except Exception as e:  # noqa: BLE001  one odd request must not stall the ones behind it
            failures += 1
            print(f"[FAIL] request {r.get('id')} left waiting: {type(e).__name__}: {e}", file=sys.stderr)
    if change and still_held != told:
        state.save(cfg.state_file, still_held)
    return failures


def doctor(cfg: Config) -> int:
    seerr, sonarr = _apis(cfg)
    ok = True

    def seerr_check() -> str:
        defaults = int(seerr.get("/api/v1/settings/main").get("defaultPermissions") or 0)
        if defaults & core.AUTO_APPROVE_BITS:
            print("[WARN] Seerr gives NEW users auto-approve: turn it off in Settings > Users")
        return "key accepted"

    def sonarr_check() -> str:
        return f"{cfg.quality} is {_rate(cfg, sonarr):g} MB per minute"

    def people_check() -> str:
        names = core.auto_approvers(api.users(seerr))
        if names:
            print(f"[WARN] auto-approve is on, so the limits never apply to: {', '.join(names)}")
        return f"{len(names)} user(s) bypass the gate"

    checks: list[tuple[str, Callable[[], str]]] = [
        ("Seerr", seerr_check),
        ("Sonarr", sonarr_check),
        ("auto-approve", people_check),
    ]
    for label, check in checks:
        try:
            print(f"[ ok ] {label}: {check()}")
        except ApiError as e:
            print(f"[FAIL] {label}: {e}")
            ok = False
    if not cfg.dry_run and not os.access(Path(cfg.state_file).parent, os.W_OK):
        print(f"[FAIL] state: cannot write next to {cfg.state_file}; mount a volume there")
        ok = False
    print(f"[ ok ] limits: {cfg.max_seasons} seasons, {cfg.max_gb:g} GB")
    print(f"[ ok ] webhook: {'set' if cfg.webhook_url else 'not set (alerts are skipped)'}")
    print(f"[ ok ] mode: {'dry run (nothing is approved)' if cfg.dry_run else 'LIVE'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lombo-gate", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("plan")
    run = sub.add_parser("run")
    run.add_argument("--loop", action="store_true")
    args = p.parse_args(argv)

    try:
        cfg = from_env(dict(os.environ) if env is None else env)
    except ConfigError as e:
        print(f"[FAIL] settings: {e}", file=sys.stderr)
        return 2

    if args.cmd == "doctor":
        return doctor(cfg)
    change = args.cmd == "run" and not cfg.dry_run
    loop = args.cmd == "run" and args.loop
    while True:
        try:
            failures = run_once(cfg, change)
        except Exception as e:  # noqa: BLE001  a loop survives one bad round, an odd reply included
            print(f"[FAIL] {e}", file=sys.stderr)
            failures = 1
        if not loop:
            return 1 if failures else 0
        time.sleep(cfg.interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
