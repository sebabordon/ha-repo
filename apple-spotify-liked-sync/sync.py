#!/usr/bin/env python3
"""Two-way sync of Liked Songs (Spotify) <-> Loved tracks (Apple Music, local library).

First run only records a baseline (no changes applied) so pre-existing
differences between the two libraries aren't blindly pushed to either side.
From the second run on, only what changed *since the last run* is propagated.

Known limitation: a Spotify like for a song that isn't already in your local
Apple Music library can't be auto-added (Music.app's AppleScript interface
can't search/add from the streaming catalog) — it's logged for manual review
instead. The reverse direction (Apple Music love -> Spotify) is fully
automatic since it uses the real Spotify Web API.
"""
import argparse
import html
import os
import subprocess
import sys
import time
import urllib.parse

from spotipy.exceptions import SpotifyException

import apple_catalog
import matcher
import music_app
import spotify_client
import state

RATE_LIMIT_PATH = os.path.join(state.CONFIG_DIR, "rate_limit_until")
RATE_LIMIT_BACKOFF = 3600
UNMATCHED_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "add_to_library.html")


def _apple_music_link(name: str, artist: str) -> str:
    """Fallback when no direct link was resolved (see _resolve_links)."""
    query = urllib.parse.quote(f"{name} {artist}")
    return f"https://music.apple.com/{apple_catalog.STOREFRONT}/search?term={query}"


LOOKUPS_PER_RUN = 15


def _copies_by_key(apple_tracks):
    """norm_key -> every library copy (the same song can be in the library
    several times: single + album, remaster...)."""
    idx = {}
    for t in apple_tracks:
        idx.setdefault(matcher.norm_key(t["name"], t["artist"]), []).append(t)
    return idx


def _prefer_loved(track, copies):
    """If another copy of the same song is already loved, use that one so
    loving a match never creates a duplicate favorite."""
    for c in copies.get(matcher.norm_key(track["name"], track["artist"]), [track]):
        if c["loved"]:
            return c
    return track


def _resolve_links(pending, limit=LOOKUPS_PER_RUN):
    """Fill t["url"] with a direct Apple Music link via the free iTunes API,
    at most `limit` lookups per run (it rate-limits at ~20/min). "" means
    looked up, no confident hit -> the HTML falls back to a search link.
    Returns True if anything was resolved.
    """
    done = 0
    for t in pending:
        if "url" in t:
            continue
        if done >= limit:
            break
        done += 1
        try:
            cand, score = matcher.best_candidate(t["name"], t["artist"], apple_catalog.search(t["name"], t["artist"]))
        except Exception:
            continue
        t["url"] = cand["url"] if cand and score >= 0.75 else ""
    return done > 0


def _reconcile_pending(candidates, apple_tracks, matches, dry_run):
    """candidates: Spotify likes with no Apple match yet, as
    {"name", "artist", "spotify_id"}. Any that now exist in the local Apple
    library get loved there and recorded in matches. Returns
    (still_pending, newly_loved_apple_ids).
    """
    copies = _copies_by_key(apple_tracks)
    still, loved = [], set()
    for c in candidates:
        key = matcher.norm_key(c["name"], c["artist"])
        a = (copies.get(key) or [None])[0] or matcher.best_match(c["name"], c["artist"], apple_tracks)
        if not a:
            still.append(c)
            continue
        a = _prefer_loved(a, copies)
        if not a["loved"]:
            print(f"Now in Apple Music library -> loving: {c['name']} - {c['artist']}")
            if not dry_run:
                music_app.set_loved(a["id"], True)
            a["loved"] = True
            loved.add(a["id"])
        matches[key] = {"spotify_id": c["spotify_id"], "apple_id": a["id"],
                        "name": c["name"], "artist": c["artist"]}
    return still, loved


