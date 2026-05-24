## 0.2.51

- **Grilla de charts unificada y reordenable**: todos los charts (fijos y personalizados) viven en la misma grilla. Cada uno tiene botones ← → para reordenar. El orden se persiste en base de datos.
- **Charts personalizados**: botón "+ Chart" que abre un modal para configurar nombre, tipo (barras/línea/dona), dimensión (categoría/mes/fuente/persona) y métrica (egresos/ingresos/cantidad). Filtros opcionales fijos por mes, fuente, persona y categoría; si vacíos, usan los filtros globales del tab. Los charts personalizados tienen además ✎ editar y ✕ eliminar.
- **Endpoint `/api/stats/pivot`**: nuevo endpoint para queries dinámicos agrupados por cualquier dimensión.
- **Nuevo módulo `routes/charts.py`**: CRUD de custom charts + layout + pivot.

## 0.2.50

- **Cross-filtering en Gráficos**: hacer click en una categoría (donut o stacked bar) filtra todos los demás charts al instante. Aparece un badge oscuro con el nombre de la categoría y un × para limpiar. Las categorías no seleccionadas se atenúan en el donut.
- **Click en leyenda (stacked bar)**: hacer click en un ítem de la leyenda también activa el cross-filter.
- **Click en Fuente o Persona**: hacer click en una barra/slice de esos charts actualiza el selector correspondiente (fuente / persona) y recarga los charts.
- **Backend**: nuevo parámetro `categoria` en `/api/stats` y todas las funciones de stats para soportar el filtrado.

## 0.2.49

- **Fix carga inicial de Gráficos mostraba todo el historial**: `loadCharts()` se ejecutaba antes de que `_populateMonthFilter` tuviera tiempo de setear `cf-mes`, así que el primer render usaba filtro vacío (todos los meses). Ahora `loadCharts()` se dispara desde dentro de `_populateMonthFilter`, garantizando que el filtro ya esté seteado.
- **Gráficos arranca en el último mes cerrado**: el selector de mes de Gráficos (`cf-mes`) defaultea al último mes *completo* (estrictamente anterior al mes en curso), mientras que Gastos sigue defaulteando al mes activo (mes corriente con datos parciales).

## 0.2.48

- **Total en cada gráfico**: cada chart de Gráficos muestra el total del período en el encabezado — Egresos por categoría, Top 15 descripciones, Mes a mes, Por fuente y Por persona.

## 0.2.47

- **Columnas ordenables — Gastos**: hacer click en los encabezados Fecha, Descripción, Monto, Persona y Categoría ordena la tabla. Click de nuevo invierte el orden. El orden es client-side sobre los datos ya cargados.
- **Columnas ordenables — Presupuesto**: los encabezados Categoría/Persona, Presupuesto, Gastado y Diferencia también son clicables. Por defecto ordena por Gastado descendente.
- **Presupuesto por Persona**: segunda sección en la solapa Presupuesto que permite definir un presupuesto mensual por usuario y compararlo contra el gasto real del mes. Misma UX que el presupuesto por categoría — editable inline, auto-save, barra de progreso.
- **Reglas de usuario (nota)**: ya existían en Config → Personas → "Reglas de asignación de persona".

## 0.2.46

- **Fix filtro de mes se reseteaba al guardar categoría**: al llamar `saveCategoria` o `saveFecha` se recargaba el gráfico mensual, que a su vez repoblaba el combo de meses. Si el usuario tenía "Todos los meses" seleccionado (valor vacío), la lógica lo trataba como "sin selección" y aplicaba el mes por defecto (mes actual). Ahora, después del primer cargado inicial, el combo siempre preserva el valor que el usuario tenía — incluido el vacío ("Todos los meses").

## 0.2.45

- **Autocomplete de categorías**: el campo de categoría en la tabla de Gastos y en el panel "Nuevo movimiento" ahora sugiere las categorías existentes al tipear, usando un `<datalist>` nativo del browser. Evita crear categorías duplicadas por errores de tipeo.

## 0.2.44

- **Cuentas en Config**: la solapa "Cuentas" fue eliminada y su contenido se movió a una sección colapsable dentro de ⚙ Config, al final del orden Importar → Reglas → Personas → Cuentas → Borrar.
- **"Cerrar todo" en Config**: nuevo botón que colapsa todas las secciones de Config de una vez para navegar más rápido.
- **Botón ↑ scroll-to-top**: botón flotante que aparece al scrollear más de 200px y lleva de vuelta al inicio de la página.

