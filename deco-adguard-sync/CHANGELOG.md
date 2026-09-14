# Changelog

## 1.1.0
- Deco now takes precedence over AdGuard Home: existing clients (matched by fixed MAC, or by name when the MAC is a randomized privacy address) get their IP updated and the old IP removed
- New devices with a randomized MAC are no longer added as new AdGuard clients (configurable via `exclude_random_mac`)
- Clients managed by this add-on (tagged `deco-sync`) that stop appearing on the Deco for more than `stale_days` (default 7) are automatically removed from AdGuard Home; manually created clients are never touched
- Added persistent "last seen" state file (`/data/deco_adguard_state.json`)

## 1.0.4
- Updated password fields properly
  
## 1.0.2
- Translated add-on configuration and documentation to English
- Added detailed descriptions for all configuration options

## 1.0.0
- Initial release
- Syncs TP-Link Deco XE75 Pro clients to AdGuard Home every 6 hours
- Filters devices by minimum IP suffix
- Skips existing clients matched by name or IP
