# Changelog

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
