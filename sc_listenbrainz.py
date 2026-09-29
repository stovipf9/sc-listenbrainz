# /// script
# requires-python = ">=3.10"
# dependencies = ["soundcloud-v2>=1.6", "requests"]
# ///
"""Submit SoundCloud play history to ListenBrainz.

Stateless: listens already on ListenBrainz (music_service == soundcloud.com)
are matched by listened_at, and only the missing ones are submitted. Running
it twice gives the same result.

Environment:
    SOUNDCLOUD_OAUTH_TOKEN  the "oauth_token" cookie of soundcloud.com
    LISTENBRAINZ_TOKEN      user token from https://listenbrainz.org/settings/
"""

import os
import sys
import time

import requests
from soundcloud import SoundCloud

LB = "https://api.listenbrainz.org/1"
SC_HISTORY_DEPTH = 300  # history items read from SoundCloud
LB_LOOKBACK = 100  # listens read from ListenBrainz for matching
LB_GET_TIMEOUT = 60  # seconds; responses measured from 1.5 to over 40
LB_GET_ATTEMPTS = 3
CLIENT = "sc-listenbrainz"
MUSIC_SERVICE = "soundcloud.com"


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"{name} is not set")
    return v


# --- pure ---


def is_a_scrobble(duration_ms: int, played_for_ms: int) -> bool:
    # https://www.last.fm/api/scrobbling#when-is-a-scrobble-a-scrobble
    if duration_ms <= 30_000:
        return False
    return played_for_ms * 2 >= duration_ms or played_for_ms >= 4 * 60_000


def to_listen(item) -> dict:
    t = item.track
    return {
        "listened_at": item.played_at // 1000,
        "track_metadata": {
            "artist_name": t.user.username,
            "track_name": t.title,
            "additional_info": {
                "music_service": MUSIC_SERVICE,
                "origin_url": t.permalink_url,
                "duration_ms": t.duration,
                "submission_client": CLIENT,
            },
        },
    }


def already_submitted(lb_listens: list[dict], lookback: int) -> tuple[set[int], int | None]:
    """listened_at of listens that came from SoundCloud, and the floor of the window.

    Plays older than the floor fall outside what was read, so whether they
    were submitted is unknown and they must not be sent. The floor is None
    when the window was not full (everything is visible).
    """
    seen = {
        l["listened_at"]
        for l in lb_listens
        if l["track_metadata"].get("additional_info", {}).get("music_service")
        == MUSIC_SERVICE
    }
    floor = min(l["listened_at"] for l in lb_listens) if len(lb_listens) >= lookback else None
    return seen, floor


def plan(history: list, seen: set[int], floor: int | None, now_ms: int) -> tuple[dict | None, list[dict]]:
    """Decide what to submit. Returns (playing_now or None, listens).

    history is newest first. The newest item cannot be judged until the next
    play arrives; it only yields playing_now while its duration has not elapsed.
    """
    if not history:
        return None, []
    history = sorted(history, key=lambda i: i.played_at, reverse=True)

    playing_now = None
    newest = history[0]
    if now_ms - newest.played_at < newest.track.duration:
        playing_now = to_listen(newest)
        del playing_now["listened_at"]

    listens = []
    for item, next_item in zip(history[1:], history[:-1]):
        listened_at = item.played_at // 1000
        if listened_at in seen:
            continue
        if floor is not None and listened_at < floor:
            continue
        if is_a_scrobble(item.track.duration, next_item.played_at - item.played_at):
            listens.append(to_listen(item))
    return playing_now, listens


# --- I/O ---


def lb_headers(token: str) -> dict:
    return {"Authorization": f"Token {token}"}


def lb_get(path: str, token: str, **params) -> requests.Response:
    """GET from ListenBrainz, retrying on timeouts and dropped connections."""
    for attempt in range(1, LB_GET_ATTEMPTS + 1):
        try:
            r = requests.get(f"{LB}{path}", params=params, headers=lb_headers(token), timeout=LB_GET_TIMEOUT)
            r.raise_for_status()
            return r
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt == LB_GET_ATTEMPTS:
                raise
            print(f"ListenBrainz {path}: {e.__class__.__name__}, retrying ({attempt}/{LB_GET_ATTEMPTS})")
            time.sleep(5 * attempt)


def lb_username(token: str) -> str:
    r = lb_get("/validate-token", token)
    body = r.json()
    if not body.get("valid"):
        sys.exit("LISTENBRAINZ_TOKEN is invalid")
    return body["user_name"]


def lb_listens(token: str, user: str) -> list[dict]:
    return lb_get(f"/user/{user}/listens", token, count=LB_LOOKBACK).json()["payload"]["listens"]


def submit(token: str, listen_type: str, payload: list[dict]) -> None:
    r = requests.post(
        f"{LB}/submit-listens",
        json={"listen_type": listen_type, "payload": payload},
        headers=lb_headers(token),
        timeout=30,
    )
    r.raise_for_status()


def sc_history(token: str) -> list:
    sc = SoundCloud(auth_token=token)
    if not sc.is_auth_token_valid():
        sys.exit("SOUNDCLOUD_OAUTH_TOKEN is invalid (it changes on logout/login)")
    history = []
    for item in sc.get_my_history():
        history.append(item)
        if len(history) >= SC_HISTORY_DEPTH:
            break
    return history


def main() -> None:
    sc_token = env("SOUNDCLOUD_OAUTH_TOKEN")
    lb_token = env("LISTENBRAINZ_TOKEN")

    history = sc_history(sc_token)
    user = lb_username(lb_token)
    seen, floor = already_submitted(lb_listens(lb_token, user), LB_LOOKBACK)
    playing_now, listens = plan(history, seen, floor, int(time.time() * 1000))

    if floor is not None:
        below = sum(1 for i in history if i.played_at // 1000 < floor)
        if below:
            print(f"{below} plays are older than the {LB_LOOKBACK} listens read from ListenBrainz; not judged")
    if playing_now:
        submit(lb_token, "playing_now", [playing_now])
        m = playing_now["track_metadata"]
        print(f"playing_now: {m['artist_name']} - {m['track_name']}")
    if not listens:
        print("nothing new")
        return
    submit(lb_token, "import" if len(listens) > 1 else "single", listens)
    for l in listens:
        m = l["track_metadata"]
        print(f"submitted: {m['artist_name']} - {m['track_name']} @ {l['listened_at']}")


if __name__ == "__main__":
    main()
