# Homeassistant Apps by me (actually Claude, but with my ideas)

# Deco → AdGuard Sync — Home Assistant Add-on

Automatically syncs connected devices from your **TP-Link Deco XE75 Pro** into **AdGuard Home** as persistent clients, using both devices' local APIs.

## How it works

1. Connects to the Deco and fetches all currently connected devices
2. Filters out infrastructure devices by minimum IP (configurable)
3. Compares against existing AdGuard Home clients (by name and by IP)
4. Adds only new clients — existing ones are safely skipped
5. All new clients are created with global settings and global blocked services enabled

The sync runs once on startup, then automatically every 6 hours.

## Installation

1. In Home Assistant go to **Settings → Add-ons → Add-on Store**
2. Click the **⋮** menu (top right) → **Repositories**
3. Add: `https://github.com/sebabordon/deco-to-adguard`
4. Click **Add** → **Close**
5. Find **"Deco → AdGuard Sync"** in the store and install it
6. Go to the **Configuration** tab and fill in your credentials
7. Click **Start**

## Configuration

| Option | Description | Example |
|---|---|---|
| `deco_host` | URL of your main Deco node | `https://10.0.2.1` |
| `deco_pass` | Deco local admin password | set in Deco app → More → Local Management |
| `agh_host` | AdGuard Home URL with port | `https://10.0.2.232:3002` |
| `agh_user` | AdGuard Home username | `admin` |
| `agh_pass` | AdGuard Home password | — |
| `min_ip_suffix` | Minimum last IP octet to export | `100` → exports from x.x.x.100 upward |
| `run_on_start` | Run a sync immediately on startup | `true` |

### About `min_ip_suffix`

This filters out infrastructure devices (router, APs, switches, servers) which typically have low IPs like `.1`, `.2`, `.10`, etc.

For example, with `min_ip_suffix: 100`, only devices with IPs ending in `.100` or higher will be exported to AdGuard Home.

## Notes

- SSL certificate verification is disabled for both the Deco and AdGuard Home connections, since both typically use self-signed certificates on local networks
- Clients already in AdGuard Home are matched by **name** and by **IP address** — so renaming a client in AdGuard Home won't cause duplicates
- To force an immediate sync without waiting 6 hours, simply restart the add-on

## Requirements

- TP-Link Deco XE75 Pro (or compatible Deco model)
- AdGuard Home with API access enabled
- Local Management enabled on the Deco app (More → Local Management)
