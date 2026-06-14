# Guía de diseño — Finance Me (gastos-tarjetas)

Convenciones de UI para que la app crezca con un estilo consistente. **Todo
agregado nuevo de UI debe seguir esto.** Si algo no encaja, primero se actualiza
esta guía y después se implementa (no al revés).

## Botones

### Clases base (CSS en `static/style.css`)
- `.btn` — botón base.
- `.btn-primary` — acción principal (azul). Uno por grupo/fila.
- `.btn-danger` — acción destructiva (rojo): borrar, etc.
- `.btn-pagado` — verde, marcar pagado.
- `.btn-sm` — variante chica (barras de herramientas).
- `.pago-action` — botones de acción de la tabla de Pagos (icono+texto).

### Texto + emoji
Todo botón de acción lleva **emoji + texto**, en ese orden: `💾 Guardar`.

- **Excepción — botones `+` / `×` / `✕`**: los de "agregar" (`+ Movimiento`,
  `+ Chart`…) y cierre/cancelar inline (`×`, `✕`) quedan **icono-solo**, no se les
  agrega texto ni se tocan.
- Si el texto del botón se **reescribe desde JS** (`btn.textContent = …`,
  estados tipo "Aplicando…", toggles "Ver/Cerrar"), el emoji debe ir **también**
  en esas asignaciones del JS, no solo en el HTML. Si no, se pierde al primer uso.

### Vocabulario de emojis (oficial — reusar estos, no inventar)
| Acción | Emoji | | Acción | Emoji |
|---|---|---|---|---|
| Guardar | 💾 | | Cancelar | ❌ |
| Agregar / Nueva | ➕ | | Borrar | 🗑 |
| Recargar / Actualizar | ↺ | | Exportar / descargar | ⬇ |
| Restablecer (a default) | ↩ | | Reaplicar / reprocesar | 🔄 |
| Buscar | 🔍 | | Categorizar / etiquetar | 🏷️ |
| Probar / ejecutar | ▶ | | Confirmar | ✓ |
| Ver / mostrar (keywords) | 🔑 | | Transferencia | ⇄ |
| Activar notificaciones | 🔔 | | Desactivar notif. | 🔕 |
| Limpiar / resetear | 🧹 | | Movimientos | 🧾 |
| Pagado | ✓ | | Finalizar | ■ |
| Editar | ✎ | | Reabrir | ↺ |

Iconos en glifo de texto (✓ ■ ✎ ↺ ⬇ ↩ ⇄) heredan el color del botón →
preferidos cuando el icono debe seguir el color (ej. rojo de `.btn-danger`).
Emojis a color (💾 🗑 🔔…) para el resto.

## Toggles de display (icono / texto / ambos)
Patrón: el label se parte en dos `<span>` con clases propias, y una clase en
`<body>` oculta una u otra.

- **Pestañas de navegación**: `.tab-icon` / `.tab-text` + `body.tab-mode-icons` /
  `body.tab-mode-text`. Pref: `ui_prefs.tab_icon_mode`.
- **Botones de acción de Pagos**: `.pa-icon` / `.pa-text` + `body.pago-btns-icons`
  / `body.pago-btns-text`. Pref: `ui_prefs.pago_btn_mode`.

> **Pendiente (estructural):** unificar TODOS los botones de acción bajo una
> convención global `.btn-icon` / `.btn-text` + `body.btns-icons|text` con su
> propio toggle. Hoy la mayoría tiene el emoji inline (un solo nodo de texto), no
> en spans → no responden a ningún toggle. Migrar a spans es el trabajo de esa
> tanda. Hasta entonces, los emojis nuevos van inline siguiendo el vocabulario.

## Chips de estado del scraper (borde derecho de color)
En los chips de saldo/vencimiento (`_scraperStatusColor` en `app.js`):
- 🟢 verde (`scrape-ok`) — último scrape OK dentro de la ventana.
- 🟡 amarillo (`scrape-warn`) — atrasado / nunca corrió OK.
- 🔴 rojo (`scrape-err`) — último scrape falló / sesión expirada.
- 🔵 azul pulsante (`scrape-run`) — corriendo ahora (auto-refresh hasta terminar).

## Colores
Variables CSS en `:root` (configurables en Config → UI): `--color-ars`,
`--color-usd`, `--color-rg5617`, `--color-accent`, `--color-cat-parent`,
`--color-cat-child`. Usar las variables, no hex sueltos, para montos/categorías.

## Fechas y horas
- Se **guardan en UTC** en la DB.
- Se **muestran en la zona horaria del browser**: usar `_fmtTs()` (fecha+hora
  corta) o `_fmtLogTs()` (log, con segundos). Nunca renderizar el timestamp crudo.

## Refresco de datos
Tras cualquier mutación amplia (importación, scraper, ABM categorías, alta/baja de
movimientos, reglas), llamar `refreshAfterDataChange()` — no listar `load*()` a
mano (se olvida alguno). Excepción: edición de una sola celda de la grilla →
refrescar solo gráficos (no `loadGastos`, perdería ediciones en curso).

## Configuración
Toda config va en la UI (Config → sección correspondiente), nunca hardcodeada en
Python. Default sensato OK, pero override desde la UI siempre. (Ver CLAUDE.md.)
