import re
from pathlib import Path

import pytest

from conftest import tv
from lombo_gate import core, notify
from lombo_gate.api import Api, ApiError
from lombo_gate.cli import main
from lombo_gate.config import ConfigError, from_env

SHOW = {"seasons": [{"seasonNumber": n, "episodeCount": 22} for n in range(11)], "episodeRunTime": [42]}
LIVE = {"LOMBO_GATE_DRY_RUN": "false"}
MOVIE = {"id": 9, "type": "movie", "media": {"mediaType": "movie", "tmdbId": 5}}


def judge(seasons, max_seasons=5, max_gb=125, show=SHOW):
    return core.judge_tv(tv(1, seasons), show, 60, max_seasons, max_gb)


def test_either_limit_holds_and_exactly_at_a_limit_passes():
    assert judge([1, 2]).action == "approve"  # about 108 GB
    assert judge([1], max_seasons=1).action == "approve"
    assert "6 seasons" in judge([1, 2, 3, 4, 5, 6], max_gb=10_000).reason
    big = judge([1, 2, 3])
    assert big.action == "hold"
    assert "GB" in big.reason
    assert "seasons" not in big.reason


def test_no_season_list_means_every_season_but_specials():
    assert "10 seasons" in judge([]).reason


def test_what_cannot_be_estimated_is_held():
    assert "unknown" in judge([99]).reason
    assert "unknown" in judge([1, 99]).reason
    assert "unknown" in judge([1], show={}).reason
    announced = {"seasons": [{"seasonNumber": 1, "episodeCount": 8}, {"seasonNumber": 2, "episodeCount": 0}]}
    assert judge([], show=announced).action == "approve"


def test_screen_leaves_4k_and_unknown_kinds_and_approves_movies():
    assert core.screen(MOVIE).action == "approve"
    assert core.screen({**MOVIE, "is4k": True}).action == "wait"
    assert core.screen({"id": 1, "type": "music"}).action == "wait"
    assert core.screen(tv(1, [1])) is None


def test_rate_takes_preferred_capped_by_maximum():
    def d(preferred, top):
        return [{"quality": {"name": "WEBDL-1080p"}, "preferredSize": preferred, "maxSize": top}]

    assert core.mb_per_min(d(60, 100), "webdl-1080p", 7) == 60
    assert core.mb_per_min(d(500, 100), "WEBDL-1080p", 7) == 100
    assert core.mb_per_min(d(None, 100), "WEBDL-1080p", 7) == 100
    assert core.mb_per_min(d(None, None), "WEBDL-1080p", 7) == 7  # Sonarr "unlimited"
    assert core.mb_per_min(d(60, 100), "Bluray-2160p", 7) is None


def test_auto_approvers_skips_admins_and_managers():
    users = [{"displayName": n, "permissions": p} for n, p in [("a", 130), ("b", 144), ("c", 512), ("d", 32)]]
    assert core.auto_approvers(users) == ["c"]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SEERR_URL", "seerr:5055"),
        ("SONARR_URL", ""),
        ("SEERR_API_KEY", "changeme"),
        ("SONARR_API_KEY", ""),
        ("WEBHOOK_URL", "ftp://x"),
        ("MAX_SEASONS", "-1"),
        ("MAX_GB", "lots"),
        ("MAX_GB", "nan"),
        ("INTERVAL_SECONDS", "5"),
        ("DRY_RUN", "treu"),
    ],
)
def test_config_rejects_bad_values_and_names_the_setting(env, name, value):
    with pytest.raises(ConfigError, match=f"LOMBO_GATE_{name}"):
        from_env({**env, f"LOMBO_GATE_{name}": value})


def test_config_defaults_are_safe(env):
    cfg = from_env(env)
    assert (cfg.dry_run, cfg.max_seasons, cfg.max_gb) == (True, 5, 125)


def test_env_example_lists_exactly_the_settings():
    root = Path(__file__).parent.parent
    listed = set(re.findall(r"^LOMBO_GATE_(\w+)=", (root / ".env.example").read_text(), re.M))
    read = set(re.findall(r'(?:get|url|key|number)\("([A-Z_]+)"', (root / "src/lombo_gate/config.py").read_text()))
    assert listed == read


