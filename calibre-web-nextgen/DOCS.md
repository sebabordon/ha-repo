# Calibre-Web-NextGen

- `library` (default `/media/Libros`): carpeta con `metadata.db`. Se enlaza a `/calibre-library`, que es donde NextGen busca la biblioteca.
- `ingest` (opcional): carpeta de la que NextGen importa libros nuevos (se enlaza a `/cwa-book-ingest`).
- Acceso: panel "Libros" (Ingress) o `http://<ha>:8083`. Login inicial de upstream: `admin` / `admin123`.
- `/media`, `/share` y `/config` están mapeados en lectura/escritura.