## 0.2.43

- **Fix `importaciones.cantidad` siempre mostraba 1**: `SELECT changes()` después de `executemany()` en SQLite devuelve solo el conteo de la **última** fila del batch, no el total. Corregido usando `total_changes()` antes y después. Migración automática `fix_importaciones_cantidad_v1` recalcula los conteos históricos desde la tabla `gastos`.

## 0.2.42

- **Importar por parser**: la sección Importar en Config ahora muestra una grilla de cards — una por fuente (AMEX, BBVA MC, BBVA Visa, BBVA Cuenta, Galicia MC, MercadoPago). Cada card indica el último mes importado y la cantidad de movimientos. Click en la card abre el selector de archivo y sube automáticamente.
- **Borrar datos separado**: el danger zone de borrar movimientos se movió a su propia sección "Borrar datos" al final de Config, colapsada por default, con header en rojo para distinguirla claramente.

## 0.2.41

- **Fix forecast — mes incompleto**: el chart de proyección excluye el mes en curso de la regresión lineal. Un mes parcial (ej. 23 de 31 días importados) tiraba la tendencia a cero y proyectaba gastos casi nulos. El mes actual sigue apareciendo en la serie histórica del gráfico.
- **Fix gráfico mensual superior — actualización dinámica**: ahora se refresca al guardar un movimiento manual, al cambiar la fecha de un gasto, y al cambiar la categoría de un gasto.

## 0.2.40

- **Categorías especiales**: las reglas de categorización ahora tienen un checkbox "Especial". Las categorías marcadas como especiales se excluyen de totales y gráficos. Dos checkboxes "Sin especiales" (activos por defecto) en las solapas Gastos y Gráficos controlan la exclusión.
- **Siempre excluido en el gráfico superior**: el chart mensual de la página principal siempre excluye categorías especiales.
- **Categorías especiales built-in**: "Transferencia" y "Transferencia Intercuentas" siempre se excluyen de los totales (sin necesidad de crear regla).
- **🔁 Transferencias → "Transferencia Intercuentas"**: el botón de matching automático ahora categoriza como "Transferencia Intercuentas" en lugar de "Transferencia".
- **Excluye especiales en stats**: `/api/stats` y `/api/gastos/monthly` excluyen categorías especiales por defecto; se puede desactivar con `excluir_especiales=false`.
- **`GET /api/categorias/especiales`**: nuevo endpoint que retorna la lista de categorías especiales activas.

## 0.2.39

- **Filtro por importación en Gastos**: nuevo combo "+" en la barra de filtros de la solapa Gastos que permite filtrar todos los movimientos de una importación específica. Oculto por default; se despliega con el botón `+` y colapsa limpiando el filtro. Útil para detectar inconsistencias en imports recientes.

## 0.2.38

- **Fix Galicia MC — comisión de mantenimiento de cuenta**: la comisión (COMISION MANT DE CTA + IVA) aparece solo en el bloque CONSOLIDADO del PDF sin prefijo de fecha, por lo que el parser no la capturaba. Ahora se extrae del texto del PDF y se agrega como egreso en la fecha de cierre del resumen. En meses con bonificación (el banco la devuelve cuando se supera el umbral de gasto), el BONIF.COM.MEN.MANT.C del DETALLE se incluye como ingreso compensatorio — neto = 0. El neto de egresos e ingresos cuadra exactamente con el "TOTAL A PAGAR" del resumen.

## 0.2.37

- **Combos de fuente dinámicos**: los selectores de fuente en los filtros de Gastos, Gráficos, Eliminar por fuente y las reglas de emparejado ahora se construyen a partir de las cuentas configuradas (via `/api/cuentas`). Reflejan automáticamente cambios de nombre de cuenta (ej. "BBVA ARS" en lugar de "BBVA Cuenta") y cuentas manuales.
- **Tabla fuente→persona dinámica**: la tabla de asignación de fuente a persona en Config → Personas también usa los nombres reales de las cuentas.
- **Renombrar categoría**: doble clic en cualquier chip de categoría abre un editor inline. Enter/blur guarda, Escape cancela. Campo vacío limpia la categoría de todos los gastos (útil para eliminar categorías con typos sin gastos asociados). Llama a `POST /api/categorias/rename`.
- **Config tab refresca reglas**: al hacer clic en la pestaña Config, las reglas de categoría y de emparejado se recargan del servidor para reflejar aprendizaje automático (keywords auto-agregadas al categorizar gastos).
- **Fix Galicia MC — cuotas usan fecha del resumen**: los pagos en cuotas (`CUOTA DEL MES`) y débitos automáticos (`DEBITOS AUTOMATICOS`) usaban la fecha original de compra (ej. Nov-25) en lugar de la del resumen actual. Ahora se detecta la fecha de cierre del resumen (3er fecha en la fila de 6 fechas del encabezado) y se reasigna al mes de liquidación. El indicador de cuota (`NN/NN`) se elimina de la descripción almacenada.

