# Changelog

## 0.2.0
- Fix pérdida de datos entre updates: DATA_DIR vuelve a /data (storage
  persistente nativo de HA). addon_config:rw se mantiene para browsing
  pero el dato vive en /data que HA garantiza entre rebuilds.

## 0.1.9
- Agregar icon.png y logo.png para la UI de Home Assistant.

## 0.1.8
- Iconos PNG para iOS PWA: apple-touch-icon 180px, manifest 192px y 512px.
- Favicon .ico para browsers desktop.

## 0.1.7
- Datos en `/addon_configs/headon/` (visible desde HA file editor y Samba).
  Antes usaba `/data` que es interno del container.

## 0.1.6
- Fix concurrencia server: contextvar se resetea con token después de cada
  request (patrón SnapBudget). Cache de init_db por usuario.
- Fix offline multi-usuario: IndexedDB namespaceada por email. Dos usuarios
  en el mismo dispositivo ya no comparten cache ni cola de sync.

## 0.1.5
- Aislamiento de datos por usuario: cada usuario tiene su propia DB en
  `/data/users/{email}/migraines.db`. No hay filtración entre usuarios.

## 0.1.4
- Chips de tipo de dolor más compactos para caber en una fila en mobile.
- Fix "vundefined": /api/version ahora es público (no requiere auth).
- Cambio de contraseña self-service en tab Config.

## 0.1.3
- Fecha y hora de inicio en la misma línea para mayor compacidad.
- Botones Guardar/Cancelar flotantes (sticky bottom) para acceso rápido.

## 0.1.2
- Admin puede crear usuarios con cualquier email (sin restricción de dominio).
- Formulario de creación de usuario en el panel de administración.

## 0.1.1
- Agregar build.yaml con imágenes base por arquitectura (fix build en HA).

## 0.1.0
- Release inicial como HeadOn: registro de episodios de migraña.
- Selector de localización SVG estilo Migraine Buddy: vista frontal (corona,
  frente, sien, ojo, mejilla, mandíbula) y posterior (parietal, occipital, cuello),
  con labels izquierda/derecha.
- Campos: fecha, hora inicio, intensidad 1-10 (touch), localización, tipo dolor,
  aura, medicación, comentarios, duración auto.
- Sistema de autenticación con registro, login, admin y rate limiting (copiado
  de SnapBudget).
- Panel de administración: toggle registro, gestión de usuarios.
- Soporte offline: IndexedDB para cola de operaciones + cache de datos. Al
  volver la conexión, sincroniza automáticamente con el servidor.
- Service worker para cache de assets estáticos (PWA standalone).
- Calendario mensual con indicadores de intensidad por día.
- Exportación a Excel (.xlsx) con filtro de fechas.
- Estilo visual basado en SnapBudget (tabs, navbar, colores, accent configurable).
