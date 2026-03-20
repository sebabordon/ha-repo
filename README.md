# 🏠 sebabordon's Home Assistant Add-ons

A collection of Home Assistant add-ons built to scratch my own itches.
> Honestly conceived by me, technically executed by Claude.

---

## Add-ons


### 🔄 Deco → AdGuard Sync

Automatically syncs connected devices from your TP-Link Deco mesh network into AdGuard Home as persistent clients. Runs on startup and every 6 hours, skipping devices that are already registered.

[View add-on →](./deco-to-adguard)

---

### 🖨️ CUPS Print Server - NonWorking for Xerox 3020

Runs a CUPS print server inside Home Assistant, allowing you to share a USB printer over your local network. macOS devices discover it automatically via Bonjour/AirPrint — no manual configuration needed.

[View add-on →](./cups)

---

## Installation

In Home Assistant go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add:

```
https://github.com/sebabordon/ha-repo
```

Then find and install any add-on from the store.

---

## Credits

- CUPS add-on forked from [arest/cups-addon](https://github.com/arest/cups-addon) by Andrea Restello
- Built on top of [Home Assistant](https://www.home-assistant.io/) and [CUPS](https://www.cups.org/)
```
