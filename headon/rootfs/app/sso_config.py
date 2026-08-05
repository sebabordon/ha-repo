"""Config de SSO/OIDC leída de env vars — sin dependencias de auth.py ni
oidc.py, para que ambos puedan importarla sin ciclos."""
import os

OIDC_ENABLED = os.environ.get("OIDC_ENABLED", "false").strip().lower() in ("1", "true", "yes")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "").strip().rstrip("/")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "").strip()

# Sólo "prendido" de verdad si además está configurado — un checkbox tildado
# sin completar issuer/client_id/secret no debe romper el login local.
SSO_ENABLED = bool(OIDC_ENABLED and OIDC_ISSUER and OIDC_CLIENT_ID and OIDC_CLIENT_SECRET)
