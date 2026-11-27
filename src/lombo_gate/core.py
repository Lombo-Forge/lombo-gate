"""The decisions. Pure: no network, no disk, no clock, so tests need no fakes.

approve  within both limits (and every non-4K movie)
hold     over a limit, or the size cannot be estimated: left waiting, the admin is told once
wait     left waiting and nothing said (4K, or a kind this app does not know)
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_RUNTIME_MIN = 40  # when Seerr knows no episode length

# Seerr permission bits
ADMIN, MANAGE_REQUESTS = 2, 16
AUTO_APPROVE_BITS = 128 | 256 | 512  # all, movies, TV


@dataclass(frozen=True)
class Decision:
    action: str  # "approve", "hold" or "wait"
    reason: str


def kind(request: Mapping[str, Any]) -> str:
    return str((request.get("media") or {}).get("mediaType") or request.get("type") or "")


def screen(request: Mapping[str, Any]) -> Decision | None:
    """What can be decided without looking anything up. None means: a TV request, check its size."""
    if kind(request) not in {"movie", "tv"}:
        return Decision("wait", "unknown kind of request")
    if request.get("is4k"):
        return Decision("wait", "4K requests are the admin's to approve")
    if kind(request) == "movie":
        return Decision("approve", "movie")
    return None


def mb_per_min(definitions: Sequence[Mapping[str, Any]], quality: str, unlimited: float) -> float | None:
    """Sonarr's preferred MB per minute for one quality, capped by its maximum; `unlimited` when it sets neither.
    None when Sonarr has no quality of that name (a typo must not approve anything)."""
    for d in definitions:
        if str((d.get("quality") or {}).get("name", "")).lower() == quality.lower():
            preferred, top = d.get("preferredSize") or 0, d.get("maxSize") or 0
            if top:
                preferred = min(preferred, top) if preferred else top
            return float(preferred) if preferred else unlimited
    return None


def judge_tv(
    request: Mapping[str, Any], show: Mapping[str, Any], rate: float, max_seasons: int, max_gb: float
) -> Decision:
    """Season count and a rough size: episodes x runtime x MB per minute."""
    episodes = {s["seasonNumber"]: s.get("episodeCount") or 0 for s in show.get("seasons") or []}
    wanted = {s["seasonNumber"] for s in request.get("seasons") or []}
    if not wanted:  # no list means the whole show, without specials
        wanted = {n for n in episodes if n}
    total = sum(episodes.get(n, 0) for n in wanted)
    runtimes = [r for r in show.get("episodeRunTime") or [] if r]
    runtime = sum(runtimes) / len(runtimes) if runtimes else DEFAULT_RUNTIME_MIN
    gb = total * runtime * rate / 1024

    why = []
    if len(wanted) > max_seasons:
        why.append(f"{len(wanted)} seasons (limit {max_seasons})")
    if gb > max_gb:
        why.append(f"about {gb:,.0f} GB (limit {max_gb:,.0f})")
    # An announced season with no episodes yet counts as nothing, but a request we know nothing about does not pass.
    if not total or wanted - episodes.keys():
        why.append("size unknown: Seerr has no episode count")
    if why:
        return Decision("hold", " and ".join(why))
    return Decision("approve", f"{len(wanted)} season(s), about {gb:,.0f} GB")


def auto_approvers(users: Sequence[Mapping[str, Any]]) -> list[str]:
    """People whose requests Seerr approves before this app can see them. Admins and managers are meant to."""
    out = []
    for u in users:
        bits = int(u.get("permissions") or 0)
        if bits & AUTO_APPROVE_BITS and not bits & (ADMIN | MANAGE_REQUESTS):
            out.append(str(u.get("displayName") or u.get("id")))
    return out


def alert_text(who: str, title: str, reason: str) -> str:
    # Names come from users: a zero-width space stops "@everyone" from pinging a chat.
    return f"{who} asked for {title}: {reason}. It is waiting in Seerr.".replace("@", "@​")
