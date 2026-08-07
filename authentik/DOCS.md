# Authentik — Documentación

Add-on que corre [Authentik](https://goauthentik.io) (Identity Provider / SSO
self-hosted) en un solo contenedor: incluye su propio PostgreSQL embebido, no
necesita Redis (Authentik lo eliminó como dependencia desde la versión
2025.10) y arranca en modo `allinone` (server + worker en un solo proceso).

Pensado para usarse como **frontend de autenticación delante de Nginx Proxy
Manager** (también instalado como add-on): NPM sigue siendo el reverse proxy
que atiende tus dominios, y Authentik se encarga del login/SSO antes de dejar
pasar el tráfico a cada sitio.

---

## Configuración obligatoria

| Opción | Descripción |
|--------|-------------|
| `authentik_host` | Dominio público por el que vas a acceder a Authentik detrás de NPM. Ejemplo: `auth.sbsoft.com.ar`. |
| `bootstrap_password` | Contraseña inicial del usuario admin (`akadmin`). Solo se aplica en el primer arranque (cluster de Postgres vacío). |

## Configuración opcional

| Opción | Default | Descripción |
|--------|---------|-------------|
| `bootstrap_email` | `admin@example.com` | Email del usuario admin inicial (`akadmin`). |
| `additional_domains` | _(vacío)_ | Dominios adicionales, separados por coma, que también van a hablar con Authentik (ej: `apps.sbsoft.com.ar`) — típicamente los dominios de las apps protegidas por forward-auth vía NPM. Se usan para armar `CSRF_TRUSTED_ORIGINS` (ver más abajo); si no lo completás, solo `authentik_host` queda confiado y vas a ver errores 403 CSRF al loguearte desde otro dominio. Acepta wildcards estilo Django, ej `*.sbsoft.com.ar`. |
| `cookie_domain` | _(vacío)_ | Dominio para la cookie de sesión, ej `sbsoft.com.ar`, si querés SSO entre varios subdominios (`auth.sbsoft.com.ar`, `app1.sbsoft.com.ar`, etc). Si lo dejás vacío, la cookie queda atada solo al dominio exacto de `authentik_host`. |
| `trusted_proxy_cidrs` | `172.30.32.0/23` | CIDRs desde los que Authentik acepta headers `X-Forwarded-*` (necesario para que detecte bien el host/proto real detrás de NPM). `172.30.32.0/23` es la red interna default del Supervisor de HA; si tu instalación usa otra, ajustala (`docker network inspect hassio` desde el host, o Configuración → Sistema → Red en HA). |
| `log_level` | `info` | `debug`, `info`, `warning` o `error`. |
| `error_reporting` | `false` | Envío de errores/telemetría anónima a Authentik Security. Desactivado por defecto. |
| `smtp_host` / `smtp_port` / `smtp_username` / `smtp_password` / `smtp_use_tls` / `smtp_from` | _(vacío)_ | Server SMTP para invitaciones, reseteo de contraseña, notificaciones. Si dejás `smtp_host` vacío, Authentik funciona igual pero sin esos emails. |

---

## Primer arranque

1. Instalá y arrancá el add-on con `authentik_host` y `bootstrap_password` configurados.
2. La primera vez tarda más: inicializa Postgres y corre las migraciones de Authentik. Mirá el log del add-on hasta ver que el server queda arriba.
3. Entrá directamente a `http://<IP-de-HA>:9000/if/flow/initial-setup/` (o al puerto que hayas mapeado) para terminar el setup inicial, o logueate directo con `akadmin` / la contraseña que pusiste en `bootstrap_password`.
4. Si el bootstrap automático no tomó (pasa en algunos casos si el add-on se reinició a mitad del primer arranque), podés generar un link de recuperación desde una consola dentro del contenedor del add-on:
   ```
   ak create_recovery_key 10 akadmin
   ```

## Integrarlo con Nginx Proxy Manager

Authentik no reemplaza a NPM — NPM sigue siendo tu reverse proxy de dominios.
El patrón habitual es "forward-auth" con el outpost embebido de Authentik:

1. En Authentik, creá un **Proxy Provider** (modo *Forward auth (single
   application)* o *(domain level)* si querés protegé varios subdominios con
   un solo login) y una **Application** apuntando a ese provider.
