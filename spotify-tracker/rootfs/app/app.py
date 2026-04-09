import os
import json
import sqlite3
import logging
from datetime import datetime, date
from flask import Flask, render_template, redirect, request, session, url_for, jsonify
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.jinja_env.globals.update(enumerate=enumerate)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret-key")

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "spotify_tracker.db")
TOKEN_PATH = os.path.join(DATA_DIR, ".spotify_token")
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:8765/callback")

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SCAN_DAY = os.environ.get("SCAN_DAY", "sunday")
SCAN_HOUR = int(os.environ.get("SCAN_HOUR", "0"))
INGRESS_ENTRY = os.environ.get("INGRESS_ENTRY", "")

SCOPE = "user-library-read"

DAY_MAP = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed",
    "thursday": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun"
}

# ─── Database ────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_label TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            total_tracks INTEGER NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            spotify_id TEXT NOT NULL,
            name TEXT NOT NULL,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            added_at TEXT,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS removed_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spotify_id TEXT NOT NULL,
            name TEXT NOT NULL,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            last_seen_week TEXT NOT NULL,
            detected_week TEXT NOT NULL,
            detected_date TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized at %s", DB_PATH)

# ─── Spotify Auth ─────────────────────────────────────────────────────────────

def get_sp_oauth():
    return SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=TOKEN_PATH,
        show_dialog=False
    )

def get_spotify_client():
    oauth = get_sp_oauth()
    token_info = oauth.get_cached_token()
    if not token_info:
        return None
    if oauth.is_token_expired(token_info):
        token_info = oauth.refresh_access_token(token_info["refresh_token"])
    return spotipy.Spotify(auth=token_info["access_token"])

# ─── Core Tracker Logic ───────────────────────────────────────────────────────

def fetch_all_liked_songs(sp):
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
                    "spotify_id": t["id"],
                    "name": t["name"],
                    "artist": ", ".join(a["name"] for a in t["artists"]),
                    "album": t["album"]["name"],
                    "added_at": item.get("added_at", ""),
                })
        offset += limit
        if len(items) < limit:
            break
    return tracks

def get_week_label(dt=None):
    if dt is None:
        dt = date.today()
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"

def save_snapshot(tracks):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    week_label = get_week_label()
    snapshot_date = date.today().isoformat()

    # Avoid duplicate snapshots for the same week
    c.execute("SELECT id FROM snapshots WHERE week_label = ?", (week_label,))
    existing = c.fetchone()
    if existing:
        logger.info("Snapshot for week %s already exists, overwriting...", week_label)
        c.execute("DELETE FROM tracks WHERE snapshot_id = ?", (existing[0],))
        c.execute("DELETE FROM snapshots WHERE id = ?", (existing[0],))

    c.execute(
        "INSERT INTO snapshots (week_label, snapshot_date, total_tracks) VALUES (?, ?, ?)",
        (week_label, snapshot_date, len(tracks))
    )
    snapshot_id = c.lastrowid

    for t in tracks:
        c.execute(
            "INSERT INTO tracks (snapshot_id, spotify_id, name, artist, album, added_at) VALUES (?, ?, ?, ?, ?, ?)",
            (snapshot_id, t["spotify_id"], t["name"], t["artist"], t["album"], t["added_at"])
        )

    conn.commit()
    conn.close()
    logger.info("Saved snapshot %s with %d tracks", week_label, len(tracks))
    return snapshot_id, week_label

def detect_removed_tracks():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id, week_label FROM snapshots ORDER BY snapshot_date DESC LIMIT 2")
    rows = c.fetchall()
    if len(rows) < 2:
        conn.close()
        logger.info("Not enough snapshots yet for comparison")
        return []

    current_snap_id, current_week = rows[0]
    prev_snap_id, prev_week = rows[1]

    c.execute("SELECT spotify_id, name, artist, album FROM tracks WHERE snapshot_id = ?", (current_snap_id,))
    current_ids = {row[0]: row for row in c.fetchall()}

    c.execute("SELECT spotify_id, name, artist, album FROM tracks WHERE snapshot_id = ?", (prev_snap_id,))
    prev_tracks = c.fetchall()

    removed = []
    for row in prev_tracks:
        sid = row[0]
        if sid not in current_ids:
            # Check if already logged
            c.execute("SELECT id FROM removed_tracks WHERE spotify_id = ? AND detected_week = ?", (sid, current_week))
            if not c.fetchone():
                c.execute(
                    "INSERT INTO removed_tracks (spotify_id, name, artist, album, last_seen_week, detected_week, detected_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (sid, row[1], row[2], row[3], prev_week, current_week, date.today().isoformat())
                )
                removed.append({"spotify_id": sid, "name": row[1], "artist": row[2], "album": row[3]})

    conn.commit()
    conn.close()
    logger.info("Detected %d removed tracks this week", len(removed))
    return removed

