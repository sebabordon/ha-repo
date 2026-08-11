# Authentik RAC Outpost — Documentación

Add-on chico que corre el **outpost RAC** de Authentik (`ghcr.io/goauthentik/rac`,
trae [guacd](https://guacamole.apache.org/) adentro): acceso remoto vía
navegador a RDP, VNC y SSH, protegido detrás de Authentik.

RAC **no corre embebido** en el server principal de Authentik (a diferencia
del outpost de proxy/forward-auth, que sí). Es un componente separado que se
conecta hacia afuera al server de Authentik con un token — por eso, si creaste
un proveedor/outpost RAC en la UI de Authentik y no instalaste este add-on (o
cualquier otro contenedor RAC), el outpost va a quedar en salud "not
available" para siempre: nunca hay un proceso real conectándose.

Este add-on es exactamente ese proceso.

---

## Requisito previo: el add-on `authentik` principal

Este add-on asume que ya tenés el add-on **Authentik** (el principal, con
Postgres embebido) instalado y andando. Acá solo corre el outpost que se
conecta a él — no tiene base de datos ni estado propio.

## Configuración

| Opción | Descripción |
|--------|-------------|
| `authentik_host` | URL completa (con `https://`) del add-on Authentik principal. Usá el mismo dominio público que ya tenés en NPM, ej `https://auth.example.com`. |
| `authentik_token` | Token del outpost, generado por Authentik al crear el proveedor RAC. Ver abajo cómo conseguirlo. |
| `authentik_insecure` | `true` para no validar el certificado TLS de `authentik_host` (self-signed, etc). Default `false`. |

### Cómo conseguir el token

1. En Authentik: **Admin interface → Applications → Providers**, creá un
   **RAC Provider** (apuntando al host/RDP/VNC/SSH que querés exponer).
2. **Admin interface → Applications → Outposts**, creá un outpost tipo
   **RAC**, asignale el provider de arriba.
3. Abrí ese outpost recién creado → **View Deployment Info** (o el ícono de
   "descargar" según la versión) → ahí está el token (`AUTHENTIK_TOKEN`) que
   Authentik generó junto con una cuenta de servicio dedicada para ese
   outpost. Pegalo en `authentik_token`.
4. Instalá y arrancá este add-on con `authentik_host` + ese token.
5. Volvé a la página del outpost en Authentik — la salud debería pasar a
   verde en unos segundos (el outpost se conecta solo por WebSocket, no hace
   falta abrir ningún puerto en este add-on ni en tu router).

## Notas

- No expone ningún puerto: todo el tráfico (registro del outpost + las
  sesiones RAC en sí) va por la conexión saliente hacia `authentik_host`, tal
  como lo documenta Authentik para deploys manuales de outposts vía Docker.
- Sin estado/persistencia: no usa `/data`. Si necesitás rotar el token, solo
  cambiálo en la configuración del add-on y reiniciá.
- Corre como el usuario no-root que ya trae la imagen base (no necesita root
  ni privilegios especiales).
- La versión de la imagen (`ghcr.io/goauthentik/rac`) está pineada igual que
  la del add-on Authentik principal — mantenelas en sync si actualizás una.