def _write_unmatched_html(tracks):
    """tracks: list of {"name", "artist"}. Writes an HTML page with a direct
    Apple Music link per track so adding them to the library is one click.
    """
    # Two Spotify likes of the same song (different releases) map to one Apple add.
    unique = {}
    for t in tracks:
        key = matcher.norm_key(t["name"], t["artist"]) + ("::live" if "live" in t["name"].lower() else "")
        if key not in unique or (t.get("url") and not unique[key].get("url")):
            unique[key] = t
    seen_urls = set()
    tracks = []
    for t in unique.values():
        if t.get("url"):
            if t["url"] in seen_urls:
                continue
            seen_urls.add(t["url"])
        tracks.append(t)

    groups = {"add": [], "searching": [], "nolink": []}
    for t in sorted(tracks, key=lambda t: (t["artist"].lower(), t["name"].lower())):
        label = f"{html.escape(t['name'])} - {html.escape(t['artist'])}"
        if t.get("url"):
            groups["add"].append(f"<li><a href=\"{html.escape(t['url'])}\" target=\"_blank\">{label}</a></li>")
        elif "url" in t:
            spotify = f"https://open.spotify.com/track/{t['spotify_id']}"
            groups["nolink"].append(f"<li>{label} <small><a href=\"{spotify}\" target=\"_blank\">Spotify</a></small></li>")
        else:
            groups["searching"].append(f"<li>{label}</li>")

    first_open = [True]

    def section(title, note, items):
        if not items:
            return ""
        attr = " open" if first_open[0] else ""
        first_open[0] = False
        return (f"<details{attr}><summary>{title} ({len(items)})</summary>"
                f"<p class=\"note\">{note}</p><ul>{chr(10).join(items)}</ul></details>")

    body = (
        section("Agregar", 'Abri el link y toca "Agregar a la biblioteca". El proximo sync lo ama y lo saca de esta lista.', groups["add"])
        + section("Buscando link", "Todavia no se busco el link directo; aparecen en las proximas corridas.", groups["searching"])
        + section("Sin link en Apple Music", "No estan en el catalogo de Apple Music AR (o no se encontro con confianza).", groups["nolink"])
    )
    page = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Agregar a Apple Music</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; }}
