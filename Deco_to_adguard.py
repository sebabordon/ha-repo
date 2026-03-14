#!/usr/bin/env python3
"""
deco_to_adguard.py
==================
1. Obtiene los dispositivos conectados al TP-Link Deco XE75 Pro
   (filtrando los que tengan IP >= 10.0.2.100)
2. Guarda el resultado en un YAML compatible con AdGuard Home
3. Sube los clientes nuevos directamente a AdGuard Home via API
   (los que ya existen se saltean)

Dependencias:
    pip install tplinkrouterc6u pyyaml requests

Uso basico (pide contraseñas interactivamente):
    python deco_to_adguard.py

Con argumentos:
    python deco_to_adguard.py \
        --deco-host  https://10.0.2.1 \
        --deco-pass  'TuContrasena' \
        --agh-host   https://10.0.2.232:3002 \
        --agh-user   admin \
        --agh-pass   'TuContrasena' \
        --output     clientes_adguard.yaml \
        --dry-run
"""

import argparse
import getpass
import ipaddress
import re
import sys

import requests
import yaml

try:
    from tplinkrouterc6u import TPLinkDecoClient
except ImportError:
    print("[ERROR] Falta la libreria tplinkrouterc6u.")
    print("        Instalala con:  pip install tplinkrouterc6u")
    sys.exit(1)

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DECO_HOST_DEFAULT = "https://10.0.2.1"
AGH_HOST_DEFAULT  = "https://10.0.2.232:3002"
AGH_USER_DEFAULT  = "admin"
OUTPUT_DEFAULT    = "clientes_adguard.yaml"
MIN_IP_SUFFIX     = 100  # override via --min-ip

def normalize_mac(mac: str) -> str:
    digits = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(digits) != 12:
        raise ValueError(f"MAC invalida: {mac!r}")
    return ":".join(digits[i:i+2].lower() for i in range(0, 12, 2))

def sanitize_name(name: str) -> str:
    name = name.strip()
    return name if name else "Sin nombre"

def build_agh_client(name: str, mac: str, ip: str) -> dict:
    ids = []
    if ip:
        ids.append(ip)
    if mac:
        try:
            ids.append(normalize_mac(mac))
        except ValueError:
            pass
    if not ids:
        raise ValueError(f"'{name}' no tiene IP ni MAC valida.")
    return {
        "name": sanitize_name(name),
        "ids": ids,
        "use_global_settings": True,
        "filtering_enabled": False,
        "parental_enabled": False,
        "safebrowsing_enabled": False,
        "use_global_blocked_services": True,
        "blocked_services": [],
        "upstreams": [],
        "tags": [],
    }

def fetch_devices(host: str, password: str) -> list[dict]:
    url = host if host.startswith("http") else f"https://{host}"
    print(f"\n[Deco] Conectando a {url} ...")
    try:
        client = TPLinkDecoClient(url, password, verify_ssl=False)
        client.authorize()
    except Exception as exc:
        print(f"[ERROR] No se pudo autenticar en el Deco: {exc}")
        sys.exit(1)
    print("[Deco] Autenticacion OK. Obteniendo dispositivos ...")
    try:
        status = client.get_status()
    except Exception as exc:
        print(f"[ERROR] No se pudo obtener el estado: {exc}")
        sys.exit(1)
    threshold = int(ipaddress.ip_address(f"10.0.2.{MIN_IP_SUFFIX}"))
    all_devices = status.devices
    print(f"[Deco] Total dispositivos: {len(all_devices)}")
    devices = []
    skipped = 0
    for d in all_devices:
        ip   = getattr(d, "ipaddr",   "") or ""
        mac  = getattr(d, "macaddr",  "") or ""
        name = getattr(d, "hostname", "") or ""
        try:
            if int(ipaddress.ip_address(ip)) < threshold:
                skipped += 1
                continue
        except ValueError:
            skipped += 1
            continue
        devices.append({"name": name, "mac": mac, "ip": ip})
    print(f"[Deco] Exportados (IP >= 10.0.2.{MIN_IP_SUFFIX}): {len(devices)}")
    print(f"[Deco] Omitidos   (IP <  10.0.2.{MIN_IP_SUFFIX} o sin IP): {skipped}")
    return devices

def build_yaml(devices: list[dict]) -> tuple[str, list[dict]]:
    agh_clients = []
    for dev in devices:
        name = dev["name"] or dev["mac"] or "Desconocido"
        try:
            agh_clients.append(build_agh_client(name, dev["mac"], dev["ip"]))
        except ValueError as exc:
            print(f"[WARN] Saltando '{name}': {exc}")
    yaml_str = yaml.dump(
        {"clients": agh_clients},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )
    return yaml_str, agh_clients

