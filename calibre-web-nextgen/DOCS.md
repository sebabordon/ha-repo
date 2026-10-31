# Calibre-Web-NextGen

- `library` (default `/media/Libros`): carpeta con `metadata.db`. Se pasa a NextGen con `CWA_CALIBRE_LIBRARY_DIR`.
- `ingest` (opcional): carpeta de la que NextGen importa libros nuevos (`CWA_INGEST_FOLDER`).
- Acceso: panel "Libros" (Ingress) o `http://<ha>:8083`. Login inicial de upstream: `admin` / `admin123`.
- `/media`, `/share` y `/config` están mapeados en lectura/escritura.
- `trusted_origins`: origen público si usás reverse proxy, ej. `https://library.example.com` (varios separados por coma). Si el login falla con "Rejected cross-site POST", es esto.
- `trusted_proxy_count`: cantidad de proxies delante (default 1).
