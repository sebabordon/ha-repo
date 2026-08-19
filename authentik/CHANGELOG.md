# Changelog

## 0.2.2

- Bump automático de Authentik 2026.5.6 → 2026.8.0. Ver [release notes](https://docs.goauthentik.io/releases/2026.8/) antes de aplicar el update desde Home Assistant.


## 0.2.1

- Limpieza de docs: los ejemplos usaban mi dominio personal real como
  ilustración — reemplazado por el placeholder genérico `example.com` en
  README/DOCS/CHANGELOG/`run.sh` (mensajes de error). Sin cambios de
  comportamiento.

## 0.2.0

- Soporte multi-dominio para CSRF: nueva opción `additional_domains`
  (lista separada por coma, ej `apps.example.com`) para dominios extra
  que hablan con Authentik además de `authentik_host` — típico en setups de
  forward-auth con NPM donde las apps protegidas viven en otro dominio.
- `run.sh` genera `/data/user_settings.py` en cada arranque con
  `CSRF_TRUSTED_ORIGINS = [...]` a partir de `authentik_host` +
  `additional_domains`. Aprovecha que Authentik importa ese archivo solo
  (`data.user_settings`, ver `authentik/root/settings.py` y
  [goauthentik/authentik#4209](https://github.com/goauthentik/authentik/issues/4209)) —
  sin esto, loguearse desde un dominio distinto a `authentik_host` tira 403
  CSRF. Soporta wildcards estilo Django (`*.example.com`).

## 0.1.4

- Suma `icon.png` (128×128) y `logo.png` (512×512) con el logo oficial de
  Authentik (avatar de la org `goauthentik` en GitHub), para que se vea
  correctamente en el store de add-ons y en la página de info del add-on.

## 0.1.3

- Fix crash al arrancar Authentik (`provided string was not \`true\` or
  \`false\``): el helper `cfg()` leía las opciones con `jq '.campo // empty'`,
  y en jq `//` trata `false` igual que `null` ("vacío"). Como
  `error_reporting` es booleano y su default es `false`, se exportaba
  `AUTHENTIK_ERROR_REPORTING__ENABLED=""` en vez de `"false"`, y el binario
  Rust de Authentik rechaza cualquier valor que no sea exactamente `true`/
  `false`. `cfg()` ahora usa `.[$k] as $v | if $v == null then "" else $v end`,
  que no colapsa `false`/`0`/`""` como si faltaran.

## 0.1.2

- Fix arranque: `pg_ctl -l` escribía el log en `/data/postgres.log`, pero
  `/data` es de root y solo `/data/postgres` quedó con permisos para el uid
  1000 (con el que corre Postgres). `pg_ctl` fallaba con "Permission denied"
  al crear ese archivo. Ahora el log va dentro de `/data/postgres/`.

## 0.1.1

- Fix build: el Dockerfile fallaba en el paso de invertir los symlinks de
  `/media`/`/certs` (`exit code: 1`). La imagen base ya trae `/data/media`
  como symlink hacia `/media`; había que borrar ese symlink viejo antes del
  `mkdir -p /data/media`, si no `mkdir` se chocaba con el symlink roto
  (`/media` ya borrado) y fallaba.

## 0.1.0

- Add-on inicial: Authentik (`ghcr.io/goauthentik/server:2026.5.6`) con PostgreSQL
  embebido (sin Redis, ya no es dependencia desde Authentik 2025.10), corriendo
  en modo `allinone` (server + worker en un solo proceso).
- Persistencia en `/data`: cluster de Postgres, `secret_key`, `postgres_password`,
  media y certs subidos desde la UI de Authentik.
- Configuración vía UI: `authentik_host`, `bootstrap_email`/`bootstrap_password`,
  `cookie_domain`, `trusted_proxy_cidrs`, `log_level`, `error_reporting`, SMTP opcional.
- Documentación de integración como forward-auth con Nginx Proxy Manager en `DOCS.md`.
