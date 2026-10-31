# Changelog

## 4.1.60-2
- Fix: la biblioteca/ingest ahora se configuran con CWA_CALIBRE_LIBRARY_DIR / CWA_INGEST_FOLDER (/calibre-library es un VOLUME y no admite symlink).
- Nuevo: opciones `trusted_origins` (CWNG_TRUSTED_ORIGINS) y `trusted_proxy_count` para usar detrás de un reverse proxy; arregla "Rejected cross-site POST" en el login.

## 4.1.60-1
- Fix: /calibre-library de la imagen no estaba vacío y no se enlazaba la biblioteca; ahora se aparta y se enlaza.

## 4.1.60
- Versión inicial: wrapper de Calibre-Web-NextGen v4.1.60 con /media mapeado y biblioteca en /media/Libros.
