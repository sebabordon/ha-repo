"""Free, unauthenticated iTunes Search API — used only to find a
music.apple.com deep link for a track so it can be opened in Music.app for
manual review/add. Not the (paid, developer-account-gated) MusicKit API.
"""
import json
import os
import urllib.parse
import urllib.request

STOREFRONT = os.environ.get("APPLE_MUSIC_STOREFRONT", "ar")


def search(name: str, artist: str, limit: int = 5):
    query = urllib.parse.urlencode({
        "term": f"{name} {artist}",
        "media": "music",
        "entity": "song",
        "limit": limit,
        "country": STOREFRONT,
    })
    url = f"https://itunes.apple.com/search?{query}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.load(resp)
    return [
        {"name": r["trackName"], "artist": r["artistName"], "url": r["trackViewUrl"]}
        for r in data.get("results", [])
    ]