## 0.2.36

- **Fix persona de adicional en importación**: los parsers de AMEX y BBVA siempre emitían `"Adicional"` hardcodeado; ahora `upload.py` lo traduce al nombre real configurado en la slot 1 de personas (ej. "Mada"). Si renombrás la persona, los próximos imports ya usan el nombre nuevo.
- **Rename de persona propaga a la DB**: al renombrar una persona en Config → Personas, ahora también se actualiza `usuario` en todos los registros existentes de la tabla `gastos` (antes solo se actualizaba el config). El toast confirma cuántos gastos fueron actualizados.
- **Nuevo endpoint** `POST /api/config/usuarios/rename-db` + `rename_usuario_in_gastos()` en `db.py`.
- **Edición inline de keywords** (doble clic en etiquetas de reglas de categoría y persona): Enter guarda, Escape cancela, blur guarda, campo vacío elimina.

## 0.2.35

- **Unificación de convención de signos**: a partir de esta versión todos los movimientos en la BD usan `monto > 0 = egreso` y `monto < 0 = ingreso`, sin excepción de fuente. Se eliminan los CASE especiales por fuente en todas las queries SQL.
- **Migración automática** (`normalize_signs_v1`): al iniciar, la app flipea los montos de las fuentes no-CC (bbva_cuenta, mercadopago, manuales) existentes en la BD. La migración es idempotente (tabla `db_migrations`).
- **Import normalizado**: `upload.py` ahora flipea el signo para fuentes no-CC en el momento de importar, sin necesidad de modificar los parsers.
- **Backend simplificado**: `_EGRESO_EXPR` es ahora `CASE WHEN monto > 0 THEN monto ELSE 0 END`; `monthly_summary`, `detect_transfers` y `stats_forecast` usan la misma expresión simple. Se eliminó `_cc_list`.
- **`recalc_cuenta_saldo`**: actualizado para usar `−SUM(monto)` (balance = ingresos − egresos con la nueva convención).
- **Frontend**: `_isEgreso(monto)` ya no necesita el segundo argumento `fuente`. Los movimientos manuales se guardan con el signo correcto (egreso = positivo), y la lista de movimientos de cuenta refleja el nuevo display (positivo → rojo, negativo → verde con "+").

## 0.2.34

- **Tabla de Gastos — display normalizado**: los montos siempre se muestran como valor absoluto. Rojo = egreso (dinero que sale), verde con "+" = ingreso (dinero que entra). Aplica la convención correcta según la fuente: tarjetas CC (positivo = egreso) y cuentas/billeteras (negativo = egreso).
- **Resumen normalizado**: el contador de la tabla ahora muestra "Egresos ARS X · Ingresos +Y" en lugar del total crudo, que era engañoso al mezclar fuentes con convenciones distintas.
- **CSS**: `.monto.egreso` (rojo), `.monto.ingreso` (verde), `.monto.usd` (itálica). Se elimina `.monto.neg`.
- Los gráficos ya usaban `_EGRESO_EXPR` y no cambian.

## 0.2.33

- **Fix caché de service worker**: el CACHE name del SW ahora incluye la versión (`gastos-v0.2.33`) y se inyecta dinámicamente desde el servidor. Cada deploy invalida el caché anterior, evitando que el browser sirva app.js/style.css viejos.
- **APP_VERSION** centralizado en `config.py`; `main.py` lo usa para versionar el SW sin duplicación.

## 0.2.32

