from types import SimpleNamespace

from sc_listenbrainz import already_submitted, is_a_scrobble, plan

MIN = 60_000


def item(played_at_ms, duration_ms=5 * MIN, title="t"):
    track = SimpleNamespace(
        duration=duration_ms,
        title=title,
        permalink_url="https://soundcloud.com/a/" + title,
        user=SimpleNamespace(username="a"),
    )
    return SimpleNamespace(played_at=played_at_ms, track=track)


def lb_listen(listened_at, service="soundcloud.com"):
    info = {"music_service": service} if service else {}
    return {"listened_at": listened_at, "track_metadata": {"additional_info": info}}


def test_is_a_scrobble_follows_lastfm_rules():
    assert not is_a_scrobble(30_000, 30_000)  # too short to count
    assert is_a_scrobble(5 * MIN, 150_000)  # half
    assert not is_a_scrobble(5 * MIN, 149_000)
    assert is_a_scrobble(20 * MIN, 4 * MIN)  # 4 minutes
    assert not is_a_scrobble(20 * MIN, 4 * MIN - 1)


def test_plan_judges_each_play_by_the_gap_to_the_next():
    history = [item(0, title="skipped"), item(MIN, title="heard"), item(6 * MIN, title="newest")]
    _, listens = plan(history, set(), None, now_ms=60 * MIN)
    assert [l["track_metadata"]["track_name"] for l in listens] == ["heard"]
    assert listens[0]["listened_at"] == MIN // 1000


def test_plan_accepts_history_in_any_order():
    history = [item(6 * MIN), item(0), item(MIN)]
    _, listens = plan(history, set(), None, now_ms=60 * MIN)
    assert [l["listened_at"] for l in listens] == [MIN // 1000]


def test_plan_skips_already_submitted():
    history = [item(MIN), item(6 * MIN)]
    _, listens = plan(history, {MIN // 1000}, None, now_ms=60 * MIN)
    assert listens == []


def test_plan_skips_plays_below_the_floor():
    history = [item(MIN), item(6 * MIN), item(11 * MIN)]
    _, listens = plan(history, set(), floor=6 * MIN // 1000, now_ms=60 * MIN)
    assert [l["listened_at"] for l in listens] == [6 * MIN // 1000]


def test_plan_reports_playing_now_only_while_the_newest_is_still_playing():
    history = [item(0), item(MIN, duration_ms=5 * MIN)]
    playing, _ = plan(history, set(), None, now_ms=2 * MIN)
    assert playing is not None and "listened_at" not in playing
    playing, _ = plan(history, set(), None, now_ms=7 * MIN)
    assert playing is None


def test_plan_with_empty_history():
    assert plan([], set(), None, now_ms=0) == (None, [])


def test_listen_shape():
    _, [l] = plan([item(MIN, title="x"), item(6 * MIN)], set(), None, now_ms=60 * MIN)
    info = l["track_metadata"]["additional_info"]
    assert l["track_metadata"]["artist_name"] == "a"
    assert info["music_service"] == "soundcloud.com"
    assert info["origin_url"].endswith("/x")
    assert info["duration_ms"] == 5 * MIN


def test_already_submitted_matches_only_soundcloud_listens():
    seen, floor = already_submitted([lb_listen(10), lb_listen(20, service=None), lb_listen(30, "spotify.com")], lookback=100)
    assert seen == {10}
    assert floor is None


def test_already_submitted_floor_when_window_is_full():
    seen, floor = already_submitted([lb_listen(50), lb_listen(10)], lookback=2)
    assert floor == 10