2. Anotá la URL del outpost embebido, algo como
   `https://auth.sbsoft.com.ar/outpost.goauthentik.io/...`.
3. En NPM, en el *Proxy Host* del sitio que querés proteger, pestaña
   **Advanced**, agregá algo como:
   ```nginx
   location /outpost.goauthentik.io {
       proxy_pass              http://<IP-de-HA>:9000/outpost.goauthentik.io;
       proxy_set_header        Host $host;
       proxy_set_header        X-Original-URL $scheme://$http_host$request_uri;
       add_header               Set-Cookie $auth_cookie;
       auth_request_set         $auth_cookie $upstream_http_set_cookie;
       proxy_pass_request_body  off;
   }
   location / {
       auth_request             /outpost.goauthentik.io/auth/nginx;
       error_page               401 = @goauthentik_proxy_signin;
       auth_request_set         $auth_cookie $upstream_http_set_cookie;
       add_header               Set-Cookie $auth_cookie;
       auth_request_set         $authentik_username $upstream_http_x_authentik_username;
       proxy_set_header         X-authentik-username $authentik_username;
       # ... proxy_pass al sitio real ...
   }
   location @goauthentik_proxy_signin {
       internal;
       add_header  Set-Cookie $auth_cookie always;
       return 302  https://auth.sbsoft.com.ar/outpost.goauthentik.io/start?rd=$scheme://$http_host$request_uri;
   }
   ```
   (snippet base tomado de la [doc oficial de NGINX forward-auth de
   Authentik](https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth) —
   ajustá `<IP-de-HA>:9000` y `auth.sbsoft.com.ar` a tu entorno).
4. Para el propio dominio de Authentik (`auth.sbsoft.com.ar`), el *Proxy
   Host* en NPM simplemente apunta a `http://<IP-de-HA>:9000` sin
   forward-auth (necesitás poder llegar a Authentik sin estar ya
   autenticado).

### Multi-dominio (CSRF) — `additional_domains`

Si protegés apps que viven en un dominio distinto al de `authentik_host` (ej:
`auth.sbsoft.com.ar` para Authentik y `apps.sbsoft.com.ar` para las apps
protegidas por forward-auth), Authentik va a rechazar los POST/login con un
403 de CSRF apenas el flujo cruce de un dominio al otro — Django solo confía
en el dominio "propio" por default.

Authentik no expone esto como variable de entorno, pero sí soporta un archivo
`user_settings.py` que Django importa automáticamente en cada arranque (ver
[goauthentik/authentik#4209](https://github.com/goauthentik/authentik/issues/4209)
y `authentik/root/settings.py`, que hace
`_update_settings("data.user_settings")` — es decir, importa
`/data/user_settings.py` como módulo de settings). Este add-on genera ese
archivo solo, en cada arranque, con:

```python
CSRF_TRUSTED_ORIGINS = ["https://<authentik_host>", "https://<cada dominio de additional_domains>"]
```

Para el ejemplo de arriba, en `additional_domains` poné:

```
apps.sbsoft.com.ar
```

(no hace falta repetir `authentik_host`, ya se agrega solo). Podés poner
varios separados por coma, y también wildcards estilo Django
(`*.sbsoft.com.ar`) para cubrir cualquier subdominio sin listarlos todos.
El archivo se regenera en cada arranque a partir de la config del add-on —
si lo editás a mano dentro del contenedor, se pierde en el próximo restart.

## Limitaciones conocidas

- **Modo `allinone`**: server y worker corren en el mismo proceso. Es el modo
  que Authentik documenta para instalaciones chicas/single-container; no
  escala horizontalmente. Para un uso doméstico/homelab está pensado para
  esto.
- **Sin outposts vía Docker socket**: este add-on no monta
  `/var/run/docker.sock`, así que no vas a poder crear outposts
  "Docker"-managed desde la UI de Authentik. El outpost embebido (proxy
  forward-auth de arriba) no lo necesita.
- **PostgreSQL sin backup automático**: vive en `/data/postgres`, dentro del
  volumen persistente del add-on. Los backups de Home Assistant (Settings →
  System → Backups) lo incluyen si el add-on está incluido en el backup,
  pero no hay un mecanismo de dump/restore aparte.
