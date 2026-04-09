# Spotify Liked Songs Tracker — HA Add-on

Tracks your Spotify liked songs weekly, stores snapshots, and shows you which songs disappeared each week.

---

## 1. Create a Spotify App

1. Go to https://developer.spotify.com/dashboard
2. Click **Create app**
3. Name it anything (e.g. "HA Liked Tracker")
4. Set **Redirect URI** to: `http://YOUR_HA_IP:8099/callback`
   - Example: `http://192.168.1.100:8099/callback`
5. Copy your **Client ID** and **Client Secret**

---

## 2. Install the Add-on

### Option A — Sideload (local add-on)

1. Copy the entire `spotify-tracker-addon` folder to:
   ```
   /addons/spotify_tracker/
   ```
   on your Home Assistant host (via Samba, SSH, or the file editor add-on).

2. Go to **Settings → Add-ons → Add-on Store**
3. Click the **⋮ menu** (top right) → **Check for updates** or **Reload**
4. You should see **"Local add-ons"** — find **Spotify Liked Songs Tracker** and install it.

---

## 3. Configure the Add-on

In the add-on **Configuration** tab, set:

```yaml
spotify_client_id: "your_client_id_here"
spotify_client_secret: "your_client_secret_here"
scan_day: "sunday"   # day of the week to auto-scan
scan_hour: 0         # hour (0–23) to run the scan
```

Save and **Start** the add-on.

---

## 4. Authorize Spotify

1. Open the add-on's **Web UI** (via the "Open Web UI" button or the sidebar panel)
2. Click **"Connect with Spotify"**
3. Log in and authorize the app
4. You'll be redirected back — you're connected ✓

---

## 5. Take your first snapshot

Click **"Scan now"** in the top right. This saves your current liked songs.

After 2+ scans (on different weeks), the tracker will automatically show which songs disappeared between snapshots.

---

## How it works

| Component | Details |
|-----------|---------|
| Storage | SQLite at `/data/spotify_tracker.db` (persists across restarts) |
| Scheduler | APScheduler — runs every configured day/hour |
| Auth | Spotify OAuth 2.0 — token cached at `/data/.spotify_token` |
| Web | Flask + Nginx — served through HA ingress (no extra ports needed) |

---

## Folder structure

```
spotify-tracker-addon/
├── config.yaml          # Add-on manifest
├── Dockerfile
├── requirements.txt
└── rootfs/
    ├── usr/bin/run.sh   # Startup script
    ├── etc/nginx/conf.d/default.conf
    └── app/
        ├── app.py       # Flask backend
        └── templates/
            ├── index.html
            └── snapshot.html
```
