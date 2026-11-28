"""Settings, read once from environment variables (see .env.example).

Every setting has a LOMBO_GATE_ prefix so it never collides with another container's variables.
A bad value stops the app at start-up with a message that names the variable.
"""

import math
from dataclasses import dataclass
from urllib.parse import urlparse

PREFIX = "LOMBO_GATE_"


class ConfigError(Exception):
    """A setting is missing or invalid. The message says which one and what to do."""


@dataclass(frozen=True)
class Config:
    seerr_url: str
    seerr_api_key: str
    sonarr_url: str
    sonarr_api_key: str
    max_seasons: int
    max_gb: float
    quality: str
    mb_per_min: float
    webhook_url: str | None
    dry_run: bool
    interval_seconds: int
    state_file: str


def _truthy(value: str, name: str) -> bool:
    """Strict on/off: a typo such as DRY_RUN=treu is an error, never a silent 'off'."""
    word = value.strip().lower()
    if word in {"1", "true", "yes", "on"}:
        return True
    if word in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{PREFIX}{name} must be true or false (got {value!r})")


def from_env(env: dict[str, str]) -> Config:
    def get(name: str, default: str = "") -> str:
        return (env.get(PREFIX + name) or "").strip() or default

    def url(name: str) -> str:
        value = get(name).rstrip("/")
        if urlparse(value).scheme not in {"http", "https"} or not urlparse(value).netloc:
            raise ConfigError(f"{PREFIX}{name} must be a full URL such as http://host:1234 (got {value!r})")
        return value

    def key(name: str) -> str:
        value = get(name)
        if value in {"", "changeme"}:
            raise ConfigError(f"{PREFIX}{name} is not set. Copy it from that app's settings page.")
        return value

    def number(name: str, default: str, least: float) -> float:
        try:
            value = float(get(name, default))
        except ValueError:
            raise ConfigError(f"{PREFIX}{name} must be a number") from None
        if not math.isfinite(value) or value < least:
            raise ConfigError(f"{PREFIX}{name} must be at least {least:g}")
        return value

    webhook = get("WEBHOOK_URL") or None
    if webhook and urlparse(webhook).scheme not in {"http", "https"}:
        raise ConfigError(f"{PREFIX}WEBHOOK_URL must start with http:// or https:// (or be empty)")

    return Config(
        seerr_url=url("SEERR_URL"),
        seerr_api_key=key("SEERR_API_KEY"),
        sonarr_url=url("SONARR_URL"),
        sonarr_api_key=key("SONARR_API_KEY"),
        max_seasons=int(number("MAX_SEASONS", "5", 0)),
        max_gb=number("MAX_GB", "125", 0),
        quality=get("QUALITY", "WEBDL-1080p"),
        mb_per_min=number("MB_PER_MIN", "60", 1),
        webhook_url=webhook,
        # Safe by default: nothing is approved until the person sets DRY_RUN=false.
        dry_run=_truthy(get("DRY_RUN", "true"), "DRY_RUN"),
        interval_seconds=int(number("INTERVAL_SECONDS", "60", 10)),
        state_file=get("STATE_FILE", "/data/state.json"),
    )