- **Renombrar personas**: click en el chip de cualquier persona (incluidas las dos primeras) para editarlo inline. Enter guarda, Escape cancela. Propaga el rename a los mapeos de fuente→persona y a las reglas de asignación.
- **Renombrar cuentas**: click en el nombre de cualquier cuenta (auto o manual) para editarlo inline. Enter o click fuera guarda, Escape cancela. Backend: `PUT /api/cuentas/{fuente}` ahora acepta `{nombre}`.

## 0.2.31

- **Renombrar "Usuario" → "Persona"** en toda la UI (columna de tabla, gráfico, acordeón Config, encabezados, mensajes). Los campos internos de API/DB (`usuario`) no cambiaron.
- **Reglas de asignación de persona**: nueva sección en Config → Personas con el mismo patrón de tags que las reglas de categoría. Cada regla define palabras clave + persona destino. La primera regla que coincida con la descripción del gasto gana. Se aplican al importar y con el botón "Reaplicar a todos".
- **Backend**: `apply_user_rules()` en `db.py`, `POST /api/config/usuarios/apply`, soporte de `reglas_usuario` en `PUT /api/config/usuarios` y en `upload.py` (prioridad: parser > reglas > fuente por defecto).
- **PWA (acceso directo)**: favicon (`icono-sb.ico/png/svg`), `manifest.json` y service worker (`sw.js`) con caching de assets estáticos. El SW sólo se registra cuando no se usa ingress (`!INGRESS_PREFIX`). Rutas `/manifest.json` y `/sw.js` servidas desde la raíz sin autenticación.

## 0.2.30

- **Tracking de importaciones**: cada importación queda registrada con fecha, fuente, nombre de archivo y mes del resumen detectado automáticamente (por mes más frecuente en los movimientos). Columna `import_id` agregada a `gastos`.
- **Borrar por importación**: el selector de borrado tiene optgroups — "Por fuente" (comportamiento anterior) y "Por importación" (nueva, muestra cada batch con fecha/fuente/mes/archivo/cantidad). Así se puede reimportar un resumen sin tocar el resto.
- **Backend**: nueva tabla `importaciones`, nueva función `list_importaciones()`, endpoint `GET /api/importaciones`, y `DELETE /api/gastos?import_id=N`.

## 0.2.29

- **Fix: gráficos no cargaban al inicio** — `loadCharts()` se llama ahora en el startup junto con `loadMonthlyChart()`.
- **Config: acordeón en lugar de sub-tabs** — Importar, Reglas y Usuarios son secciones colapsables con botón "+" para expandir; están colapsadas por defecto.
- **Fix: agregar usuario inline** — El botón "+" al final de la lista de usuarios despliega un input inline (igual que las reglas), sin diálogo modal. Enter guarda, Escape cancela.

## 0.2.28

- **Mes por defecto en Gastos**: la tabla de gastos ahora carga automáticamente el mes más reciente ≤ hoy en lugar de cargar todos los movimientos. Mejora el rendimiento en la carga inicial.
- **Forecast — excluir ingresos excepcionales**: nuevo control "+ Excluir de ingresos" en el gráfico de Forecast. Permite excluir categorías específicas (ej. bonos) del cálculo de la línea de tendencia de ingresos. La selección se persiste en `localStorage`.
- **Tab ⚙ Config**: Importar y Reglas se movieron a un único tab "Config" con sub-tabs. Se agrega nuevo sub-tab **Usuarios** para:
  - Gestionar la lista de usuarios (Titular, Adicional y cualquier usuario adicional).
  - Configurar el usuario asignado por defecto al importar cada fuente.
  - Los dropdowns de usuario en Gastos y Gráficos se actualizan dinámicamente.
- **Backend — configuración de usuarios**: nuevo endpoint `GET/PUT /api/config/usuarios` con persistencia en `/data/user_config.json`. `upload.py` lee el mapeo fuente→usuario dinámicamente en lugar de usar valores fijos.

## 0.2.25

- **Edición de fecha en Gastos**: la columna Fecha es ahora un `<input type="date">` editable. Al cambiar la fecha se guarda automáticamente vía `PATCH /api/gastos/{id}/fecha`. Útil para corregir fechas de cuotas mal asignadas por el parser.
- **Fix auto-aprendizaje de reglas**: se eliminó la condición que bloqueaba el aprendizaje cuando el movimiento ya tenía categoría por regla. Ahora cualquier edición manual de categoría agrega la descripción a las reglas, independientemente del origen anterior.

## 0.2.24

