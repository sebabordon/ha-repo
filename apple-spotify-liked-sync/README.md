# Apple Music ↔ Spotify Liked Songs Sync (Mac-only)

Two-way sync between Spotify's **Liked Songs** and Apple Music's **Loved** tracks,
running locally on your Mac. No Apple Developer Program membership needed —
it drives Music.app directly via AppleScript instead of the MusicKit API.

## Known limitation

Music.app's AppleScript interface can only love/unlove tracks that are **already
in your local Apple Music library** — it has no command to search or add from
the streaming catalog (that part of the old iTunes scripting dictionary was
never carried over to Music.app). So:

- **Apple Music love → Spotify**: fully automatic (uses the real Spotify Web
  API to search the catalog and save the track).
- **Spotify like → Apple Music**: only applied if the song is already
  somewhere in your Apple Music library (loved or not). If it's missing
  entirely, it's printed as "unmatched" for you to add manually — after
  which the next run will love it.

Matching is by normalized title + primary artist (no ISRC — Music.app doesn't
expose it), so covers/live versions/remasters can occasionally mismatch. Check
the unmatched list after the first few runs.

A song can look present in the Apple Music *app* (searchable/streamable) while
still being absent from `library playlist 1`, the only thing AppleScript can
see — if it hasn't been explicitly added via "Add to Library", nothing here
can touch it. Add it in the app first, then re-run.

## Setup

### 1. macOS permissions

The first time `sync.py` runs, macOS will prompt to let your terminal (or
whatever runs `osascript`) control Music.app. Allow it in
**System Settings → Privacy & Security → Automation**.

### 2. Spotify app credentials

Reuse the same Spotify Developer app you already created for the
`spotify-tracker` add-on, or create a new one at
https://developer.spotify.com/dashboard. Either way, add this Redirect URI to
the app's settings:

```
http://127.0.0.1:8899/callback
```

### 3. Install and configure

```bash
cd apple-spotify-liked-sync
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET
```

### 4. First run (baseline)

```bash
source venv/bin/activate
set -a && source .env && set +a   # plain `source .env` does NOT export to python3
python3 sync.py
```

(Or just use `./run.sh`, which does the same `set -a` internally.)

The first run never applies changes — it just records the current state of
both libraries (and matches what already overlaps) so pre-existing
differences aren't blindly pushed in one direction. A browser window opens
once to authorize Spotify; the token is cached at
`~/.apple_spotify_sync/spotify_token.json`.

### 5. Sync for real

```bash
python3 sync.py            # applies changes
python3 sync.py --dry-run  # preview only, nothing is changed
```

From here on, only what changed *since the last run* is propagated in either
direction, including unlikes/unloves.

### 5b. One-time catch-up push (optional)

If your two libraries have already diverged a lot (e.g. you were only using
Spotify so far), `python3 sync.py` alone won't reconcile the backlog — it
only looks at *changes since last run*. Use `--push` once to favorite every
current Spotify like that's already in your Apple Music library, and get a
report (not auto-applied) of what's favorited on Apple Music but missing on
Spotify:

```bash
python3 sync.py --push --dry-run   # preview
python3 sync.py --push             # apply, saves result as the new baseline
```

Writes `not_in_apple_library.txt` and `missing_from_spotify.txt` in this
folder.

### 5c. Manually review near-misses (optional)

For tracks still unmatched after `--push`, `--review` shows the closest
fuzzy candidate and asks for a y/n confirmation before touching anything —
useful for title variants the matcher isn't confident enough to auto-accept
(default threshold is 87%, `--review` shows anything down to 75% for you to
judge). Rejections are remembered, so you won't be asked about the same pair
twice.

```bash
python3 sync.py --review
python3 sync.py --review --min-score 0.6   # show weaker candidates too
```

### 6. Automate it (optional)

Runs only while the Mac is awake — there's no way around that without a
server-side Apple Music integration (MusicKit).

```bash
cp com.sebastian.applespotifysync.plist.template com.sebastian.applespotifysync.plist
# edit it: replace REPLACE_WITH_ABSOLUTE_PATH with the absolute path to this folder
chmod +x run.sh
cp com.sebastian.applespotifysync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.sebastian.applespotifysync.plist
```

Runs every 30 minutes by default (`StartInterval`, in seconds — edit the
plist to change it). Logs go to `sync.log` in this folder.

To stop: `launchctl unload ~/Library/LaunchAgents/com.sebastian.applespotifysync.plist`

## Files

| File | Purpose |
|------|---------|
| `sync.py` | Main entrypoint — fetches both libraries, diffs against last run, applies changes |
| `music_app.py` | AppleScript bridge to Music.app (read library, set loved) |
| `spotify_client.py` | Spotify Web API wrapper (spotipy) |
| `matcher.py` | Title/artist normalization + fuzzy matching |
| `state.py` | Reads/writes `~/.apple_spotify_sync/state.json` (last-seen sets + track pairings) |