def test_plan_and_dry_run_change_nothing(env, fake, capsys):
    fake.pending = [tv(1, [1]), tv(2, list(range(1, 9)))]
    assert main(["plan"], {**env, **LIVE}) == 0
    assert main(["run"], env) == 0
    out = capsys.readouterr().out
    assert "would approve request 1" in out
    assert "holding request 2" in out
    assert fake.posts() == []
    assert not Path(env["LOMBO_GATE_STATE_FILE"]).exists()


def test_live_run_approves_small_and_movies_and_tells_once_about_big(env, fake):
    fake.pending = [tv(1, [1]), tv(2, list(range(1, 9))), tv(3, [1], is4k=True), MOVIE]
    assert main(["run"], {**env, **LIVE}) == 0
    assert main(["run"], {**env, **LIVE}) == 0
    posts = fake.posts()
    assert sorted(p for p in posts if "approve" in p) == sorted(
        ["/api/v1/request/1/approve", "/api/v1/request/9/approve"] * 2
    )
    assert posts.count("/hook") == 1


def test_a_failed_alert_is_retried_and_names_cannot_ping_a_chat(env, fake):
    fake.pending = [tv(2, list(range(1, 9)), who="@everyone")]
    fake.hook_status = 500
    assert main(["run"], {**env, **LIVE}) == 1
    fake.hook_status = 204
    assert main(["run"], {**env, **LIVE}) == 0
    assert fake.posts() == ["/hook", "/hook"]
    assert "@everyone" not in fake.calls[-1]["body"]


def test_one_odd_request_does_not_stall_the_rest(env, fake, capsys):
    fake.pending = [{"id": 1, "type": "tv", "media": {"mediaType": "tv"}}, tv(2, [1])]
    assert main(["run"], {**env, **LIVE}) == 1
    assert fake.posts() == ["/api/v1/request/2/approve"]
    assert "request 1 left waiting" in capsys.readouterr().err


def test_unlimited_sizes_use_the_fallback(env, fake, capsys):
    fake.definitions = [{"quality": {"name": "WEBDL-1080p"}, "preferredSize": None, "maxSize": None}]
    fake.pending = [tv(1, [1])]
    assert main(["doctor"], env) == 0
    assert main(["plan"], env) == 0
    assert "would approve request 1" in capsys.readouterr().out


def test_a_wrong_quality_name_approves_no_tv(env, fake):
    fake.pending = [tv(1, [1])]
    assert main(["run"], {**env, **LIVE, "LOMBO_GATE_QUALITY": "WEBDL-1080"}) == 1
    assert fake.posts() == []


def test_a_redirect_is_an_error_not_a_silent_success(env, fake):
    fake.redirect = True
    fake.pending = [MOVIE]
    assert main(["run"], {**env, **LIVE}) == 1


def test_seerr_down_is_a_message(env, capsys):
    assert main(["run"], {**env, "LOMBO_GATE_SEERR_URL": "http://127.0.0.1:1"}) == 1
    assert "[FAIL] Seerr" in capsys.readouterr().err
    with pytest.raises(ApiError, match="HTTP 401"):
        Api("Seerr", env["LOMBO_GATE_SEERR_URL"], "wrong").get("/api/v1/settings/main")


def test_pagination_reads_every_pending_request(env, fake):
    fake.pending = [{**MOVIE, "id": i} for i in range(150)]
    assert main(["run"], {**env, **LIVE}) == 0
    assert len(fake.posts()) == 150


def test_doctor_passes_warns_and_fails(env, fake, capsys):
    assert main(["doctor"], env) == 0
    out = capsys.readouterr().out
    assert "[FAIL]" not in out
    assert "[WARN]" not in out
    fake.users.append({"id": 2, "displayName": "Eager", "permissions": 160})
    fake.default_permissions = 160
    assert main(["doctor"], env) == 0
    out = capsys.readouterr().out
    assert "Eager" in out
    assert "NEW users" in out
    assert main(["doctor"], {**env, "LOMBO_GATE_SONARR_API_KEY": "wrong"}) == 1
    assert main(["doctor"], {**env, **LIVE, "LOMBO_GATE_STATE_FILE": "/nonexistent/state.json"}) == 1


def test_bad_settings_exit_2(capsys):
    assert main(["plan"], {}) == 2
    assert "LOMBO_GATE_SEERR_URL" in capsys.readouterr().err


def test_notify_posts_json(fake):
    notify.send(fake.url + "/hook", "hello")
    assert '"content": "hello"' in fake.calls[-1]["body"]
    with pytest.raises(notify.NotifyError):
        notify.send("http://127.0.0.1:1/hook", "x", timeout=1)
