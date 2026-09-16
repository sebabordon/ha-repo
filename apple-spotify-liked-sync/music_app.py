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
    # NOTE: fetching one property at a time per track (e.g. `favorited of t`
    # inside a `repeat with t in tracks` loop) means one IPC round-trip to
    # Music.app per track per property — for an 8000+ track library that
    # blows well past any sane timeout (measured: >300s and still not done).
    # Fetching each property as a bulk list (`favorited of every track of
    # library playlist 1`) is a single round-trip and takes well under a
    # second regardless of library size. The repeat loop below only zips
    # those already-fetched lists together by index — no further calls into
    # Music.app — so it stays fast (a few seconds for 8000+ tracks).
    #
    # The love/heart property is called "favorited" on streaming (Apple
    # Music subscription) tracks and "loved" on local files — both exist in
    # the wild, so the bulk fetch tries "favorited" first and falls back to
    # "loved" if the library doesn't support it.
    script = '''
    tell application "Music"
        set idList to persistent ID of every track of library playlist 1
        set nameList to name of every track of library playlist 1
        set artistList to artist of every track of library playlist 1
        try
            set favList to favorited of every track of library playlist 1
        on error
            set favList to loved of every track of library playlist 1
        end try
    end tell

    set n to count of idList
    set outList to {}
    repeat with i from 1 to n
        set trackId to item i of idList
        set trackName to item i of nameList
        set trackArtist to item i of artistList
        if item i of favList then
            set trackLoved to "true"
        else
            set trackLoved to "false"
        end if
        set end of outList to trackId & tab & trackName & tab & trackArtist & tab & trackLoved
    end repeat

    set AppleScript's text item delimiters to linefeed
    set output to outList as text
    set AppleScript's text item delimiters to ""
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
