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
import os
import sys

import apple_catalog
import matcher
import music_app
import spotify_client
import state


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

    print("Fetching Spotify Liked Songs...")
    spotify_tracks = spotify_client.get_liked_tracks(sp)
    spotify_by_id = {t["id"]: t for t in spotify_tracks}
    current_spotify_liked_ids = set(spotify_by_id)

    print("Fetching Apple Music library (can take a while for large libraries)...")
    apple_tracks = music_app.get_library_tracks()
    apple_by_id = {t["id"]: t for t in apple_tracks}
    current_apple_loved_ids = {t["id"] for t in apple_tracks if t["loved"]}

    print(f"Spotify: {len(current_spotify_liked_ids)} liked. "
          f"Apple Music: {len(apple_tracks)} in library, {len(current_apple_loved_ids)} loved.")

    prev = state.load_state()
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
            if m["spotify_id"] in current_spotify_liked_ids:
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

    if not dry_run:
        state.save_state({
            "matches": matches,
            "spotify_liked_ids": sorted(current_spotify_liked_ids),
            "apple_loved_ids": sorted(current_apple_loved_ids),
            "rejected": prev.get("rejected", []),
        })

    print(f"\n{'[dry-run] ' if dry_run else ''}Done. "
          f"{len(spotify_added)} new Spotify likes, {len(apple_added)} new Apple loves, "
          f"{len(spotify_removed)} Spotify removals, {len(apple_removed)} Apple removals.")
    if unmatched:
        print(f"\n{len(unmatched)} unmatched -- review manually:")
        for line in unmatched:
            print(f"  - {line}")


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

    if args.assist:
        run_assist()
    elif args.review:
        run_review(min_score=args.min_score)
    elif args.push:
        run_push(dry_run=args.dry_run)
    else:
        run_sync(dry_run=args.dry_run)