- Documentación (`DOCS.md`) agregada al add-on: opciones de configuración, usuario admin, fuentes soportadas, cuentas, usuarios Titular/Adicional, reglas, presupuesto y FAQ.

## 0.2.23

- **Purga de datos personales** — apto para compartir públicamente:
  - `allowed_domain` por defecto cambiado a `example.com` (era un dominio personal).
  - Usuarios `Seba`/`Mada` reemplazados por **`Titular`/`Adicional`** en toda la UI, parsers y valores por defecto de fuente.
  - Nueva opción `titular2_name` (opcional): nombre o fragmento que aparece en los headers del PDF de AMEX/BBVA para identificar al titular adicional. Si no se configura, todos los movimientos se asignan al Titular.
  - Eliminadas variables muertas `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` de `config.py`.
  - CHANGELOG anonimizado.

## 0.2.22

- Renombrado el add-on a **"Gastos"** (era "Gastos Tarjetas") en título, navbar, login, admin y panel de HA.
- Fix visual: botones ✓ y ✕ en tabla Gastos del mismo tamaño y alineados; filas no manuales reservan el espacio del ✕ para mantener la columna uniforme.

## 0.2.21

- **Eliminar movimientos manuales desde Gastos**: filas de cuentas manuales muestran un botón ✕ para eliminarlas; actualiza el saldo de la cuenta automáticamente.
- **Fix decimales en inputs de saldo**: los campos de edición de saldo (widget y tab Cuentas) ahora muestran el valor en formato argentino (`18.388,62`) para que `_parseNum` lo parsee correctamente; antes se perdían los decimales.
- **Moneda automática en "+ Movimiento"**: al seleccionar una cuenta USD el selector de moneda cambia automáticamente a USD (ídem ARS); para cuentas MULTI se deja libre.

## 0.2.20

- **Multi-moneda en cuentas**: cada cuenta tiene selector de moneda (ARS / USD / MULTI). Las tarjetas de crédito (AMEX, BBVA Visa, BBVA MC, Galicia MC) se migran automáticamente a MULTI y muestran dos saldos: ARS + USD. Cuentas ARS o USD muestran su saldo en la moneda correspondiente.
- **Selector de moneda en tab Cuentas**: dropdown compacto por cuenta; cambiar la moneda llama a `PUT /api/cuentas/{fuente}` y actualiza el widget de saldos.
- **Edición de saldo para MULTI**: al editar el saldo de una cuenta MULTI se despliegan dos inputs (ARS y USD).
- **Nueva cuenta manual con moneda**: el botón "+ Cuenta" pregunta primero el nombre y luego la moneda (ARS o USD); MULTI solo aplica a cuentas automáticas.
- **`saldo_usd` en `cuentas`**: columna nueva; `recalc_cuenta_saldo()` actualiza `saldo` o `saldo_usd` según la moneda de la cuenta; cuentas manuales USD acumulan sus movimientos en `saldo_usd`.

## 0.2.19

- **Auto-aprendizaje de reglas**: al categorizar manualmente un movimiento, su descripción se agrega automáticamente como keyword a la regla de esa categoría (creando la regla si no existía). Solo aplica cuando la categoría anterior no era ya 'regla'. Los imports futuros con la misma descripción quedan automáticamente categorizados.
- **Formulario "+ Movimiento"** en tab Gastos: botón junto a Filtros que despliega un panel con selector de cuenta manual, fecha, descripción, tipo (Egreso/Ingreso), monto, categoría y moneda. Los movimientos quedan visibles en Gastos y actualizan el saldo de la cuenta.
- **Tab Cuentas UI mejorado**: "Desactivar" renombrado a "Widget ✓/✗" con tooltip explicativo (controla si la cuenta aparece en el widget de saldos del top). Para cuentas manuales se muestra texto "Saldo calculado de movimientos" en lugar del botón de edición. Los movimientos de cuentas manuales se cargan automáticamente al abrir el tab.
- Eliminado el form de nuevo movimiento del tab Cuentas (consolidado en Gastos).

## 0.2.18

