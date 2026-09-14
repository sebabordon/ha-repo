# Homeassistant Apps by me (actually Claude, but with my ideas)

# Deco → AdGuard Sync — Home Assistant Add-on

Automatically syncs connected devices from your **TP-Link Deco XE75 Pro** into **AdGuard Home** as persistent clients, using both devices' local APIs.

## How it works

1. Connects to the Deco and fetches all currently connected devices
2. Filters out infrastructure devices by minimum IP (configurable)
3. Compares against existing AdGuard Home clients — **Deco data takes precedence**:
   - If a device's fixed (non-randomized) MAC matches an existing AdGuard client, that client is updated: name and IP are synced, the old IP is removed.
   - Otherwise, if the device's name matches an existing client, its IP is updated (old IP removed). This is the primary match for phones, since iOS/Android randomize their MAC per network.
   - If nothing matches, a new client is created — unless the device only has a randomized MAC, in which case it's skipped to avoid cluttering AdGuard with throwaway entries (configurable).
4. Clients created by this add-on (tagged `deco-sync`) that stop appearing on the Deco for more than `stale_days` are removed from AdGuard. Manually created AdGuard clients are never touched.
5. All new/updated clients keep global settings and global blocked services enabled

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
| `stale_days` | Days a Deco-managed client can go unseen before it's removed from AdGuard | `7`, `0` disables cleanup |
| `exclude_random_mac` | Skip creating new AdGuard clients for devices with a randomized MAC | `true` |

### About `min_ip_suffix`

This filters out infrastructure devices (router, APs, switches, servers) which typically have low IPs like `.1`, `.2`, `.10`, etc.

For example, with `min_ip_suffix: 100`, only devices with IPs ending in `.100` or higher will be exported to AdGuard Home.

## Notes

- SSL certificate verification is disabled for both the Deco and AdGuard Home connections, since both typically use self-signed certificates on local networks
- "Last seen" state for the stale cleanup is stored in `/data/deco_adguard_state.json`, which persists across add-on restarts/updates
- A device is considered to have a "randomized MAC" when the locally-administered bit of its first octet is set — the standard signal for iOS/Android per-network privacy MACs
- To force an immediate sync without waiting 6 hours, simply restart the add-on

## Requirements

- TP-Link Deco XE75 Pro (or compatible Deco model)
- AdGuard Home with API access enabled
- Local Management enabled on the Deco app (More → Local Management)
