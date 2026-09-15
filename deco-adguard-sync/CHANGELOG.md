# Changelog

## 1.2.0
- Added `build.yaml` (missing `build_from` per arch) — fixes Docker build failure `exit code 1` on 1.1.0 caused by an unset `BUILD_FROM`
- Stale cleanup is now aggressive: it removes **any** AdGuard client whose IP/CIDR falls inside `network_cidr` (default `10.0.2.0/23`) and hasn't been seen on the Deco for `stale_days`, not only clients this add-on created. Clients outside that network, or identified only by MAC/ClientID, are never touched
- New `network_cidr` option to control the managed range

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
