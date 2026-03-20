# Non Working CUPS for Xerox 3020. 

```markdown
# CUPS Print Server for Home Assistant

A Home Assistant add-on that runs a CUPS (Common Unix Printing System) print server, allowing you to share USB printers over your local network. Includes a web administration interface accessible at `http://<your-ha-ip>:631` and supports AirPrint for automatic discovery on macOS and iOS devices.

## How it works

When the add-on starts, it launches a CUPS daemon inside a container with access to the host's USB devices. CUPS acts as a print server — it receives print jobs from any device on your network, processes them through the appropriate driver and filter pipeline, and forwards the output to the physical printer over USB. macOS devices discover the printer automatically via Bonjour/mDNS without any manual configuration needed.

The add-on stores all printer configuration, PPD files, and logs in `/data/cups` so settings persist across restarts and updates.

## Note on USB printer drivers

GDI/host-based printers like the Xerox Phaser 3020 require proprietary ARM binaries from the manufacturer. On aarch64 hosts these binaries may have compatibility limitations due to the 32-bit ARM requirement of the official Xerox ULD driver.

## Credits

Forked from [arest/cups-addon](https://github.com/arest/cups-addon) by Andrea Restello, built on top of [CUPS](https://www.cups.org/) and [Home Assistant](https://www.home-assistant.io/).
```