# Changelog

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
