# Changelog

## 0.1.0

- Add-on inicial: Authentik (`ghcr.io/goauthentik/server:2026.5.6`) con PostgreSQL
  embebido (sin Redis, ya no es dependencia desde Authentik 2025.10), corriendo
  en modo `allinone` (server + worker en un solo proceso).
- Persistencia en `/data`: cluster de Postgres, `secret_key`, `postgres_password`,
  media y certs subidos desde la UI de Authentik.
- Configuración vía UI: `authentik_host`, `bootstrap_email`/`bootstrap_password`,
  `cookie_domain`, `trusted_proxy_cidrs`, `log_level`, `error_reporting`, SMTP opcional.
- Documentación de integración como forward-auth con Nginx Proxy Manager en `DOCS.md`.
