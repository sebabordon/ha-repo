# Homeassistant Apps by me (actually Claude, but with my ideas)

# Deco → AdGuard Sync — Home Assistant Add-on

Automatically syncs connected devices from your **TP-Link Deco XE75 Pro** into **AdGuard Home** as persistent clients, using both devices' local APIs.

## How it works

1. Connects to the Deco and fetches all currently connected devices
2. Filters out infrastructure devices by minimum IP (configurable)
3. Compares against existing AdGuard Home clients — **Deco data takes precedence**:
   - If a device's fixed (non-randomized) MAC matches an existing AdGuard client, that client is updated: name and IP are synced, the old IP is removed.
   - Otherwise, if the device's name matches an existing client, its IP is updated (old IP removed). This is the primary match for phones, since iOS/Android randomize their MAC per network.
   - Devices with a generic/default hostname — `wlan0`, `lwip0`, `dot`, AdGuard's own `none-N` placeholders, or any name Deco reports for more than one device in the same run — are never matched or renamed by that name, since it isn't a reliable identity (it previously caused unrelated devices to get merged into one corrupted client). If such a device has its own fixed MAC it's still created, just under a disambiguated name (e.g. `H110-79f4`); only devices with both an ambiguous name and no usable MAC are skipped entirely.
   - If nothing matches, a new client is created — unless the device only has a randomized MAC, in which case it's skipped to avoid cluttering AdGuard with throwaway entries (configurable).
   - Whenever a device's IP is (re)assigned to a client, if another AdGuard client still holds that IP it's released from it first (and that other client is deleted if it had no other id) — this is what actually prevents duplicate-IP conflicts as DHCP leases churn.
4. **Any** AdGuard client whose IP/CIDR falls inside `network_cidr` — not just the ones this add-on created — that stops appearing on the Deco for more than `stale_days` is removed from AdGuard. Clients outside that network, or identified only by MAC/ClientID (no way to place them on a network), are never touched.
5. All new/updated clients keep global settings and global blocked services enabled
6. Every device listed in `parental_exempt` (by name or MAC) has Parental Control turned off on that client — ad-blocking and safe browsing stay on. Re-applied every sync, so it keeps working across IP/name changes as long as the device is still identifiable.

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
| `stale_days` | Days a client can go unseen before it's removed from AdGuard | `7`, `0` disables cleanup |
| `exclude_random_mac` | Skip creating new AdGuard clients for devices with a randomized MAC | `true` |
| `network_cidr` | Network this sync manages; stale cleanup only ever touches clients inside it | `10.0.2.0/23` |
| `parental_exempt` | Devices with Parental Control forced off (ad-block/safe browsing stay on), one name or MAC per entry | `AirdeSebastian`, `Apple TV Living`, `aa:bb:cc:dd:ee:ff` |

### About `min_ip_suffix`

This filters out infrastructure devices (router, APs, switches, servers) which typically have low IPs like `.1`, `.2`, `.10`, etc.

For example, with `min_ip_suffix: 100`, only devices with IPs ending in `.100` or higher will be exported to AdGuard Home.

## Notes

- **`parental_exempt` matching**: each entry must match either the device's fixed MAC, or the exact name the client ends up with in AdGuard after sync (for devices with an ambiguous/generic Deco hostname, that's the disambiguated name, e.g. `H110-79f4` — check the AdGuard client list once if unsure). Matching by MAC is more robust since it doesn't depend on naming. `filtering_enabled` and `safebrowsing_enabled` are set to `true` explicitly for these devices and don't follow later changes to AdGuard's global toggles — only `parental_enabled` is what this option controls.
- **Stale cleanup is aggressive within `network_cidr`**: any AdGuard client in that range not reported by the Deco for `stale_days` gets deleted, including ones you created manually in the AdGuard UI. If you keep static AdGuard clients for devices the Deco doesn't see (e.g. a device connected to a different AP, or identified only by a CIDR you assigned), either give them an IP outside `network_cidr` or lower `stale_days`/set it to `0`.
- The first time a client is seen missing, its "last seen" is just recorded (not deleted yet) — real deletions only happen after `stale_days` of confirmed absence, so upgrading to this version doesn't wipe anything on the first run.
- SSL certificate verification is disabled for both the Deco and AdGuard Home connections, since both typically use self-signed certificates on local networks
- "Last seen" state for the stale cleanup is stored in `/data/deco_adguard_state.json`, which persists across add-on restarts/updates
- A device is considered to have a "randomized MAC" when the locally-administered bit of its first octet is set — the standard signal for iOS/Android per-network privacy MACs
- To force an immediate sync without waiting 6 hours, simply restart the add-on

## Requirements

- TP-Link Deco XE75 Pro (or compatible Deco model)
- AdGuard Home with API access enabled
- Local Management enabled on the Deco app (More → Local Management)