- **Tab Cuentas** (nuevo, entre Gastos e Importar): gestión completa de cuentas automáticas y manuales.
- Cuentas **automáticas**: saldo actualizado al importar PDF (si el parser lo detecta) o editable con ✏. Pueden activarse/desactivarse.
- Cuentas **manuales**: se crean desde el tab con nombre libre. Permiten agregar/eliminar movimientos (fecha, descripción, tipo Egreso/Ingreso, monto, categoría, moneda). El saldo se recalcula automáticamente al agregar o borrar movimientos. Los movimientos aparecen también en el tab Gastos.
- Migración automática de la tabla `cuentas`: agrega columna `tipo` ('auto'/'manual').
- Nuevos endpoints: `POST /api/cuentas`, `DELETE /api/cuentas/{fuente}`, `GET/POST/DELETE /api/cuentas/{fuente}/movimientos`.

## 0.2.17

- **Gemini como categorizador IA gratuito**: configurar `gemini_api_key` activa Google Gemini 2.0 Flash (~1.500 req/día gratis, solo requiere cuenta Google). Usa el endpoint OpenAI-compatible de Google AI Studio.
- Orden de fallback: reglas → Groq → Gemini → Claude. Se usa el primer proveedor con clave configurada.

## 0.2.16

- **Groq como categorizador IA gratuito**: configurar `groq_api_key` en el add-on activa la categorización automática vía Llama 3.1 8B Instant (gratis, ~14.000 req/día). Si hay clave Groq, se usa en lugar de Claude; Claude sigue funcionando como fallback si no hay clave Groq. Orden: reglas → Groq → Claude.
- **Reset de contraseña desde admin**: cada usuario en el panel `/admin` tiene un campo para establecer nueva contraseña directamente, sin necesidad de que el usuario lo solicite.

## 0.2.15

- **Registro deshabilitado por defecto**: `registration_enabled: false` en config. Para habilitar, cambiar a `true` y reiniciar el add-on.
- **Usuario administrador**: configurar `admin_password` en config para activar el usuario `admin@{dominio}`. Al loguearse como admin aparece el link ⚙ Admin en el navbar.
- **Panel de administración** (`/admin`): toggle de registro on/off en tiempo real (sin reiniciar), lista de usuarios registrados con opción de eliminar. Solo accesible con sesión de admin.
- El estado de registro se guarda en `/data/settings.json` (override del config, persiste entre reinicios).

## 0.2.14

- **Filtro por Moneda**: selector ARS / USD en Gráficos y selector Todas / ARS / USD en Gastos. Los gráficos siempre muestran una sola moneda (sin mezclar); el filtro de Gastos es independiente. Los USD nunca se convierten ni suman con ARS — se analizan separados. El gráfico de Forecast y el monthly overview superior siempre muestran ARS.

## 0.2.13

- **FIX raíz del ancho de Presupuesto**: el `</main>` estaba mal posicionado (cerraba antes del tab Presupuesto, introducido al agregar el tab en 0.2.3). El tab quedaba FUERA del `<main class="container">` con `max-width: 1200px`, por eso ocupaba todo el viewport. Ahora el `</main>` cierra después de Presupuesto, igual que todos los demás tabs.

## 0.2.12

- Presupuesto: tabla vuelve a width:100% pero con `width:1%; white-space:nowrap` en todas las columnas excepto Categoría — los números/barras/botones se dimensionan al contenido y la columna de categoría toma el espacio restante. Ya no queda espacio vacío a la derecha.
- Combos: `blur()` aplicado a todos los selectores de filtros (Gastos, Gráficos, Forecast) para que se puedan volver a abrir sin necesidad de hacer click afuera primero.

## 0.2.11

- Fix definitivo del ancho: `overflow-x: hidden` en el body previene scroll horizontal a nivel de página, independientemente de qué elemento lo cause.
- Presupuesto: `h2 { margin-right: auto }` en lugar de `flex: 1` — el h2 ya no se expande, solo empuja los controles a la derecha con margen automático.
- Presupuesto: tabla usa clase `table-wrap` (consistente con la tabla de gastos) en lugar de estilo inline.

## 0.2.10

- Presupuesto: tabla ya no se estira al 100% del contenedor — las columnas se dimensionan por su contenido (width: auto), quedando mucho más compacta.

## 0.2.9

- Presupuesto: corregido ancho excesivo — la sección ya no empuja el ancho de la página.
- Presupuesto: auto-guardado sin botón — se guarda 800ms después del último cambio (editar monto, agregar o eliminar categoría, salir de un campo). Botón "Guardar" eliminado.
- Presupuesto: Enter en el campo de monto guarda inmediatamente.

