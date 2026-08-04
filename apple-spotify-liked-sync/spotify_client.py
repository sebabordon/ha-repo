"""Thin wrapper around the Spotify Web API for Liked Songs."""
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth

CONFIG_DIR = os.path.expanduser("~/.apple_spotify_sync")
TOKEN_PATH = os.path.join(CONFIG_DIR, "spotify_token.json")
SCOPE = "user-library-read user-library-modify"


def get_client() -> spotipy.Spotify:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8899/callback")
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
        cache_path=TOKEN_PATH,
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def get_liked_tracks(sp: spotipy.Spotify):
    """Return every Liked Song. Each item: {"id", "name", "artist"}"""
    tracks = []
    limit = 50
    offset = 0
    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        items = results.get("items", [])
        if not items:
            break
        for item in items:
            t = item.get("track")
            if t:
                tracks.append({
                    "id": t["id"],
                    "name": t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                })
        offset += limit
        if len(items) < limit:
            break
    return tracks


def save_track(sp: spotipy.Spotify, track_id: str):
    sp.current_user_saved_tracks_add([track_id])


def remove_track(sp: spotipy.Spotify, track_id: str):
    sp.current_user_saved_tracks_delete([track_id])


def search_candidates(sp: spotipy.Spotify, name: str, artist: str, limit: int = 5):
    """Catalog search. Returns a list of {"id", "name", "artist"}."""
    query = f"track:{name} artist:{artist}"
    results = sp.search(q=query, type="track", limit=limit)
    items = results.get("tracks", {}).get("items", [])
    return [
        {"id": t["id"], "name": t["name"], "artist": ", ".join(a["name"] for a in t["artists"])}
        for t in items
    ]


def search_track(sp: spotipy.Spotify, name: str, artist: str):
    """Best-effort catalog search. Returns {"id", "name", "artist"} or None."""
    candidates = search_candidates(sp, name, artist, limit=5)
    return candidates[0] if candidates else None
