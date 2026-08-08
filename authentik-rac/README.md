# Home Assistant add-on: Authentik RAC Outpost

Corre el outpost RAC de [Authentik](https://goauthentik.io)
(`ghcr.io/goauthentik/rac`, incluye [guacd](https://guacamole.apache.org/)):
acceso remoto vía navegador a RDP/VNC/SSH, protegido por Authentik.

RAC nunca corre embebido en el server principal de Authentik — necesita su
propio proceso conectado por token. Este add-on es ese proceso; requiere
tener ya instalado el add-on [`authentik`](../authentik) principal.

Ver [DOCS.md](./DOCS.md) para cómo generar el token del outpost desde la UI
de Authentik y la configuración completa.

## Instalación

1. Instalá primero el add-on **Authentik** (principal) si todavía no lo tenés.
2. En Authentik, creá un **RAC Provider** + un **Outpost** tipo RAC, y sacá el
   token de "View Deployment Info".
3. Instalá este add-on y completá `authentik_host` (la URL pública de tu
   Authentik, ej `https://auth.sbsoft.com.ar`) y `authentik_token`.
4. Arrancalo. La salud del outpost en la UI de Authentik debería pasar a
   verde en unos segundos.