## 0.2.8

- Parser AMEX: detecta automáticamente las secciones por titular ("Nuevos Cargos en PESOS/DOLARES para <NOMBRE>") y asigna usuario="Adicional" al titular secundario según la opción `titular2_name`.
- Parser BBVA Visa: detecta la sección "Consumos <Nombre>" y asigna usuario="Adicional" al titular adicional; cierra en "TOTAL CONSUMOS DE <NOMBRE>".
- Los movimientos sin sección identificada se asignan al usuario por defecto de la fuente ("Titular") definido en upload.py.

## 0.2.7

- Reglas: auto-guardado sin botón — se guarda 800ms después del último cambio (agregar/eliminar regla, agregar/eliminar palabra, salir de un campo de texto). Los botones "Guardar" fueron eliminados.
- Reglas: "+ Nueva regla" hace scroll automático hasta el nuevo campo y le da el foco.
- Eliminados todos los alert/confirm/prompt nativos del navegador. Reemplazados por una barra de notificación fija debajo del navbar: verde para éxito, roja para error, amarilla para confirmaciones (con botón Confirmar/Cancelar), azul para inputs (ej: nueva categoría de presupuesto).

## 0.2.6

- Presupuesto: resumen de totales (presupuestado / gastado / diferencia / %) visible encima de la tabla cuando hay un mes seleccionado; fila Total en el pie de la tabla siempre visible.
- Presupuesto: tabla con overflow-x:auto — ya no rompe el ancho del tab en pantallas chicas.
- Presupuesto: selector de mes libera el foco automáticamente al elegir, para que se pueda volver a abrir sin necesidad de hacer click afuera primero.

## 0.2.5

- Fix: borrar la categoría de un movimiento (campo vacío + Enter) ya no deja categoria_fuente='manual'. Antes quedaba bloqueado y las reglas de categorización/emparejado no podían volver a aplicarle categoría.

## 0.2.4

- Fix "Reaplicar a todos": ya no pisa los movimientos marcados por reglas de emparejado (categoria_fuente='auto'). Antes, al reaplicar categorías se borraba la categoría "Transferencia" de los DEBIN/pagos de tarjeta que habían sido marcados por match rules.

## 0.2.3

- **Saldos de cuentas** (widget siempre visible encima de los tabs): muestra el saldo actual de BBVA Cuenta y MercadoPago (únicas cuentas marcadas como activas por defecto). Se actualiza automáticamente al importar un PDF/XLSX. Botón ✏ para override manual.
- **Forecast** (nuevo gráfico en tab Gráficos, fila inferior): proyección lineal a 6 o 12 meses de egresos e ingresos, calculada por regresión lineal sobre los últimos 3 o 6 meses históricos. La línea punteada arranca desde el último mes real.
- **Tab Presupuesto** (nuevo, a la derecha de Reglas): define un presupuesto mensual por categoría; al seleccionar un mes muestra gastado vs presupuestado con barra de progreso (verde → amarillo → rojo). Se pueden agregar/eliminar categorías y guardar.
- **Chip "Sin categoría"** en el slicer de categorías: filtra exclusivamente los movimientos sin categoría asignada, ideal para revisar qué falta categorizar.

## 0.2.2

- Enter en el campo de categoría graba inmediatamente (igual que el botón ✓)

## 0.2.1

- Fix gráfico Top 15 descripciones: crecía infinitamente por loop entre Chart.js y el contenedor. Ahora usa un wrapper con height fijo antes de crear el chart.

## 0.2.0

- **Tab Gráficos** (a la izquierda de Gastos): donut de egresos por categoría, top 15 descripciones (barras horizontales), stacked bar de categorías mes a mes, barras por fuente, donut por usuario. Filtros propios (fuente, usuario, mes específico o últimos N meses). Todos los gráficos usan la misma normalización de signos que el gráfico mensual.
- **Reglas de emparejado** (nueva sección en tab Reglas): define reglas con Lado A (patrón + fuente) y Lado B opcional (patrón + fuente + ventana de días). Si solo tiene Lado A, marca todos los movimientos que coincidan. Si tiene ambos lados, empareja transacciones dentro de la ventana de días y marca ambas. Cada regla tiene botón "Aplicar" individual y hay "Aplicar todas". Ideal para marcar pagos de tarjeta, transferencias entre cuentas, etc.
- Endpoints nuevos: GET/PUT `/api/rules/match`, POST `/api/rules/match/apply`, POST `/api/rules/match/apply-one`, GET `/api/stats`