def run_weekly_scan():
    logger.info("Running weekly scan...")
    sp = get_spotify_client()
    if not sp:
        logger.warning("No Spotify token available. Skipping scan.")
        return
    tracks = fetch_all_liked_songs(sp)
    save_snapshot(tracks)
    removed = detect_removed_tracks()
    logger.info("Scan complete. %d liked songs, %d removed.", len(tracks), len(removed))

# ─── Scheduler ────────────────────────────────────────────────────────────────

def start_scheduler():
    scheduler = BackgroundScheduler()
    cron_day = DAY_MAP.get(SCAN_DAY.lower(), "sun")
    scheduler.add_job(
        run_weekly_scan,
        CronTrigger(day_of_week=cron_day, hour=SCAN_HOUR, minute=0),
        id="weekly_scan",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started: every %s at %02d:00", SCAN_DAY, SCAN_HOUR)

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    sp = get_spotify_client()
    authed = sp is not None

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get all snapshots ordered by date
    c.execute("SELECT id, week_label, snapshot_date, total_tracks FROM snapshots ORDER BY snapshot_date DESC")
    snapshots = c.fetchall()

    # Get removed tracks grouped by detected_week
    c.execute("""
        SELECT spotify_id, name, artist, album, last_seen_week, detected_week, detected_date
        FROM removed_tracks
        ORDER BY detected_date DESC
    """)
    removed_rows = c.fetchall()
    conn.close()

    # Group removed by week
    removed_by_week = {}
    for row in removed_rows:
        week = row[5]
        if week not in removed_by_week:
            removed_by_week[week] = []
        removed_by_week[week].append({
            "spotify_id": row[0], "name": row[1], "artist": row[2],
            "album": row[3], "last_seen_week": row[4], "detected_week": row[5], "detected_date": row[6]
        })

    return render_template(
        "index.html",
        authed=authed,
        snapshots=snapshots,
        removed_by_week=removed_by_week,
        scan_day=SCAN_DAY.capitalize(),
        scan_hour=SCAN_HOUR,
        ingress_entry=INGRESS_ENTRY
    )

@app.route("/login")
def login():
    oauth = get_sp_oauth()
    auth_url = oauth.get_authorize_url()
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Authorization failed.", 400
    oauth = get_sp_oauth()
    oauth.get_access_token(code)
    return redirect(url_for("index"))

@app.route("/scan", methods=["POST"])
def manual_scan():
    sp = get_spotify_client()
    if not sp:
        return jsonify({"error": "Not authenticated with Spotify"}), 401
    tracks = fetch_all_liked_songs(sp)
    snap_id, week_label = save_snapshot(tracks)
    removed = detect_removed_tracks()
    return jsonify({
        "status": "ok",
        "week": week_label,
        "total": len(tracks),
        "removed": len(removed)
    })

@app.route("/snapshot/<int:snap_id>")
def snapshot_detail(snap_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT week_label, snapshot_date, total_tracks FROM snapshots WHERE id = ?", (snap_id,))
    snap = c.fetchone()
    if not snap:
        conn.close()
        return "Snapshot not found", 404
    c.execute("SELECT name, artist, album, added_at FROM tracks WHERE snapshot_id = ? ORDER BY name", (snap_id,))
    tracks = c.fetchall()
    conn.close()
    return render_template("snapshot.html", snap=snap, tracks=tracks, snap_id=snap_id, ingress_entry=INGRESS_ENTRY)

@app.route("/api/stats")
def api_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT week_label, total_tracks FROM snapshots ORDER BY snapshot_date ASC")
    rows = c.fetchall()
    c.execute("SELECT detected_week, COUNT(*) FROM removed_tracks GROUP BY detected_week ORDER BY detected_week ASC")
    removed = c.fetchall()
    conn.close()
    return jsonify({"snapshots": rows, "removed_by_week": removed})

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    start_scheduler()
    app.run(host="0.0.0.0", port=8765, debug=False)