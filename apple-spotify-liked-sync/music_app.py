"""AppleScript bridge to Music.app — read/write the local library's Loved status."""
import subprocess

FIELD_SEP = "\t"
ROW_SEP = "\n"


class MusicAppError(RuntimeError):
    pass


def _run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise MusicAppError(result.stderr.strip() or "osascript failed")
    return result.stdout


def get_library_tracks():
    """Return every track in the local Music.app library.

    Each item: {"id": persistent ID, "name": str, "artist": str, "loved": bool}
    """
    # NOTE: string-building with "&" must happen *outside* `tell application
    # "Music"` — concatenating a boolean while still inside the tell block
    # routes the "&" operation to Music.app itself and it errors out with
    # -10001 ("descriptor type mismatch"). So we collect raw values first,
    # then build the tab-separated output after leaving the tell block.
    #
    # The love/heart property is called "favorited" on streaming (Apple
    # Music subscription) tracks and "loved" on local files — both exist in
    # the wild, so each track tries "favorited" first and falls back to
    # "loved".
    script = '''
    tell application "Music"
        set trackList to {}
        repeat with t in (every track of library playlist 1)
            set isFav to false
            try
                set isFav to favorited of t
            on error
                try
                    set isFav to loved of t
                end try
            end try
            set end of trackList to {persistent ID of t, name of t, artist of t, isFav}
        end repeat
    end tell

    set output to ""
    repeat with rec in trackList
        set trackId to item 1 of rec
        set trackName to item 2 of rec
        set trackArtist to item 3 of rec
        if item 4 of rec then
            set trackLoved to "true"
        else
            set trackLoved to "false"
        end if
        set output to output & trackId & tab & trackName & tab & trackArtist & tab & trackLoved & linefeed
    end repeat
    return output
    '''
    raw = _run_applescript(script)
    tracks = []
    for row in raw.split(ROW_SEP):
        row = row.strip()
        if not row:
            continue
        parts = row.split(FIELD_SEP)
        if len(parts) != 4:
            continue
        track_id, name, artist, loved = parts
        tracks.append({
            "id": track_id,
            "name": name,
            "artist": artist,
            "loved": loved.strip().lower() == "true",
        })
    return tracks


def open_location(url: str):
    """Open a music.apple.com URL in Music.app (navigates/plays it — does not
    add it to the library; that step is up to whoever's watching the screen).
    """
    escaped = url.replace("\\", "\\\\").replace('"', '\\"')
    _run_applescript(f'tell application "Music" to open location "{escaped}"')


def set_loved(persistent_id: str, loved: bool):
    flag = "true" if loved else "false"
    script = f'''
    tell application "Music"
        set targetTrack to (first track of library playlist 1 whose persistent ID is "{persistent_id}")
        try
            set favorited of targetTrack to {flag}
        on error
            set loved of targetTrack to {flag}
        end try
    end tell
    '''
    _run_applescript(script)