li {{ margin-bottom: 10px; font-size: 16px; }}
a {{ color: #fa233b; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.note {{ color: #666; margin-top: -6px; }}
details {{ margin-top: 24px; }}
summary {{ font-size: 18px; font-weight: 600; cursor: pointer; list-style: none; }}
summary::-webkit-details-marker {{ display: none; }}
summary::before {{ content: "+"; display: inline-block; width: 1.2em; color: #fa233b; }}
details[open] > summary::before {{ content: "\\2212"; }}
</style>
</head>
<body>
<h2>Liked en Spotify, sin match en tu biblioteca de Apple Music ({len(tracks)})</h2>
{body}
</body>
</html>"""
    with open(UNMATCHED_HTML_PATH, "w") as f:
        f.write(page)


def build_baseline(sp, spotify_tracks, apple_tracks):
    matches = {}
    apple_loved_tracks = [t for t in apple_tracks if t["loved"]]
    apple_loved_by_key = {matcher.norm_key(t["name"], t["artist"]): t for t in apple_loved_tracks}

    for t in spotify_tracks:
        key = matcher.norm_key(t["name"], t["artist"])
        apple_t = apple_loved_by_key.get(key) or matcher.best_match(t["name"], t["artist"], apple_loved_tracks)
        if apple_t:
            matches[key] = {
                "spotify_id": t["id"], "apple_id": apple_t["id"],
                "name": t["name"], "artist": t["artist"],
            }
    return matches


def run_sync(dry_run: bool):
    sp = spotify_client.get_client()
    prev = state.load_state()

    print("Fetching Apple Music library (can take a while for large libraries)...")
    apple_tracks = music_app.get_library_tracks()
    apple_by_id = {t["id"]: t for t in apple_tracks}
    current_apple_loved_ids = {t["id"] for t in apple_tracks if t["loved"]}

    # Unchanged Apple side + unchanged Spotify head (total, newest like) means
    # nothing to sync: skip the ~20-request full liked-songs download that
    # was tripping Spotify's rate limit when polling every 30 minutes.
    head = spotify_client.get_head(sp)
    if (prev and prev.get("pending_add") is not None and prev.get("spotify_head") == list(head)
            and set(prev["apple_loved_ids"]) == current_apple_loved_ids):
        print(f"No changes (Spotify: {head[0]} liked. Apple Music: {len(apple_tracks)} in library, "
              f"{len(current_apple_loved_ids)} loved).")
        matches, pending, loved = prev["matches"], prev["pending_add"], set()
        changed = False
        # Library grew/shrank: some pending tracks may have been added by hand.
        if prev.get("apple_count") != len(apple_tracks) and pending:
            pending, loved = _reconcile_pending(pending, apple_tracks, matches, dry_run)
            changed = True
        if _resolve_links(pending):
            changed = True
        if changed:
            if not dry_run:
                prev.update(matches=matches, pending_add=pending, apple_count=len(apple_tracks),
                            apple_loved_ids=sorted(current_apple_loved_ids | loved),
                            html_notified_keys=sorted(matcher.norm_key(t["name"], t["artist"]) for t in pending))
                state.save_state(prev)
        if pending:
            _write_unmatched_html(pending)
        return

    print("Fetching Spotify Liked Songs...")
    spotify_tracks = spotify_client.get_liked_tracks(sp)
    spotify_by_id = {t["id"]: t for t in spotify_tracks}
    current_spotify_liked_ids = set(spotify_by_id)

    print(f"Spotify: {len(current_spotify_liked_ids)} liked. "
          f"Apple Music: {len(apple_tracks)} in library, {len(current_apple_loved_ids)} loved.")

    if prev is None:
        print("\nNo prior state found — recording baseline, no changes will be applied this run.")
        matches = build_baseline(sp, spotify_tracks, apple_tracks)
        print(f"Matched {len(matches)} tracks between the two libraries as a starting point.")
        state.save_state({
            "matches": matches,
            "spotify_liked_ids": sorted(current_spotify_liked_ids),
            "apple_loved_ids": sorted(current_apple_loved_ids),
        })
        print("Baseline saved. Run again after you like/love something to sync it.")
        return

    prev_spotify_ids = set(prev["spotify_liked_ids"])
    prev_apple_ids = set(prev["apple_loved_ids"])
    matches = prev.get("matches", {})
    unmatched = []

    def record_match(key, spotify_id=None, apple_id=None, name="", artist=""):
        entry = matches.get(key, {"spotify_id": None, "apple_id": None, "name": name, "artist": artist})
        if spotify_id:
            entry["spotify_id"] = spotify_id
        if apple_id:
            entry["apple_id"] = apple_id
        entry["name"] = name or entry["name"]
        entry["artist"] = artist or entry["artist"]
        matches[key] = entry

    copies = _copies_by_key(apple_tracks)

    # Removals first, so a fresh like elsewhere this run isn't immediately undone.
    spotify_removed = prev_spotify_ids - current_spotify_liked_ids
    for m in matches.values():
        if m.get("spotify_id") in spotify_removed and m.get("apple_id"):
            apple_track = apple_by_id.get(m["apple_id"])
            if apple_track and apple_track["loved"]:
                print(f"Unliked on Spotify -> un-loving on Apple Music: {m['name']} - {m['artist']}")
                if not dry_run:
                    music_app.set_loved(m["apple_id"], False)
                apple_track["loved"] = False
                current_apple_loved_ids.discard(m["apple_id"])

    apple_removed = prev_apple_ids - current_apple_loved_ids
    for m in matches.values():
        if m.get("apple_id") in apple_removed and m.get("spotify_id"):
            other_copy_loved = any(
                c["loved"] for c in copies.get(matcher.norm_key(m["name"], m["artist"]), []))
            if m["spotify_id"] in current_spotify_liked_ids and not other_copy_loved:
                print(f"Un-loved on Apple Music -> removing from Spotify Liked Songs: {m['name']} - {m['artist']}")
                if not dry_run:
                    spotify_client.remove_track(sp, m["spotify_id"])
                current_spotify_liked_ids.discard(m["spotify_id"])

    # Additions
    spotify_added = current_spotify_liked_ids - prev_spotify_ids
    for sid in spotify_added:
        t = spotify_by_id[sid]
        key = matcher.norm_key(t["name"], t["artist"])
        apple_id = matches.get(key, {}).get("apple_id")
        apple_track = apple_by_id.get(apple_id) if apple_id else None
        if not apple_track:
            apple_track = matcher.best_match(t["name"], t["artist"], apple_tracks)
        if apple_track:
            apple_track = _prefer_loved(apple_track, copies)
            if not apple_track["loved"]:
                print(f"New Spotify like -> loving on Apple Music: {t['name']} - {t['artist']}")
                if not dry_run:
                    music_app.set_loved(apple_track["id"], True)
                apple_track["loved"] = True
                current_apple_loved_ids.add(apple_track["id"])
            record_match(key, spotify_id=sid, apple_id=apple_track["id"], name=t["name"], artist=t["artist"])
        else:
            unmatched.append(f"Liked on Spotify, not found in Apple Music library: {t['name']} - {t['artist']}")
            record_match(key, spotify_id=sid, name=t["name"], artist=t["artist"])

    apple_added = current_apple_loved_ids - prev_apple_ids
    for aid in apple_added:
        t = apple_by_id[aid]
        key = matcher.norm_key(t["name"], t["artist"])
        existing = matches.get(key, {})
        spotify_id = existing.get("spotify_id")
        found = spotify_by_id.get(spotify_id) if spotify_id and spotify_id in current_spotify_liked_ids else None
        if not found:
            found = spotify_client.search_track(sp, t["name"], t["artist"])
        if found:
            if found["id"] not in current_spotify_liked_ids:
                print(f"New Apple Music love -> adding to Spotify Liked Songs: {t['name']} - {t['artist']}")
                if not dry_run:
                    spotify_client.save_track(sp, found["id"])
                current_spotify_liked_ids.add(found["id"])
            record_match(key, spotify_id=found["id"], apple_id=aid, name=t["name"], artist=t["artist"])
        else:
            unmatched.append(f"Loved on Apple Music, not found on Spotify: {t['name']} - {t['artist']}")
            record_match(key, apple_id=aid, name=t["name"], artist=t["artist"])

    candidates = []
    for sid in current_spotify_liked_ids:
        t = spotify_by_id.get(sid)
        if t is None:
            continue
        m = matches.get(matcher.norm_key(t["name"], t["artist"]))
        if not (m and m.get("apple_id")):
            candidates.append({"name": t["name"], "artist": t["artist"], "spotify_id": sid})
    unmatched_spotify_tracks, newly_loved = _reconcile_pending(candidates, apple_tracks, matches, dry_run)
    current_apple_loved_ids |= newly_loved
    prev_urls = {p["spotify_id"]: p["url"] for p in prev.get("pending_add") or [] if "url" in p}
    for t in unmatched_spotify_tracks:
        if t["spotify_id"] in prev_urls:
            t["url"] = prev_urls[t["spotify_id"]]
    _resolve_links(unmatched_spotify_tracks)
    unmatched_keys = {matcher.norm_key(t["name"], t["artist"]) for t in unmatched_spotify_tracks}
    prev_notified_keys = set(prev.get("html_notified_keys", []))

    if not dry_run:
        new_state = {
            "matches": matches,
            "spotify_liked_ids": sorted(current_spotify_liked_ids),
            "apple_loved_ids": sorted(current_apple_loved_ids),
            "rejected": prev.get("rejected", []),
            "html_notified_keys": sorted(unmatched_keys),
            "pending_add": unmatched_spotify_tracks,
            "apple_count": len(apple_tracks),
        }
        # Only trust the probe if we didn't change Spotify ourselves this run.
        if current_spotify_liked_ids == {t["id"] for t in spotify_tracks}:
            new_state["spotify_head"] = list(head)
        state.save_state(new_state)

    print(f"\n{'[dry-run] ' if dry_run else ''}Done. "
          f"{len(spotify_added)} new Spotify likes, {len(apple_added)} new Apple loves, "
          f"{len(spotify_removed)} Spotify removals, {len(apple_removed)} Apple removals.")
    if unmatched:
        print(f"\n{len(unmatched)} unmatched -- review manually:")
        for line in unmatched:
            print(f"  - {line}")

    if unmatched_spotify_tracks:
        _write_unmatched_html(unmatched_spotify_tracks)
        if not dry_run and (unmatched_keys - prev_notified_keys):
            subprocess.run(["open", UNMATCHED_HTML_PATH])


def run_push(dry_run: bool):
    """One-time catch-up: favorite every current Spotify like that's already
    in the Apple Music library (whether or not it was matched before), and
    report (without touching Spotify) what's favorited on Apple Music but
    missing on Spotify. Ends by saving the result as the new baseline, so a
    plain `sync.py` run afterwards only has to sync what changes from here.
    """
    sp = spotify_client.get_client()
    prior_rejected = (state.load_state() or {}).get("rejected", [])

    print("Fetching Spotify Liked Songs...")
    spotify_tracks = spotify_client.get_liked_tracks(sp)

    print("Fetching Apple Music library (can take a while for large libraries)...")
    apple_tracks = music_app.get_library_tracks()
    apple_by_key = {}
    for t in apple_tracks:
        apple_by_key.setdefault(matcher.norm_key(t["name"], t["artist"]), t)
    copies_all = _copies_by_key(apple_tracks)

    print(f"Spotify: {len(spotify_tracks)} liked. Apple Music: {len(apple_tracks)} in library, "
          f"{sum(1 for t in apple_tracks if t['loved'])} favorited.\n")

    matches = {}
    pushed = 0
    already = 0
    not_in_apple_library = []

    for t in spotify_tracks:
        key = matcher.norm_key(t["name"], t["artist"])
        apple_t = apple_by_key.get(key) or matcher.best_match(t["name"], t["artist"], apple_tracks)
        if apple_t:
            apple_t = _prefer_loved(apple_t, copies_all)
            matches[key] = {"spotify_id": t["id"], "apple_id": apple_t["id"], "name": t["name"], "artist": t["artist"]}
            if apple_t["loved"]:
                already += 1
            else:
                print(f"Favoriting on Apple Music: {t['name']} - {t['artist']}")
                if not dry_run:
                    music_app.set_loved(apple_t["id"], True)
                apple_t["loved"] = True
                pushed += 1
        else:
            not_in_apple_library.append(f"{t['name']} - {t['artist']}")

    missing_from_spotify = []
    for t in apple_tracks:
        if not t["loved"]:
            continue
        key = matcher.norm_key(t["name"], t["artist"])
        if key not in matches:
            missing_from_spotify.append(f"{t['name']} - {t['artist']}")

    print(f"\n{'[dry-run] ' if dry_run else ''}Favorited {pushed} on Apple Music "
          f"({already} were already favorited there).")

    if not_in_apple_library:
        path = "not_in_apple_library.txt"
        with open(path, "w") as f:
            f.write("\n".join(sorted(not_in_apple_library)))
        print(f"\n{len(not_in_apple_library)} Spotify-liked songs aren't in your Apple Music library at all "
              f"(can't auto-add — Music.app scripting has no catalog search). List saved to {path}")

    if missing_from_spotify:
        path = "missing_from_spotify.txt"
        with open(path, "w") as f:
            f.write("\n".join(sorted(missing_from_spotify)))
        print(f"\n{len(missing_from_spotify)} songs are favorited on Apple Music but not liked on Spotify "
              f"(not touched). List saved to {path}")

    if not dry_run:
        state.save_state({
            "matches": matches,
            "spotify_liked_ids": sorted(t["id"] for t in spotify_tracks),
            "apple_loved_ids": sorted(t["id"] for t in apple_tracks if t["loved"]),
            "rejected": prior_rejected,
        })
        print("\nState saved as new baseline — future `python3 sync.py` runs will only sync what changes from here.")


def run_review(min_score: float):
    """Interactive: for tracks that still have no confirmed match, show the
    closest candidate (below the auto-accept threshold) and ask for a y/n
    confirmation before applying anything. Rejections are remembered so the
    same pair isn't asked about again.

    Spotify-side gaps are matched against the local Apple Music library
    (nothing else is possible — no catalog search via AppleScript). Apple
    Music-side gaps are matched against a live Spotify catalog search, which
    has far more reach than comparing only against your current likes.
    """
    sp = spotify_client.get_client()

    print("Fetching Spotify Liked Songs...")
    spotify_tracks = spotify_client.get_liked_tracks(sp)
    current_spotify_liked_ids = {t["id"] for t in spotify_tracks}

    print("Fetching Apple Music library (can take a while for large libraries)...")
    apple_tracks = music_app.get_library_tracks()
    current_apple_loved_ids = {t["id"] for t in apple_tracks if t["loved"]}

    prev = state.load_state()
    if prev is None:
        print("No hay baseline todavia -- corre `python3 sync.py --push` primero.")
        return

    matches = prev.get("matches", {})
    rejected = set(prev.get("rejected", []))
    matched_spotify_ids = {m["spotify_id"] for m in matches.values() if m.get("spotify_id")}
    matched_apple_ids = {m["apple_id"] for m in matches.values() if m.get("apple_id")}

    def ask():
        try:
            return input("Es la misma cancion? [y/N/q] ").strip().lower()
        except EOFError:
            return "q"

    quit_requested = False
    reviewed = accepted = 0

    print("\n--- Spotify likes sin matchear en Apple Music ---")
    for t in spotify_tracks:
        if quit_requested:
            break
        if t["id"] in matched_spotify_ids:
            continue
        key = matcher.norm_key(t["name"], t["artist"])
        if key in rejected:
            continue
        cand, score = matcher.best_candidate(t["name"], t["artist"], apple_tracks)
        if not cand or score < min_score:
            continue
        reviewed += 1
        print(f"\nSpotify:            {t['name']} - {t['artist']}")
        print(f"Apple Music ({score:.0%}): {cand['name']} - {cand['artist']}")
        answer = ask()
        if answer == "q":
            quit_requested = True
            break
        if answer == "y":
            accepted += 1
            if not cand["loved"]:
                music_app.set_loved(cand["id"], True)
                cand["loved"] = True
                current_apple_loved_ids.add(cand["id"])
            matches[key] = {"spotify_id": t["id"], "apple_id": cand["id"], "name": t["name"], "artist": t["artist"]}
            matched_apple_ids.add(cand["id"])
            print("-> favorita en Apple Music.")
        else:
            rejected.add(key)

    print("\n--- Apple Music loves sin matchear en Spotify (buscando en el catalogo real) ---")
    for t in apple_tracks:
        if quit_requested:
            break
        if not t["loved"] or t["id"] in matched_apple_ids:
            continue
        key = matcher.norm_key(t["name"], t["artist"])
        if key in rejected:
            continue
        candidates = spotify_client.search_candidates(sp, t["name"], t["artist"], limit=5)
        if not candidates:
            continue
        cand, score = matcher.best_candidate(t["name"], t["artist"], candidates)
        if not cand or score < min_score:
            continue
        reviewed += 1
        print(f"\nApple Music:      {t['name']} - {t['artist']}")
        print(f"Spotify ({score:.0%}): {cand['name']} - {cand['artist']}")
        answer = ask()
        if answer == "q":
            quit_requested = True
            break
        if answer == "y":
            accepted += 1
            if cand["id"] not in current_spotify_liked_ids:
                spotify_client.save_track(sp, cand["id"])
                current_spotify_liked_ids.add(cand["id"])
            matches[key] = {"spotify_id": cand["id"], "apple_id": t["id"], "name": t["name"], "artist": t["artist"]}
            print("-> agregada a Liked Songs de Spotify.")
        else:
            rejected.add(key)

    state.save_state({
        "matches": matches,
        "spotify_liked_ids": sorted(current_spotify_liked_ids),
        "apple_loved_ids": sorted(current_apple_loved_ids),
        "rejected": sorted(rejected),
    })
    print(f"\nRevisadas {reviewed}, confirmadas {accepted}. Estado guardado.")


def run_assist():
    """Semi-assisted catch-up for Spotify likes missing from the local Apple
    Music library: look each one up via the free iTunes Search API and open
    the best candidate directly in Music.app so you just have to glance at
    it and click "Add to Library" yourself. Doesn't touch anything -- purely
    a navigation shortcut. Nothing is added automatically.
    """
    sp = spotify_client.get_client()

    print("Fetching Spotify Liked Songs...")
    spotify_tracks = spotify_client.get_liked_tracks(sp)

    print("Fetching Apple Music library...")
    apple_tracks = music_app.get_library_tracks()
    apple_by_key = {matcher.norm_key(t["name"], t["artist"]): t for t in apple_tracks}

    pending = []
    for t in spotify_tracks:
        key = matcher.norm_key(t["name"], t["artist"])
        if apple_by_key.get(key) or matcher.best_match(t["name"], t["artist"], apple_tracks):
            continue
        pending.append(t)

    print(f"\n{len(pending)} Spotify likes no encontrados en tu biblioteca de Apple Music.\n"
          f"Por cada una te abro el mejor candidato en Music.app -- mira, toca 'Agregar a Biblioteca' "
          f"si corresponde, y apreta Enter para seguir con la proxima ('q' para salir).\n")

    for i, t in enumerate(pending, 1):
        try:
            candidates = apple_catalog.search(t["name"], t["artist"])
        except Exception as e:
            print(f"[{i}/{len(pending)}] {t['name']} - {t['artist']}: error buscando ({e}), salteando.")
            continue
        if not candidates:
            print(f"[{i}/{len(pending)}] {t['name']} - {t['artist']}: sin resultados en el catalogo de Apple Music.")
            continue
        cand, score = matcher.best_candidate(t["name"], t["artist"], candidates)

        print(f"[{i}/{len(pending)}] Spotify: {t['name']} - {t['artist']}")
        print(f"    Abriendo ({score:.0%}): {cand['name']} - {cand['artist']}")
        try:
            music_app.open_location(cand["url"])
        except music_app.MusicAppError as e:
            print(f"    No se pudo abrir: {e}")

        try:
            answer = input("    Enter para seguir, 'q' para salir: ").strip().lower()
        except EOFError:
            answer = "q"
        if answer == "q":
            print(f"\nCortado en {i}/{len(pending)}. Volve a correr --assist cuando quieras seguir "
                  f"(las que ya agregaste no van a aparecer de nuevo).")
            return

    print("\nListo. Corre `python3 sync.py --push` para favoritear en Apple Music lo que hayas agregado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without applying it")
    parser.add_argument("--push", action="store_true",
                         help="One-time catch-up: favorite all current Spotify likes on Apple Music "
                              "and report what's missing on Spotify, without touching Spotify")
    parser.add_argument("--review", action="store_true",
                         help="Interactive: show near-miss fuzzy matches for still-unmatched tracks "
                              "and ask for y/n confirmation before applying")
    parser.add_argument("--min-score", type=float, default=0.75,
                         help="Lowest match score to bother showing during --review (0-1, default 0.75)")
    parser.add_argument("--assist", action="store_true",
                         help="Semi-assisted: look up each Spotify like missing from Apple Music via the "
                              "free iTunes Search API and open it in Music.app for you to add by hand")
    args = parser.parse_args()

    for var in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
        if not os.environ.get(var):
            print(f"Missing required env var: {var}", file=sys.stderr)
            sys.exit(1)

    try:
        until = float(open(RATE_LIMIT_PATH).read())
    except (OSError, ValueError):
        until = 0
    if time.time() < until:
        print(f"Spotify rate limit active, skipping until {time.strftime('%H:%M', time.localtime(until))}.")
        sys.exit(0)

    try:
        if args.assist:
            run_assist()
        elif args.review:
            run_review(min_score=args.min_score)
        elif args.push:
            run_push(dry_run=args.dry_run)
        else:
            run_sync(dry_run=args.dry_run)
    except SpotifyException as e:
        if e.http_status != 429:
            raise
        os.makedirs(state.CONFIG_DIR, exist_ok=True)
        with open(RATE_LIMIT_PATH, "w") as f:
            f.write(str(time.time() + RATE_LIMIT_BACKOFF))
        print(f"Spotify rate limit hit; backing off {RATE_LIMIT_BACKOFF // 60} min.")