def upload_to_adguard(
    agh_clients: list[dict],
    agh_host: str,
    agh_user: str,
    agh_pass: str,
    dry_run: bool = False,
) -> None:
    url = agh_host.rstrip("/")
    print(f"\n[AdGuard] Conectando a {url} ...")
    session = requests.Session()
    session.auth = (agh_user, agh_pass)
    session.verify = False
    try:
        resp = session.get(f"{url}/control/clients")
        resp.raise_for_status()
    except Exception as exc:
        print(f"[ERROR] No se pudo conectar a AdGuard Home: {exc}")
        sys.exit(1)
    existing_clients = resp.json().get("clients", [])
    existing_names = {c["name"] for c in existing_clients}
    # Índice de todas las IPs y MACs ya registradas -> nombre del cliente existente
    existing_ids: dict[str, str] = {}
    for c in existing_clients:
        for id_ in c.get("ids", []):
            existing_ids[id_.lower()] = c["name"]
    print(f"[AdGuard] Clientes existentes: {len(existing_names)}")
    added = skipped = failed = 0
    for client in agh_clients:
        # Buscar conflicto por nombre exacto o por IP/MAC ya registrada
        conflict_name = None
        if client["name"] in existing_names:
            conflict_name = client["name"]
        else:
            for id_ in client["ids"]:
                if id_.lower() in existing_ids:
                    conflict_name = existing_ids[id_.lower()]
                    break
        if conflict_name:
            if conflict_name == client["name"]:
                print(f"  [=] Ya existe:  {client['name']}")
            else:
                print(f"  [=] Ya existe con otro nombre: '{conflict_name}' tiene {client['ids']}")
            skipped += 1
            continue
        if dry_run:
            print(f"  [~] Dry-run:    {client['name']}  {client['ids']}")
            added += 1
            continue
        payload = {
            "name": client["name"],
            "ids":  client["ids"],
            "use_global_settings":         True,
            "filtering_enabled":           False,
            "parental_enabled":            False,
            "safebrowsing_enabled":        False,
            "use_global_blocked_services": True,
            "blocked_services":            [],
            "upstreams":                   [],
            "tags":                        [],
        }
        r = session.post(f"{url}/control/clients/add", json=payload)
        if r.status_code == 200:
            print(f"  [+] Agregado:   {client['name']}  {client['ids']}")
            added += 1
        else:
            print(f"  [!] Error:      {client['name']} -> {r.status_code} {r.text}")
            failed += 1
    print(f"\n[AdGuard] Resumen: {added} agregados, {skipped} ya existian, {failed} errores.")
    if dry_run:
        print("[AdGuard] Modo dry-run: no se realizaron cambios reales.")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza clientes del Deco XE75 Pro -> AdGuard Home.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--deco-host", default=DECO_HOST_DEFAULT)
    parser.add_argument("--deco-pass", default=None)
    parser.add_argument("--agh-host",  default=AGH_HOST_DEFAULT)
    parser.add_argument("--agh-user",  default=AGH_USER_DEFAULT)
    parser.add_argument("--agh-pass",  default=None)
    parser.add_argument("--output",    default=OUTPUT_DEFAULT)
    parser.add_argument("--min-ip", dest="min_ip", type=int, default=None,
                        help="Ultimo octeto minimo de IP a exportar (default: 100)")
    parser.add_argument("--no-upload", action="store_true",
                        help="Solo genera el YAML, no sube a AdGuard Home")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Muestra que se haria sin hacer cambios reales")
    parser.add_argument("--print",     dest="print_yaml", action="store_true",
                        help="Imprime el YAML en consola")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    # Permitir override del MIN_IP_SUFFIX via argumento
    global MIN_IP_SUFFIX
    if args.min_ip is not None:
        MIN_IP_SUFFIX = args.min_ip

    deco_pass = args.deco_pass or getpass.getpass("[?] Contrasena del Deco: ")
    agh_pass  = None
    if not args.no_upload:
        agh_pass = args.agh_pass or getpass.getpass("[?] Contrasena de AdGuard Home: ")
    devices = fetch_devices(args.deco_host, deco_pass)
    if not devices:
        print("[!] No se encontraron dispositivos. Saliendo.")
        sys.exit(0)
    yaml_str, agh_clients = build_yaml(devices)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("# Generado automaticamente por deco_to_adguard.py\n\n")
        f.write(yaml_str)
    print(f"\n[OK] YAML guardado: {args.output}  ({len(agh_clients)} clientes)")
    if args.print_yaml:
        print("\n" + "-" * 60)
        print(yaml_str)
        print("-" * 60)
    if not args.no_upload:
        upload_to_adguard(
            agh_clients, args.agh_host, args.agh_user, agh_pass,
            dry_run=args.dry_run,
        )

if __name__ == "__main__":
    main()
