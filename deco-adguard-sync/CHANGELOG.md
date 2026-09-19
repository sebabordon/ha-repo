# Changelog

## 1.5.0
- New `unfiltered_devices` option: like `parental_exempt`, but turns off every AdGuard block (parental + ad/tracker filtering + safe browsing) — meant for IoT/media devices (smart speakers, cameras, smart plugs, streaming boxes) that break when their own telemetry/API domains get blocked

## 1.4.0
- New `parental_exempt` option: list devices (by name or fixed MAC) that should have AdGuard's Parental Control turned off, while keeping ad-blocking and safe browsing on. Re-applied on every sync so it survives IP changes and renames, same as the rest of the sync

## 1.3.1
- A device with an ambiguous/generic Deco hostname is no longer dropped outright when it has its own fixed (non-randomized) MAC: it's still created, just under a disambiguated name (`H110-79f4` instead of a colliding `H110`), since the MAC alone is enough to confirm a real, distinct identity. Only devices with an ambiguous name *and* no usable MAC are skipped

## 1.3.0
- Fixed data corruption: devices with a generic/default hostname reported by more than one physical device (`wlan0`, `lwip0`, `dot`, AdGuard's own `none-N` placeholders, or any name Deco reports for 2+ devices in the same run) are no longer matched/merged by name — this was gluing unrelated MACs onto a single AdGuard client and flipping its IP on every run. These devices are now only touched via a real MAC match; otherwise they're skipped (new "omitidos (nombre ambiguo)" counter)
- Fixed the resulting `400 another client uses the same IP` flood: when a device's IP is being assigned to a client, any other AdGuard client still holding that IP is now found and released first (and deleted if that was its only id) — this is what "remove the old IP" actually needs on a live instance, not just editing the target client
- Stopped accumulating stale MAC ids on update: old IP/MAC ids are now replaced, not merged, when a device's identity is confirmed

## 1.2.1
- Fixed `400 invalid tag: "deco-sync"` on every add/update: AdGuard Home only accepts a fixed set of predefined tags (device type / OS), not arbitrary strings. Dropped the custom tag entirely — the stale cleanup was already based on `network_cidr`, not the tag, so this only removes dead code and the broken API calls

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
