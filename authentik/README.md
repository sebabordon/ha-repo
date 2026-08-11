# Home Assistant add-on: Authentik

[Authentik](https://goauthentik.io) (Identity Provider / SSO self-hosted) empaquetado
como add-on de Home Assistant, con PostgreSQL embebido — no necesita ningún
otro add-on ni servicio externo para arrancar.

Pensado para correr como **frontend de autenticación delante de Nginx Proxy
Manager** (también add-on): NPM sigue siendo tu reverse proxy; Authentik le
agrega login/SSO antes de dejar pasar el tráfico a cada sitio proxeado.

- Imagen base: `ghcr.io/goauthentik/server` (build oficial de Authentik Security).
- Sin Redis: desde Authentik 2025.10, caché/tasks/websockets corren sobre Postgres.
- Server + worker en un solo proceso (`ak allinone`).
- Postgres vive en `/data/postgres`, persistido junto al resto de la config del add-on.

Ver [DOCS.md](./DOCS.md) para la configuración completa y cómo conectarlo con
Nginx Proxy Manager (forward-auth via el outpost embebido).

## Instalación

1. En Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, agregá:
   ```
   https://github.com/sebabordon/ha-repo
   ```
2. Instalá el add-on **Authentik**.
3. En la pestaña Configuration, completá al menos:
   - `authentik_host`: el dominio público, ej `auth.example.com`.
   - `bootstrap_password`: contraseña inicial del usuario `akadmin`.
4. Arrancá el add-on. El primer arranque tarda más (inicializa Postgres + migraciones).
5. Puerto por defecto: `9000` (HTTP, para apuntar desde Nginx Proxy Manager) y `9443` (HTTPS interno, self-signed).

Detalles de la integración con NPM, variables opcionales (SMTP, cookie
domain, trusted proxies) y troubleshooting: [DOCS.md](./DOCS.md).
