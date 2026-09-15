#!/usr/bin/env python3
"""
deco_to_adguard.py
==================
1. Obtiene los dispositivos conectados al TP-Link Deco XE75 Pro
   (filtrando los que tengan IP >= 10.0.2.100)
2. Guarda el resultado en un YAML compatible con AdGuard Home
3. Sincroniza los clientes con AdGuard Home via API:
   - Los dispositivos del Deco tienen precedencia: si un cliente ya
     existe (por MAC fija o por nombre), se actualiza su IP quitando
     la anterior.
   - Los dispositivos nuevos con MAC aleatoria (randomizacion de
     privacidad de iOS/Android) no se crean como clientes nuevos,
     salvo que ya existiera un cliente con ese nombre.
   - Los clientes de AdGuard dentro de la red gestionada (network_cidr)
     que dejan de verse en el Deco por mas de N dias se borran.

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
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

DECO_HOST_DEFAULT  = "https://10.0.2.1"
AGH_HOST_DEFAULT   = "https://10.0.2.232:3002"
AGH_USER_DEFAULT   = "admin"
OUTPUT_DEFAULT     = "clientes_adguard.yaml"
STATE_FILE_DEFAULT = "/data/deco_adguard_state.json"
STALE_DAYS_DEFAULT = 7
MIN_IP_SUFFIX      = 100  # override via --min-ip
NETWORK_DEFAULT    = "10.0.2.0/23"

def normalize_mac(mac: str) -> str:
    digits = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(digits) != 12:
        raise ValueError(f"MAC invalida: {mac!r}")
    return ":".join(digits[i:i+2].lower() for i in range(0, 12, 2))

def is_locally_administered_mac(mac_norm: str) -> bool:
    """Detecta MACs aleatorias (privacidad de red de iOS/Android):
    el bit 'locally administered' (0x02) del primer octeto esta seteado."""
    first_octet = int(mac_norm.split(":")[0], 16)
    return bool(first_octet & 0x02)

def is_ip_id(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False

def client_in_network(client: dict, network: ipaddress.IPv4Network) -> bool:
    """True si alguno de los ids del cliente (IP o CIDR) cae dentro de la red gestionada.
    Clientes identificados solo por MAC o ClientID no se pueden ubicar en una red,
    asi que se consideran fuera (protegidos)."""
    for id_ in client.get("ids", []):
        try:
            if "/" in id_:
                if ipaddress.ip_network(id_, strict=False).overlaps(network):
                    return True
            elif ipaddress.ip_address(id_) in network:
                return True
        except ValueError:
            continue
    return False

def sanitize_name(name: str) -> str:
    name = name.strip()
    return name if name else "Sin nombre"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] No se pudo leer el estado ({path}): {exc}. Se empieza de cero.")
        return {}

def save_state(path: str, state: dict) -> None:
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"[WARN] No se pudo guardar el estado ({path}): {exc}")

def build_agh_client(name: str, mac: str, ip: str) -> dict:
    ids = []
    if ip:
        ids.append(ip)
    if mac:
        ids.append(mac)
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

def build_yaml(devices: list[dict]) -> str:
    agh_clients = []
    for dev in devices:
        name = dev["name"] or dev["mac"] or "Desconocido"
        mac_norm = None
        if dev["mac"]:
            try:
                mac_norm = normalize_mac(dev["mac"])
            except ValueError:
                mac_norm = None
        if mac_norm and is_locally_administered_mac(mac_norm):
            mac_norm = None  # no se usa como id, es aleatoria
        try:
            agh_clients.append(build_agh_client(name, mac_norm or "", dev["ip"]))
        except ValueError as exc:
            print(f"[WARN] Saltando '{name}': {exc}")
    return yaml.dump(
        {"clients": agh_clients},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        indent=2,
    )

def sync_to_adguard(
    devices: list[dict],
    agh_host: str,
    agh_user: str,
    agh_pass: str,
    state: dict,
    stale_days: int = STALE_DAYS_DEFAULT,
    exclude_random_mac: bool = True,
    network: str = NETWORK_DEFAULT,
    dry_run: bool = False,
) -> None:
    managed_network = ipaddress.ip_network(network, strict=False)
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
    existing_by_name = {c["name"]: c for c in existing_clients}
    existing_by_id: dict[str, dict] = {}
    for c in existing_clients:
        for id_ in c.get("ids", []):
            existing_by_id[id_.lower()] = c
    print(f"[AdGuard] Clientes existentes: {len(existing_clients)}")

    added = updated = unchanged = skipped_random = failed = 0
    current_names: set[str] = set()
    now = now_iso()

    for dev in devices:
        name = sanitize_name(dev["name"] or dev["mac"] or "Desconocido")
        ip = dev["ip"]
        mac_norm = None
        if dev["mac"]:
            try:
                mac_norm = normalize_mac(dev["mac"])
            except ValueError:
                mac_norm = None
        is_random = bool(mac_norm) and is_locally_administered_mac(mac_norm)
        usable_mac = mac_norm if (mac_norm and not is_random) else None

        if not ip and not usable_mac:
            print(f"[WARN] Saltando '{name}': no tiene IP ni MAC utilizable.")
            continue

        matched, match_reason = None, None
        if usable_mac and usable_mac in existing_by_id:
            matched, match_reason = existing_by_id[usable_mac], "mac"
        elif name in existing_by_name:
            matched, match_reason = existing_by_name[name], "name"

        if matched:
            old_ids = matched.get("ids", [])
            new_ids = []
            if ip:
                new_ids.append(ip)
            for id_ in old_ids:
                if not is_ip_id(id_) and id_ not in new_ids:
                    new_ids.append(id_)
            if usable_mac and usable_mac not in new_ids:
                new_ids.append(usable_mac)
            # Si matcheo por MAC y el Deco reporta otro nombre, el Deco manda.
            new_name = name if match_reason == "mac" else matched["name"]
            current_names.add(new_name)

            changed = set(new_ids) != set(old_ids) or new_name != matched["name"]
            if changed:
                payload = dict(matched)
                payload["ids"] = new_ids
                payload["name"] = new_name
                if dry_run:
                    print(f"  [~] Dry-run update: '{matched['name']}' -> '{new_name}' {new_ids}")
                    updated += 1
                else:
                    r = session.post(f"{url}/control/clients/update",
                                      json={"name": matched["name"], "data": payload})
                    if r.status_code == 200:
                        print(f"  [*] Actualizado: '{matched['name']}' -> '{new_name}' {new_ids}")
                        updated += 1
                    else:
                        print(f"  [!] Error actualizando '{matched['name']}': {r.status_code} {r.text}")
                        failed += 1
            else:
                unchanged += 1
            state[new_name] = {"last_seen": now, "ip": ip, "mac": usable_mac}
            continue

        # Sin match: cliente nuevo
        if is_random and exclude_random_mac:
            skipped_random += 1
            print(f"  [-] MAC aleatoria, no se crea cliente nuevo: '{name}' ({dev['mac']})")
            continue

        current_names.add(name)
        try:
            payload = build_agh_client(name, usable_mac or "", ip)
        except ValueError as exc:
            print(f"[WARN] Saltando '{name}': {exc}")
            continue
        if dry_run:
            print(f"  [~] Dry-run add: {payload['name']} {payload['ids']}")
            added += 1
        else:
            r = session.post(f"{url}/control/clients/add", json=payload)
            if r.status_code == 200:
                print(f"  [+] Agregado: {payload['name']} {payload['ids']}")
                added += 1
            else:
                print(f"  [!] Error agregando '{payload['name']}': {r.status_code} {r.text}")
                failed += 1
                continue
        state[name] = {"last_seen": now, "ip": ip, "mac": usable_mac}

    deleted = 0
    if stale_days > 0:
        now_dt = datetime.now(timezone.utc)
        for c in existing_clients:
            if c["name"] in current_names:
                continue
            if not client_in_network(c, managed_network):
                continue  # fuera de la red gestionada, se protege
            last_seen = state.get(c["name"], {}).get("last_seen")
            if last_seen is None:
                state[c["name"]] = {"last_seen": now}
                print(f"  [?] '{c['name']}' (dentro de la red) sin historial, se registra ahora "
                      f"(se evaluara en {stale_days} dias si sigue ausente).")
                continue
            age = now_dt - datetime.fromisoformat(last_seen)
            if age >= timedelta(days=stale_days):
                if dry_run:
                    print(f"  [~] Dry-run delete: '{c['name']}' (sin verse hace {age.days}d)")
                else:
                    r = session.post(f"{url}/control/clients/delete", json={"name": c["name"]})
                    if r.status_code == 200:
                        print(f"  [x] Borrado: '{c['name']}' (sin verse hace {age.days}d)")
                    else:
                        print(f"  [!] Error borrando '{c['name']}': {r.status_code} {r.text}")
                        continue
                state.pop(c["name"], None)
                deleted += 1
            else:
                remaining = stale_days - age.days
                print(f"  [.] '{c['name']}' ausente, en periodo de gracia ({remaining}d restantes).")

    print(f"\n[AdGuard] Resumen: {added} agregados, {updated} actualizados, "
          f"{unchanged} sin cambios, {skipped_random} omitidos (MAC aleatoria), "
          f"{deleted} borrados (stale), {failed} errores.")
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
    parser.add_argument("--state-file", default=STATE_FILE_DEFAULT,
                        help="Archivo donde se guarda la ultima vez visto de cada dispositivo")
    parser.add_argument("--stale-days", type=int, default=STALE_DAYS_DEFAULT,
                        help="Dias sin verse en el Deco antes de borrar el cliente en AdGuard (0 desactiva)")
    parser.add_argument("--network", default=NETWORK_DEFAULT,
                        help="Red gestionada (CIDR). Clientes de AdGuard fuera de esta red nunca se borran por stale")
    parser.add_argument("--min-ip", dest="min_ip", type=int, default=None,
                        help="Ultimo octeto minimo de IP a exportar (default: 100)")
    parser.add_argument("--no-exclude-random-mac", dest="exclude_random_mac",
                        action="store_false",
                        help="Crear tambien clientes nuevos para dispositivos con MAC aleatoria")
    parser.add_argument("--no-upload", action="store_true",
                        help="Solo genera el YAML, no sincroniza con AdGuard")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Muestra que se haria sin hacer cambios reales")
    parser.add_argument("--print",     dest="print_yaml", action="store_true",
                        help="Imprime el YAML en consola")
    parser.set_defaults(exclude_random_mac=True)
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
    yaml_str = build_yaml(devices)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("# Generado automaticamente por deco_to_adguard.py\n\n")
        f.write(yaml_str)
    print(f"\n[OK] YAML guardado: {args.output}")
    if args.print_yaml:
        print("\n" + "-" * 60)
        print(yaml_str)
        print("-" * 60)
    if not args.no_upload:
        state = load_state(args.state_file)
        sync_to_adguard(
            devices, args.agh_host, args.agh_user, agh_pass,
            state=state,
            stale_days=args.stale_days,
            exclude_random_mac=args.exclude_random_mac,
            network=args.network,
            dry_run=args.dry_run,
        )
        if not args.dry_run:
            save_state(args.state_file, state)

if __name__ == "__main__":
    main()