## 0.1.9

- Fix definitivo parser BBVA Cuenta: los montos son right-aligned y no coinciden con las bandas de los encabezados de columna. Nueva heurística: el número con mayor x0 de cada fila = SALDO (se descarta), el resto = movimiento. Débito negativo = egreso, positivo = ingreso. Verificado contra PDF real: 32 movimientos con signos correctos.

## 0.1.8

- Botón ✓ de categoría se pone naranja (junto al borde del input) cuando hay cambios sin guardar
- Botón borrar ahora tiene un selector de fuente: podés borrar solo una fuente (ej: BBVA Cuenta) en lugar de toda la base

## 0.1.7

- Botón "Reaplicar a todos" en tab Reglas: aplica todas las reglas a los movimientos ya importados; respeta los que tienen categoria_fuente='manual' (editados a mano); limpia la categoría de los que dejaron de coincidir con alguna regla

## 0.1.6

- Fix parser BBVA Cuenta: ahora auto-calibra las columnas leyendo la fila de encabezado del PDF (posición real de DÉBITO / CRÉDITO / SALDO), en lugar de coordenadas x hardcodeadas que fallaban con el layout real
- Filtros en vivo: cambiar fuente, usuario o mes recarga la tabla automáticamente sin necesitar el botón "Cargar"; los chips de categorías también disparan reload al hacer click
- Borrar toda la base: botón en el tab Importar con confirmación (útil para limpiar y reimportar)

## 0.1.5

- Fix cuotas: el parser BBVA ahora detecta la fecha de cierre del resumen (patrón "AL DD/MM/YY" / "CIERRE: DD/MM/YY") y reemplaza el mes/año de los movimientos en cuotas por el del resumen, en lugar del mes de compra original
- Transferencias entre cuentas: botón "🔁 Transferencias" detecta automáticamente pares BBVA Cuenta ↔ MercadoPago con mismo monto (±3 días); al confirmar los marca como categoría "Transferencia" y los excluye del gráfico mensual
- UI responsive para mobile: filtros apilados, chart más compacto, fuentes reducidas, columna Moneda oculta en pantallas pequeñas, tabs scrolleables

## 0.1.4

- Nuevo parser: BBVA Cuenta (caja de ahorro/cuenta corriente PDF) — débito = egreso (negativo), crédito = ingreso (positivo)
- Gráfico mensual ARS arriba de los tabs: barras de Egresos y Ingresos mes a mes
- Filtro por mes: dropdown poblado automáticamente con los meses que tienen datos
- Filtro de categorías tipo slicer: chips multi-seleccionables con las categorías existentes
- Filtros colapsables: botón para mostrar/ocultar el panel de filtros
- Al importar, el chart y las categorías se actualizan automáticamente

## 0.1.3

- Reglas de categorización ahora usan palabras clave en lugar de regex — interfaz de etiquetas, escribís y Enter para agregar
- Nueva columna "Usuario" en gastos (Titular / Adicional), auto-asignado por fuente (BBVA y MercadoPago → Titular)
- Exportar gastos a Excel con filtros aplicados
- Corregido crash al cargar rules.yaml con escape inválido (`\+` en string YAML con comillas dobles)

## 0.1.2

- Corregido error de sintaxis YAML en default_rules.yaml (`star\+` en string con comillas dobles)
- `run.sh` valida `rules.yaml` al iniciar y lo reemplaza si está corrupto
- Errores de YAML en reglas ya no crashean la app (devuelve lista vacía)

## 0.1.1

- Corregido loop de redirección 307 con HA Ingress — se lee el header `X-Ingress-Path`
- Rutas JS (fetch) y links de auth usan el prefijo de Ingress
- Corregido crash en upload: `PARSERS[fuente]` es una instancia, no una clase

## 0.1.0

- Parser de extractos PDF: AMEX, BBVA Mastercard, BBVA Visa, Galicia Mastercard
- Parser de exportación XLSX: MercadoPago
- Categorización automática por reglas YAML con fallback opcional a Claude API
- Autenticación local con usuarios `@<allowed_domain>`
- Interfaz web con tabs: Gastos / Importar / Reglas
- Compatibilidad aarch64 (Raspberry Pi 5) y amd64
