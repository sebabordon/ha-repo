# Changelog

## 0.3.0
- Indicador offline: dot ámbar pulsante en la navbar cuando no hay red.
- Auto-finalización: episodios de días anteriores sin fin se cierran a 23:59
  automáticamente al cargar.
- Campo "Hora de fin" visible solo al editar (no al crear).
- Síntomas adicionales: sección colapsable "Más síntomas" con chips multi-select
  (Náuseas, Vómitos, Fotofobia, Fonofobia, Mareos, Visión borrosa, Rigidez
  cervical, Congestión nasal, Lagrimeo, Internación).
- Config: toggle para mostrar síntomas abiertos por defecto.
- Síntomas en el listado de episodios y en el export Excel.

## 0.2.2
- Fix ícono iOS: servir apple-touch-icon.png y favicon.ico desde la raíz
  (iOS busca /apple-touch-icon.png, no dentro de /static/). Rutas públicas
  sin auth para que iOS las descargue al agregar a inicio.

## 0.2.1
- Fix fecha/hora en iOS: forzar min-width:0 en flex children para que los
  inputs nativos de date/time no desborden y queden en una fila.

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
