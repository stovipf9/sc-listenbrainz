# sc-listenbrainz

Submits your SoundCloud play history to [ListenBrainz](https://listenbrainz.org/).

SoundCloud keeps a server-side play history that includes plays from every
client (verified with the iOS app, which no scrobbler can observe). This
script reads that history through SoundCloud's internal API and submits it
to ListenBrainz.

## How it works

- Stateless. Listens already on ListenBrainz with `music_service = soundcloud.com`
  are matched by `listened_at`; only the missing ones are submitted. Running it
  twice gives the same result, so it can run from anywhere on any schedule.
- A play counts as a listen (`is_a_scrobble`) by the [Last.fm rule](https://www.last.fm/api/scrobbling#when-is-a-scrobble-a-scrobble):
  the gap to the next play is at least half the track length or 4 minutes,
  and the track is longer than 30 seconds. Pauses and seeks are not visible in
  the history, so this is an approximation.
- The newest play cannot be judged until the next one arrives. While its
  duration has not elapsed it is sent as `playing_now`.
- SoundCloud's history keeps only the latest play of each track (in 200
  history items, no track appeared twice). Two consequences: if you play the
  same track twice between two runs, the earlier play is lost; and if you skip
  a track and later replay the one that followed it, the gap after the skipped
  track grows and it counts as a listen. Running more often narrows both.
- `artist_name` is the uploader's username.

## Usage

Requires [uv](https://docs.astral.sh/uv/).

```
SOUNDCLOUD_OAUTH_TOKEN=...   # the "oauth_token" cookie of soundcloud.com (DevTools → Application → Cookies)
LISTENBRAINZ_TOKEN=...       # https://listenbrainz.org/settings/
uv run --script sc_listenbrainz.py
```

Or without cloning:

```
uv run --script https://raw.githubusercontent.com/stovipf9/sc-listenbrainz/main/sc_listenbrainz.py
```

Each run reads 300 plays from SoundCloud and matches them against the last 100
listens on ListenBrainz from any service. Plays older than that window are not
judged, and the script prints how many. So the window has to cover every
listen, from any service, since the previous successful run; daily runs stay
well inside it unless you listen to around 100 tracks a day. For the same
reason the first run imports only the plays newer than your 100th most recent
listen. To import more, raise `LB_LOOKBACK` (the API allows up to 1000) for
that one run. After that, run it as often as you like — daily is enough unless
you replay tracks a lot.

The `oauth_token` changes when you log out and back in; the script exits
with a message when it is invalid.

## Development

```
uv run pytest
```

The pure parts (`is_a_scrobble`, `plan`, `already_submitted`) are tested. The
I/O against the two services is not.

## Credits

The approach follows [7x11x13/sc-scrobbler](https://github.com/7x11x13/sc-scrobbler)
(Last.fm) and uses [soundcloud.py](https://github.com/7x11x13/soundcloud.py).
