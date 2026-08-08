# Changelog

## 0.1.0

- Add-on inicial: outpost RAC de Authentik (`ghcr.io/goauthentik/rac:2026.5.6`).
  Cliente saliente sin estado, sin puertos expuestos — se conecta al add-on
  Authentik principal vía `authentik_host` + `authentik_token` (token
  generado por Authentik al crear el outpost RAC).
