# Changelog

## 0.1.3

- Limpieza de docs: reemplazado mi dominio personal real (`sbsoft.com.ar`)
  por `example.com` en README/DOCS/`run.sh`. Sin cambios de comportamiento.

## 0.1.2

- Fix RDP: `setpriv --reuid=1000` cambia uid/gid pero no `$HOME`, que quedaba
  en `/root` (heredado de cuando run.sh corría como root) — no escribible
  para uid 1000. FreeRDP necesita `$HOME` escribible para certs/caché durante
  el handshake (incluido NLA/CredSSP); sin eso, guacd tiraba "Security
  negotiation failed (wrong security type?)" aunque `security: nla` estuviera
  bien configurado en el provider/endpoint — no era un problema del servidor
  Windows. `run.sh` ahora exporta `HOME=/tmp/rac-home` (creado y con dueño
  uid 1000) antes de bajar privilegios.

## 0.1.1

- Fix `jq: error: Could not open file /data/options.json: Permission denied`:
  el Dockerfile bajaba a `USER 1000` antes del `CMD`, así que `run.sh`
  (incluida la lectura de `options.json`) corría como uid 1000 — pero ese
  archivo lo escribe el Supervisor como root, con permisos que un uid no-root
  no puede abrir. Ahora `run.sh` corre como root (como el add-on principal) y
  recién baja privilegios con `setpriv` para ejecutar `/rac`.

## 0.1.0

- Add-on inicial: outpost RAC de Authentik (`ghcr.io/goauthentik/rac:2026.5.6`).
  Cliente saliente sin estado, sin puertos expuestos — se conecta al add-on
  Authentik principal vía `authentik_host` + `authentik_token` (token
  generado por Authentik al crear el outpost RAC).
