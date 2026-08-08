# Changelog

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
