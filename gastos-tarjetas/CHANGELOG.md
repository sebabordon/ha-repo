## 1.2.43

- **Scraper AMEX: elimina la doble navegación previa al login** (`scrapers/amex.py`): el `check_session` navegaba a `global.americanexpress.com` (que redirige al login) ANTES de que `do_login` navegara al login de nuevo — navegación de más que además pegaba al dominio de Akamai con estado sucio antes de un login limpio. Se setea `save_session = False` (como en la 1.2.36, que se había perdido en el revert a 1.2.26): el base ya no restaura ni valida sesión, va directo a `do_login` con una sola navegación. `check_session` queda como no-op.

## 1.2.42

- **Scraper AMEX: login con interacción humana (mouse + cadencia de tipeo) para pasar Akamai** (`scrapers/amex.py`): se descubrió (probando en el Chrome real de la Mac) que Akamai bloquea el login automático aunque sea Chrome real, porque su sensor (bmak) mide actividad de mouse/teclado y el llenado instantáneo sin mover el puntero = entropía cero = bot. Confirmado: moviendo el mouse a mano y clickeando, el login pasaba solo. Ahora el `do_login` simula interacción humana: `_wiggle_mouse` (pasea el puntero por los campos con pausas vía ActionChains), `_human_click` (mueve el puntero al elemento + hover + click), y `_human_type` (tipea carácter por carácter con delays variables 50–160ms) para usuario, contraseña y submit. Esto genera la entropía de comportamiento que Akamai espera, sin intervención manual. Headless sigue sin pasar (destildar el checkbox); headful + esta humanización es lo que funciona.

## 1.2.41

- **Log de versión de Chromium + flags de estabilidad + AMEX headless opcional** (`scrapers/base.py`, `scrapers/amex.py`, `scraper_credentials.py`): (1) **Log de versión**: el `_create_driver` local ahora loguea `Chromium X | chromedriver Y` en cada run (y el remoto loguea la versión del Chrome de la Mac), para correlacionar los "tab crashed" con versiones — el base image `:latest` cambia el Chromium en cada rebuild sin avisar. (2) **Flags de estabilidad** en el Chromium local (RPi): `--disable-software-rasterizer`, `--disable-extensions`, `--disable-background-networking`, `--disable-renderer-backgrounding`, `--disable-backgrounding-occluded-windows`, `--js-flags=--max-old-space-size=512`, para reducir los crashes del renderer en páginas pesadas (BBVA) con render por software. No cambian el fingerprint JS; afectan solo BBVA/MP, no AMEX (que corre en la Mac). (3) **AMEX headless**: nuevo checkbox `webdriver_headless` — corre el Chrome de la Mac sin ventana visible. Pendiente: pinear el base image a un tag fijo (cuando tengamos la versión logueada).

## 1.2.40

- **Scraper AMEX: opción de WebDriver remoto (Chrome real en una Mac) para pasar Akamai** (`scrapers/amex.py`, `scraper_credentials.py`): como Akamai bloquea el Chromium de Alpine del contenedor (RPi/ARM, sin Chrome real disponible), se agregó la opción de correr el browser en una Mac de la LAN con un Selenium server + Chrome real (fingerprint genuino que sí pasa Akamai), manejado por red. Dos campos nuevos en la config de AMEX: `webdriver_remote_url` (URL del Selenium server, ej. `http://IP-Mac:4444`) y `webdriver_profile_dir` (ruta opcional de un perfil Chrome "tibio" en la Mac). `AmexScraper` overridea `run()`/`_create_driver()`: si hay URL, usa `webdriver.Remote` con opciones mínimas (solo quita el cartel de automatización, resto fingerprint real de macOS); sin URL, usa el Chromium local de siempre. Aislado a AMEX — BBVA y MP no se tocan. Además el login ahora llena usuario/contraseña con `send_keys` (eventos de teclado reales que React e InAuth aceptan) en vez del setter JS de React.

## 1.2.39

- **Revert del experimento AMEX/Akamai — vuelta al estado 1.2.26** (imagen liviana de nuevo): se revirtió todo el trabajo de las versiones 1.2.27–1.2.38 (login POST directo, Xvfb headful, visor noVNC, x11vnc/websockify, Firefox, spoofs de fingerprint anti-Akamai, modo login manual, performance logging) porque Akamai bloquea el fingerprint del Chromium de Alpine de raíz (probado: ni el login manual en el contenedor pasa, mientras Safari en la Mac con la misma IP sí) y el camino no era viable. Además ese stack engordaba la imagen (xvfb + novnc + firefox + fuentes) y el performance logging tumbaba el scraper de BBVA. El código de scrapers, Dockerfile, run.sh y rutas vuelven exactamente al estado 1.2.26. Queda pendiente decidir el enfoque para AMEX (Chrome real en base Debian si el HA es amd64, u otra vía).

## 1.2.26

- **Logs de la app visibles en el tab Log del add-on** (`log_config.json`): los `logger.info/warning/error` de los módulos de la app (scrapers, DB, scheduler, etc.) no aparecían en el output del add-on porque el `log_config.json` de uvicorn solo definía handlers para los loggers de uvicorn. Se agregó un handler `console` al root logger para que todos los logs de la app salgan por stderr con formato `[nombre_módulo]`, igual que los de uvicorn. Los access logs siguen por stdout sin cambios.

## 1.2.25

- **Scraper AMEX: fix login — usar React native setter en vez de send_keys** (`scrapers/amex.py`): el form de login de AMEX dejó de funcionar con `send_keys` de Selenium: el valor quedaba en el DOM pero React no lo registraba en su state interno, causando que el submit no hiciera nada. Se reemplazó por `_react_set_input` que usa `Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set` + evento `input` con `bubbles:true`, que sí sincroniza el state del componente controlado de React.

## 1.2.24

- **Scraper AMEX: diagnóstico post-submit y fallback React para inputs** (`scrapers/amex.py`): después del click en submit, se verifica que los campos realmente contengan los valores escritos (y si están vacíos, se reintenta con el setter nativo de React via `HTMLInputElement.prototype.value`). Se agrega chequeo intermedio 8s post-submit que captura errores visibles, estado del botón, contenido de iframes y snippet de texto de la página — todo incluido en el mensaje de error del panel si el portal no carga.

## 1.2.23

- **Scraper AMEX: diagnóstico detallado en errores de login** (`scrapers/amex.py`): cuando falla cualquier paso del login (campo usuario, contraseña, submit, o portal post-login), el error ahora incluye URL actual, título de página, y lista de inputs/buttons visibles en el DOM. Permite identificar si el fallo es por cambio de selectores, bloqueo anti-bot (Akamai), o redirect inesperado — antes solo decía "Message:" vacío.

## 1.2.22

- **Gráficos: opción "9 meses" en todos los selectores de rango** (`index.html`): se agregó la opción de 9 meses en los tres combos de selección de período — gráfico principal mes a mes (`#monthly-meses`), gráficos personalizados (`#cf-meses`), y configuración de meses por defecto en UI (`#ui-graf-meses`). Ahora las opciones son 3-6-9-12 (y 24 donde ya existía).

## 1.2.21

- **Período de cobro: aclarada la semántica de los overrides por mes** (`static/index.html`, `db.py`): los overrides `YYYY-MM = delta` se aplican según el **mes en que cae el movimiento** (el mes del sueldo), no el período destino. Esto confundía: un override `2025-12 = 5` no afectaba al sueldo del 26/11 (un movimiento de noviembre) y quedaba en noviembre. Se reescribió el texto de ayuda de "Excepciones por mes" con el ejemplo concreto (cobro 26-nov → `2025-11 = 5` para que cuente en diciembre; con `4` no cruza porque 26+4=30-nov) y se reforzó el comentario en `_mes_sql`. Sin cambios de lógica: el keying por mes del movimiento es el comportamiento deseado.

## 1.2.19

- **Presupuesto: gastos USD incluidos en el total de cualquier categoría** (`db.py`): el `gastado` de cada categoría ahora suma ARS + USD × TC, independientemente de si el presupuesto está en ARS o USD. Antes, los gastos USD solo contaban si la categoría tenía presupuesto en USD; ahora una categoría con presupuesto en ARS que también tiene gastos en dólares (ej. Streaming con Netflix USD y una suscripción ARS) muestra el total real convertido. El desglose `gastado_usd` aparece en la UI siempre que haya gastos en dólares, no solo en categorías con presupuesto USD.

## 1.2.18

- **Presupuesto en USD con conversión a pesos** (`db.py`, `tc.py`, `routes/presupuesto.py`, `routes/config_route.py`, `user_config.py`, `scrapers/bbva.py`, `scrapers/amex.py`, `static/app.js`, `static/index.html`, `static/style.css`): los presupuestos mensuales por categoría ahora soportan moneda USD. Por categoría se puede elegir ARS o USD via un dropdown inline. El TC se obtiene automáticamente de dolarapi.com (tipo configurable: tarjeta/oficial/blue, default tarjeta) y se muestra en el header del tab; al comparar contra el real, los gastos USD se convierten al TC almacenado en cada transacción (`gastos.tc_ars`) o al TC actual como fallback. El resumen muestra también totales en USD brutos para presupuesto y gasto real. Los scrapers AMEX y BBVA ahora almacenan el TC del momento en cada transacción USD importada.

## 1.2.17

- **Settlement report MP: desactivar notificaciones por email** (`scrapers/mercadopago.py`): `_ensure_settlement_config` ahora también vacía el campo `notifier_emails` del config del settlement report cuando está no-vacío, evitando que MP envíe un email por cada reporte generado. El PUT se hace en una sola llamada junto con la adición de `EXTERNAL_REFERENCE` si corresponde; si ambos ya están correctos, no se hace ninguna llamada extra.

## 1.2.20

- **Refresco live de gastos y gráficos** (`static/app.js`): el refresco automático de widgets ahora también actualiza la tabla de gastos, gráficos, presupuesto y cuentas (usa `refreshAfterDataChange()` completo). Cuando termina un import o scraper, los nuevos gastos aparecen solos sin Ctrl-R. Si el usuario está editando una celda en la grilla de gastos, el refresco omite la tabla para no perder la edición en curso y solo actualiza saldos y vencimientos.

## 1.2.16

- **Refresco automático de widgets** (`static/app.js`, `static/index.html`): los chips de saldo y vencimientos se actualizan en background sin recargar la página. Se agrega un `setInterval` configurable (nueva pref `widget_refresh_mins` en Config → Interfaz → "Refresco de widgets", opciones 2/5/10/15/30 min o desactivado, default 5 min) que llama a `loadSaldos()` y `loadVencimientos()` mientras no haya un scrape corriendo. Además, un listener `visibilitychange` refresca los widgets al instante cuando el usuario vuelve al tab tras dejarlo en background. Ambos mecanismos combinados evitan que los chips queden en amarillo por datos obsoletos al dejar la app abierta.

## 1.2.15

- **Rebrand a "SnapBudget"** (`config.yaml`, `rootfs/app/main.py`, `static/index.html`, `static/quick.html`, `static/manifest.json`, `static/sw.js`, `routes/auth.py`, `routes/admin.py`, `routes/push.py`, `DOCS.md`, `DESIGN.md`): el nombre visible de la marca pasa de "Finance Me" a "SnapBudget" en todos los puntos de UI: `<title>`, `apple-mobile-web-app-title`, manifest PWA (estático y dinámico), navbar, pantalla de login/registro, nombre del sender en push notifications, y filename del backup `.zip`. También se actualiza el proyecto Capacitor (`snap-budget-mobile/`): `appName`, `appId` (`ar.com.sbsoft.snapbudget`), `package.json` y `README.md`. El slug del add-on (`gastos_tarjetas`), el nombre de la carpeta del add-on y todos los términos de dominio no se tocan.

## 1.2.14

- **Settlement report MP — umbral configurable desde la UI** (`scrapers/mercadopago.py`, `scraper_credentials.py`): el umbral para solicitar un nuevo reporte de liquidaciones (antes hardcodeado en 4h, luego en 1h) pasa a ser configurable desde Config → Scrapers → MercadoPago → "Settlement report — umbral (horas)". Default: 1h. Se pasa como parámetro `stale_hours` a `_fetch_settlement_report`.

## 1.2.13

- **Enriquecimiento retroactivo de transferencias MP** (`scrapers/mercadopago.py`, `scrapers_db.py`): `_enrich_transfer_names` solo resolvía nombres en el momento de importar; transferencias ya en la DB quedaban como "Transferencia: Varios [id:xxx]". El nuevo método `_retroactive_enrich_transfers` consulta la DB buscando movimientos_raw de mercadopago con ese patrón, llama a `GET /v1/users/{collector_id}` para cada ID único y actualiza la descripción en `movimientos_raw` y en `gastos` (respetando `descripcion_editada` si el usuario la editó manualmente). Se ejecuta en cada run del scraper MP.

## 1.2.12

- **Fix settlement report MP — umbral 4h en lugar de "solo una vez por día"** (`scrapers/mercadopago.py`): las transferencias a CBU externo solo aparecen en el settlement report (no en `/v1/payments/search`). El código anterior comparaba solo por fecha, así que si ya había un reporte de hoy (ej. 01:48) no solicitaba uno nuevo aunque el scraper corriera a las 20:14 y hubiera transferencias de las 11:39. Ahora `_download_latest_settlement` devuelve el `datetime` completo del reporte, y se solicita uno nuevo si el existente tiene más de 4 horas. El log muestra la antigüedad en minutos cuando no se solicita (`"reporte de hace N min, no se solicita nuevo"`).

## 1.2.11

- **Fix Cocos — paginación via campo `pagination`** (`scrapers/cocos.py`): la paginación se leía de `batch[0].get("total_items")` (dentro de cada movimiento), pero el campo correcto está en `data.pagination.total_items` / `total_pages` / `curr_page` a nivel de respuesta. Ahora el loop de páginas usa `curr_page >= total_pages` como condición de corte. El log de debug muestra `total_items` y `total_pages` en lugar de las claves JSON crudas.

## 1.2.10

- **Fix Cocos — account_id faltante en sesión reutilizada** (`scrapers/cocos.py`): cuando la sesión guardada tiene `access_token` pero `account_id` vacío (sesiones antiguas anteriores al fix de 1.2.4), el scraper ahora detecta el vacío y llama a `GET /api/v1/users/me` para obtenerlo, actualiza el archivo de sesión, y continúa sin re-login. El método `_fetch_account_id_sync` se extrae como helper reutilizado también desde `_full_login_sync`.

## 1.2.9

- **Debug Cocos account_id y paginación** (`scrapers/cocos.py`): el log ahora muestra el `account_id` que se está usando en el header `x-account-id`, el objeto `pagination` de la respuesta, y el JSON completo cuando `data` viene vacío. También se restauran `date_from=` y `date_to=` vacíos en el request (igual que el browser).

## 1.2.8

- **Debug Cocos movimientos** (`scrapers/cocos.py`): el scraper devolvía "Sin movimientos" sin explicar por qué. Ahora loguea la estructura de la respuesta (días recibidos, primer día, balance, claves JSON) siempre en el primer page, y muestra el body raw si la respuesta no es JSON o tiene estructura inesperada. También se eliminan `date_from`/`date_to` vacíos del request (se enviaban como strings vacíos que podían alterar la URL).

## 1.2.7

- **Fix Cocos — filtro de fecha client-side** (`scrapers/cocos.py`): la API de `cash_movements` ignora los parámetros `date_from`/`date_to` cuando se envían con valores (devuelve vacío); el HAR muestra que la app los envía vacíos (`date_from=&date_to=`). Ahora se envían vacíos y el filtro por período se aplica client-side comparando `execution_date` contra el rango configurado.

## 1.2.6

- **Fix Cocos — endpoint correcto de movimientos** (`scrapers/cocos.py`): el endpoint real que usa la app es `GET /api/v1/wallet/cash_movements?currency=ARS&date_from=&date_to=&limit=50&offset=0`, no `/api/v1/transfers` (que devolvía 404). Respuesta: `{data:[{executionDate, balance, cashMovements:[...]}]}`. Cambios: (1) endpoint corregido con paginación offset-based (50/página), (2) campo de monto cambia de `amount` a `quantity` (negativo = egreso), (3) saldo ARS se lee de `data[0].balance` sin llamada extra a portfolio, (4) descripción compuesta `description — detail`, (5) dedup key: `cm_{id_cash_movement}` > `tk_{id_ticket}` > clave sintética, (6) removida llamada 404 a `wallet/portfolio`, (7) removido header `apikey: ""` que no envía la app.

## 1.2.5

- **Fix settlement report MP — mapeo de columnas xlsx en español** (`scrapers/mercadopago.py`): el xlsx que MP envía por mail usa encabezados en español (`TIPO DE OPERACIÓN`, `PAGADOR`, `DETALLE DE LA VENTA`, etc.) en lugar de los nombres ingleses que espera el parser (`TRANSACTION_TYPE`, `PAYER_NAME`, `DESCRIPTION`, etc.). `_settlement_bytes_to_rows` ahora mapea los 16 encabezados conocidos al nombre canónico en inglés y normaliza también los valores de `TRANSACTION_TYPE` (ej. `"Pago aprobado"` → `"SETTLEMENT"`, `"Retiro"` → `"WITHDRAWAL"`).

## 1.2.4

- **Fix Cocos "Account ID is required"** (`scrapers/cocos.py`): después del login TOTP, llama a `GET api/v1/users/me` para obtener `id_accounts[0]` y lo incluye como header `x-account-id` en todas las llamadas de API. El account_id se persiste en el session file para evitar la llamada extra en runs subsiguientes.

## 1.2.3

- **Fix settlement report MP — soporte xlsx** (`scrapers/mercadopago.py`): MP cambió el formato del settlement report de CSV a xlsx binario. El código anterior intentaba leerlo como texto y fallaba con "new-line character seen in unquoted field". Ahora `_download_settlement_file` retorna `bytes` y el nuevo helper `_settlement_bytes_to_rows` detecta el formato por magic bytes: si empieza con `PK` (ZIP/xlsx) lo parsea con `openpyxl`; si no, lo decodifica como CSV con separador `;`. Ambos formatos producen la misma lista de dicts para `_parse_settlement_csv`.

## 1.2.2

- **Fix Cocos Cloudflare 403** (`scrapers/cocos.py`, `requirements.txt`): reemplazada la implementación httpx por `cloudscraper` (mismo approach que pyCocos) para bypassear el WAF Cloudflare que protege `api.cocos.capital`. Toda la lógica HTTP pasa a sync y se ejecuta via `asyncio.to_thread`. Dependencia nueva: `cloudscraper>=1.2.71`.

## 1.2.1

- **Fix CocosScraper** (`scrapers/cocos.py`): faltaba implementar el método abstracto `scrape()` heredado de `BaseScraper` — impedía instanciar la clase.

## 1.2.0

- **Scraper Cocos Capital** (`scrapers/cocos.py`, `scraper_credentials.py`, `scraper_scheduler.py`, `requirements.txt`): nuevo scraper REST para Cocos Capital. Autenticación JWT vía Supabase GoTrue con 2FA TOTP automático (requiere TOTP secret key del usuario). Flujo: email+password → token phase-1 → challenge TOTP → token final. Refresh automático de sesión guardada en `/data/sessions/cocos.json`. Importa movimientos de cuenta (`api/v1/transfers`) y saldo/tenencias (`api/v1/wallet/portfolio`). Debug log muestra estructura del primer movimiento para verificar integración. Dedup via `transaction_id` en `raw_data`. Dependencia nueva: `pyotp>=2.9.0`.

## 1.1.0

- **Resolución de nombres en transferencias MP salientes** (`scrapers/mercadopago.py`): para cada transferencia saliente (`money_transfer` egreso), el scraper intenta resolver el nombre del receptor via `GET /v1/users/{collector_id}`. Si la API responde con nombre y apellido, la descripción pasa de `"Transferencia: Alquiler [id:123456]"` a `"Juan Pérez — Transferencia: Alquiler"`, permitiendo clasificarla con reglas de categorización. Best-effort: si la llamada falla (403, 404, error de red), la descripción queda con el `[id:xxx]` previo.

## 1.0.9

- **Detección automática de pagos manuales** (`db.py`, `routes/pagos.py`, `static/app.js`, `static/style.css`): para cada pago pendiente, el backend busca gastos que coincidan por monto (±tolerancia), fecha (±N días) y categoría (si el pago la tiene definida). Usa la misma config `venc_pago_match_*` de Config → Vencimientos. En la tabla, la columna Estado muestra el chip 🔍 Detectado (fondo amarillo) y aparece un botón `+` que expande un panel con el detalle del gasto encontrado y el botón "✓ Confirmar pagado".

## 1.0.8

- **Tabla debug forecast eliminada** (`db.py`, `static/app.js`): removida la tabla de desglose temporal, ya cumplió su propósito.

## 1.0.7

- **Fix doble conteo en presupuesto forecast** (`db.py`): el total del presupuesto ahora suma solo las categorías hoja (sin descendientes con presupuesto propio), evitando que el padre y sus hijos se cuenten múltiples veces. En la tabla debug, las categorías padre (roll-up) se muestran tachadas para identificarlas.

## 1.0.6

- **Forecast debug en modo Presupuesto** (`db.py`, `static/app.js`): debajo del gráfico aparece una tabla con dos columnas — categorías del presupuesto con su monto mensual, y categorías con historial pero sin presupuesto con su promedio mensual. Permite identificar exactamente qué está inflando el componente "histórico sin presupuesto".

## 1.0.5

- **Fix: categorías especiales se expanden a sus hijos** (`db.py`): `get_special_categorias()` ahora incluye todos los descendientes de cada categoría marcada como especial, no solo el nodo raíz. Esto corrige un doble conteo en stats y forecast donde los pagos de tarjeta y transferencias intercuentas (hijos de "Pagos Especiales") se filtraban del presupuesto pero no del histórico por no tener `especial=1` propio. El fix aplica a todos los callers: `monthly_summary`, `stats_monthly_by_category`, ambos modos de forecast, etc.

## 1.0.4

- **Forecast: período actual excluido del histórico** (`db.py`): el período de cobro en curso (que aparecía casi vacío creando un "bache") se excluye del histórico y pasa a ser el primer punto de la proyección, tanto en modo regresión como en modo presupuesto.
- **Forecast: excluir categorías expande a subcategorías** (`db.py`): al excluir una categoría de ingresos, ahora se excluyen automáticamente también todas sus subcategorías descendientes. Aplica a ambos modos de forecast.

## 1.0.3

- **Forecast modo "Presupuesto + Histórico"** (`db.py`, `routes/stats.py`, `static/app.js`): nuevo modo de proyección que reemplaza la regresión lineal global por una estimación por categoría: las categorías con presupuesto configurado usan el monto mensual del presupuesto; las categorías sin presupuesto usan el promedio histórico de los últimos N meses cerrados. Los ingresos siguen siendo promedio simple. El selector "Modo" en el header del gráfico Forecast permite alternar entre "Regresión" (comportamiento anterior) y "Presupuesto + Histórico" (nuevo). En modo presupuesto, el tooltip de cada punto proyectado muestra el desglose presupuesto vs. histórico sin presupuesto.

## 1.0.2

- **Fix doble dropdown en categoría de pagos manuales** (`static/index.html`): el campo `pago-cat` tenía `list="cat-datalist"` (datalist nativo del browser) simultáneo al dropdown custom de `_setupCatAC`, lo que mostraba dos selectores superpuestos. Se eliminó el atributo `list`, dejando solo el dropdown jerárquico propio de la app.

## 1.0.1

- **Categoría en pagos manuales** (`static/index.html`, `static/app.js`, `routes/rules.py`): el formulario de Pagos / vencimientos manuales ahora incluye un campo Categoría con autocomplete (mismo dropdown que el resto de la app). Al salir del campo Descripción, si Categoría está vacía, se consulta automáticamente las reglas de categorización y se pre-rellena si hay match. La columna Categoría aparece también en la tabla de pagos. Al editar un pago existente se carga la categoría guardada.

## 1.0.0

Primera versión estable. Consolidación de todas las funcionalidades desarrolladas desde el prototipo inicial: importación de resúmenes PDF (AMEX, BBVA Mastercard/Visa/Cuenta, Galicia, MercadoPago), scrapers automáticos con schedule, categorización por reglas, presupuesto mensual, gráficos, conciliación de transferencias, gestión de pagos, widget de vencimientos, colores y nombres cortos por cuenta, selectores de color en Config → Interfaz, diseño responsivo y guía de diseño documentada en `DESIGN.md`.

## 0.10.12

- **Visibilidad de categorías unificada entre Presupuesto y Categorías** (`static/app.js`): en la tab Presupuesto las categorías padre ahora usan `<strong>` + caret `▸` y las hijas usan `padding-left:1.6rem` sin reducción de font-size, igualando el estilo de la tab Categorías. Antes Presupuesto usaba `font-weight:600` inline y `font-size:.9em` en las hijas, produciendo un aspecto diferente.
- **Selector de padre en Categorías simplificado** (`static/app.js`): la opción vacía del combo "Categoría padre" cambia de `"— Sin padre —"` a `"—"`, más limpio visualmente.

## 0.10.11

- **BBVA Cuenta: año correcto al cruzar diciembre→enero** (`parsers/bbva_cuenta.py`): el parser detectaba el año buscando el primer `20XX` en el PDF, pero los extractos de enero incluyen fechas de débito de diciembre del año anterior (ej. `"26/12/2025"`) antes de llegar a la referencia `"información al: 23/01/2026"`. Resultado: todas las transacciones de enero quedaban etiquetadas como 2025. Fix: `_detect_close_date` busca primero el patrón `"información al: DD/MM/YYYY"` que BBVA imprime en la sección de Transferencias (más confiable); luego `_parse_date_dm` usa lógica de cruce de año: mes ≤ close_month → close_year, mes > close_month → close_year − 1. Con esto "02/01" → 2026-01-02 y "26/12" → 2025-12-26.
- **Config → Interfaz: uniformidad visual de combos** (`static/index.html`): "Botones de Pagos" usaba `ui-color-row` en lugar de `ui-pref-row`, lo que hacía que el combo se viera más angosto que los otros selectores del panel. Corregido.

## 0.10.10

- **Color y nombre corto por cuenta** (`db.py`, `routes/cuentas.py`, `static/app.js`, `static/style.css`): cada cuenta ahora tiene dos campos opcionales — `color` (color hex del badge) y `short_name` (etiqueta corta para el badge). Se editan en la tab Cuentas → fila "🎨 Color badge / 📛 Nombre corto" dentro del panel expandido de cada cuenta. Al guardar, todos los badges de esa fuente (grilla de gastos, ventana de transferencias, cuotas) muestran el color y la etiqueta configurados. Sin color configurado, el badge sigue usando la clase CSS del banco. Se agregan columnas `color TEXT` y `short_name TEXT` a la tabla `cuentas` vía migración `ALTER TABLE`; la API `PUT /cuentas/{fuente}` ya las acepta.
- **Badges on the fly al guardar apariencia** (`static/app.js`): `saveCuentaDisplay` ahora hace `await loadSaldos()` antes de `loadGastos()` para asegurar que `_widgetCuentas` esté actualizado antes de re-renderizar la grilla; antes los badges mostraban el color viejo hasta dar refresh manual.

## 0.10.9

- **BBVA: fecha de cierre autoritativa para `mes_resumen` e instalamentos** (`parsers/bbva.py`, `scrapers/bbva.py`): dos bugs relacionados causaban que un resumen de Enero 2026 quedara etiquetado como "enero 25":
  1. `_detect_vencimiento_bbva` solo buscaba la línea inmediatamente siguiente al header "CIERRE ACTUAL VENCIMIENTO ACTUAL"; si había una línea en blanco entre el header y los datos (formato PDF variable), `stmt_date` quedaba `None` y las cuotas (`C.13/24`) conservaban su fecha original de compra (ej. Ene-25) en lugar de ser remapeadas al mes del cierre.
  2. `mes_resumen` se calculaba por moda de fechas de transacciones, pero en un resumen de enero 2026 la mayoría de cargos son de diciembre 2025 (y sin `stmt_date`, las cuotas viejas dominan).
  - **Fix 1**: `_detect_vencimiento_bbva` ahora escanea hasta 3 líneas después del header antes de rendirse.
  - **Fix 2**: `BBVAParser.parse()` guarda `stmt_date` como `self.fecha_cierre`; `_import_resumen` la usa como `mes_resumen` autoritativo si está disponible, tanto para la guarda de "ya importado manualmente" como para el registro de la importación.

## 0.10.8

- **6 nuevos selectores de color en Config → Interfaz** (`static/app.js`, `static/index.html`, `static/style.css`): se agregan controles de color para egreso/ingreso (grilla de gastos y gráfico mes a mes), presupuesto/real (gráfico Presupuesto vs Real), y urgente/pronto (chips y tarjetas de vencimientos). Los 6 valores nuevos se guardan en `ui_colors`, se aplican como variables CSS (`--color-egreso`, `--color-ingreso`, `--color-presup`, `--color-real`, `--color-venc-urg`, `--color-venc-pronto`) en `applyUiColors()`, y los gráficos se re-renderizan al guardar. Se agrega `_cssVar()` para leer variables CSS desde Chart.js. La paleta de donuts queda para una tanda separada.

## 0.10.7

- **Subir PDF ya no pisa el saldo de la cuenta** (`routes/upload.py`): al importar un PDF manualmente se aplicaba el `saldo_final` que detecta el parser (`upsert_cuenta_saldo`), así que subir un resumen histórico cambiaba el saldo actual con un valor viejo. Ahora el saldo lo actualiza **solo el scraper** (vía API → `result.saldos`); la subida manual no lo toca. El parser sigue calculando `saldo_final` para uso interno (dedup).
- **Guía de diseño: i18n, color/short-name por cuenta y saldo** (`DESIGN.md`): se documentó la propuesta de internacionalización (no hardcodear strings, diccionario por idioma, selector en Config → UI, migración gradual) como dirección para que todo lo nuevo quede i18n-ready; más las convenciones de color y short_name por cuenta (en la tab Cuentas, no en Interfaz) y quién actualiza el saldo. Roadmap de UI pendiente listado al final.

## 0.10.6

- **Emojis faltantes en botones de texto + guía de diseño documentada** (`static/index.html`, `static/app.js`, `DESIGN.md`, `CLAUDE.md`): se agregó emoji a los ~15 botones que eran solo texto, siguiendo un vocabulario consistente: ↩ Restablecer (×7), 🔄 Reaplicar / Reaplicar a todos, 🔑 Ver keywords, 🔍 Buscar, ✓ Confirmar pares, ⇄ Marcar solo este, ➕ Agregar todas a cola (×2), 🔔 Activar notificaciones, 🔕 Desactivar, 🧹 Resetear duplicadas, 🧾 Movimientos, 🏷️ Categorizar seleccionados. Para los botones cuyo texto se reescribe desde JS (Buscar, Reaplicar, Reaplicar a todos, Ver/Cerrar keywords) el emoji se agregó también en las asignaciones de `textContent` para que no se pierda. No se tocaron los botones `+` / `×` / `✕`. Se creó **`DESIGN.md`** con las convenciones de UI (clases de botón, vocabulario oficial de emojis, patrón de toggles icono/texto, estados de chip del scraper, colores, fechas en TZ del browser, refresco unificado) y un puntero MANDATORY en `CLAUDE.md` para que todo lo futuro siga ese estilo. El refactor estructural (toggle global icono+texto para todos los botones) queda documentado como pendiente en DESIGN.md.

## 0.10.5

- **Botones de Pagos: toggle propio, iconos unificados y "Reabrir"** (`static/app.js`, `static/index.html`, `static/style.css`):
  - **#1 Desacople + 2º toggle:** los botones de acción de la tabla de Pagos usaban las clases `.tab-icon`/`.tab-text` de la navegación, así que el modo de display de las pestañas (íconos/texto/ambos) los afectaba sin querer. Ahora tienen clases propias `.pa-icon`/`.pa-text` y un toggle dedicado en Config → UI ("Botones de Pagos": íconos+texto / solo íconos / solo texto), persistido en `ui_prefs.pago_btn_mode`, independiente del de pestañas.
  - **#3 Iconos unificados:** se reemplazaron los emoji de estilo mixto (✏️/🗑) por glifos monocromos que heredan el color del botón: ✓ Pagado, ■ Finalizar, ✎ Editar, 🗑︎ Borrar.
  - **#4 Reabrir:** las filas marcadas como pagadas ahora muestran un botón "↺ Reabrir" que las vuelve a 'pendiente' (vía `PUT /pagos/{id}` con `estado:"pendiente"`, que ya existía), para revertir un "Pagado" puesto por error sin tener que borrar y recrear.

## 0.10.4

- **Chips de cuenta: estado "corriendo" (azul) + auto-refresh + reset de estado colgado** (`static/app.js`, `static/style.css`, `scrapers_db.py`, `main.py`): los chips de saldo/vencimiento ya marcaban el estado del scraper con borde verde/amarillo/rojo; se agrega un cuarto estado **azul pulsante** cuando el scrape está corriendo (`scraper_estado === "running"` → `_scraperStatusColor` devuelve `"run"`). Mientras alguna cuenta esté corriendo, la vista se **refresca sola cada 8s** (`_scheduleScrapeAutorefresh`) y para cuando termina, así el chip cambia de azul a verde/rojo sin recargar — útil para ver de una sola vista si es seguro actualizar el add-on. Además, como un update/reinicio del add-on mata el scrape y dejaba el estado pegado en `running`, ahora al primer request de cada usuario tras arrancar el proceso se resetean los `running` colgados a `idle` (`reset_stale_running`, llamado desde el middleware junto a `init_db`).

## 0.10.3

- **BBVA Caja de Ahorro: enriquecer descripción de transferencias con la tabla de detalle** (`parsers/bbva_cuenta.py`): en la sección de movimientos las transferencias figuran como "TRANSFERENCIA" genérico, pero el PDF trae al final una sección "Transferencias" (subtablas RECIBIDAS y ENVIADAS) con la contraparte. Ahora el parser lee esa tabla (`_parse_transfer_details`) y enriquece la descripción correlacionando por fecha (DD/MM) + importe: las recibidas suman la empresa/servicio de origen (ej. "TRANSFERENCIA — INVERTIRONLINE", "TARJ VIRTUAL BB") y las enviadas el apellido del destinatario (ej. "TRANSFERENCIA CAP101 … — SAENZ"). Las "TRANSFERENCIA INMEDIATA COE" (CVU/interbancarias) no figuran en esa tabla, así que quedan genéricas. Validado contra el resumen real de abril 2026 (7 transferencias enriquecidas correctamente). Como la descripción resultante es más específica que la genérica del scraper web, gana en la conciliación PDF↔web (0.8.99).

## 0.10.2

- **BBVA resúmenes: no importar resúmenes con fecha de cierre no parseable** (`scrapers/bbva.py`, `scrapers/bbva_tarjetas.py`): tanto en Caja de Ahorro como en VISA/MC, el filtro de ventana era `if cierre and cierre < cutoff: continue` y luego `candidatos.append((cierre or date.min, …))`. Si `_parse_cierre` devolvía None (fecha no parseable), el `and` se cortocircuitaba, NO se salteaba, y el resumen se agregaba con `date.min` → se importaba aunque estuviera fuera de la ventana (así se podía colar un resumen viejo, ej. enero 2025). Ahora, si la fecha de cierre no se puede parsear, se saltea con log y no se importa (mismo criterio que el backfill de AMEX). Nota: si `resumenes_meses` está seteado alto (≥ ~17 meses), un resumen de enero 2025 SÍ cae dentro de la ventana y se importa a propósito — eso no es bug.

## 0.10.1

- **Gráfico "mes a mes": selector de meses a mostrar (3/6/12, persistido)** (`static/index.html`, `static/app.js`): se agrega un combo chico en el encabezado del gráfico de movimientos ARS para elegir cuántos meses hacia atrás mostrar (3, 6 o 12). El valor se guarda en localStorage (`monthly_meses`, default 12) y se aplica recortando los últimos N meses del set (los datos vienen de más viejo a más nuevo → `slice(-N)`). El dropdown del filtro de mes sigue listando todos los meses; el recorte es solo visual del gráfico.

## 0.10.0

- **AMEX: fix de fondo del año de las transacciones (gastos en el futuro)** (`parsers/amex.py`, `parsers/utils.py`): los renglones de transacción de AMEX no traen año, y el parser lo tomaba de `re.search(r"Facturación\s+\d{2}/\d{2}/(\d{2,4})")` sobre cada fila — pero esa regex **nunca matchea** (en el PDF real la palabra "Facturación" está en la fila de encabezado y la fecha en una fila de datos posterior), así que el año quedaba en el default hardcodeado `2026` para TODAS las transacciones de TODOS los resúmenes. Efecto: en el resumen que cierra en enero, los cargos de diciembre se fechaban como diciembre 2026 (futuro); un resumen de diciembre 2025 quedaba entero en 2026; etc. Ahora el año se ancla a la **fecha de cierre real** (Facturación), que se lee de la fila `Titular … Facturación Vencimiento` (`_detect_fact_venc_amex` devuelve cierre y vencimiento), con regla de cruce de año: si el mes de la transacción es posterior al mes de cierre, pertenece al año anterior (cargos de diciembre en el resumen de enero → diciembre del año previo). Nunca se generan fechas futuras. Nuevo helper `parse_date_dmy_anchored` en utils. Validado contra los resúmenes reales Mar26/Abr26 (sin regresión, sin fechas futuras).
- **Nota:** los resúmenes AMEX importados antes de este fix quedaron con años mal (sobre todo los que cruzan diciembre/enero y los de 2025). Conviene borrar esas importaciones y re-importarlas (o re-correr el backfill) para que tomen las fechas corregidas.

## 0.9.9

- **BBVA resúmenes: dedup de extractos en el fetch multi-año** (`scrapers/bbva.py`): cuando la ventana cruza años, `_fetch_extractos` consultaba la API una vez por año, pero la API de BBVA ignora el parámetro `fecha:año` y siempre devuelve los últimos ~100 resúmenes — así que cada año traía la MISMA lista y todo se procesaba dos veces (se veía cada `[cuenta] al día` duplicado, y en teoría se intentaría descargar dos veces un resumen nuevo). Ahora se deduplica por `reporte` al acumular, y el log muestra por año solo el conteo (en la API / nuevos) más la lista única una sola vez, en vez de repetir ~100 líneas por año. No cambia qué se importa (el filtro de ventana por fecha de cierre ya era correcto).

## 0.9.8

- **Log unificado: timestamp en la TZ del browser** (`static/app.js`): `app_log.py` guarda `ts` como `datetime.now(timezone.utc)` ("YYYY-MM-DD HH:MM:SS", UTC sin sufijo) y el frontend lo mostraba crudo → se veía en UTC. Se agrega `_fmtLogTs()` que interpreta el valor como UTC y lo muestra en la zona horaria del browser, manteniendo el formato ordenable con segundos. El resto de timestamps de la UI (último intento/OK del scraper vía `_fmtTs`, `scraped_at`, próximo run vía `isoformat()` con offset) ya convertían bien — no requerían cambios.

## 0.9.7

- **Refresco unificado del frontend tras cambios de datos** (`static/app.js`): varios handlers refrescaban solo una parte de la UI, dejando la grilla de Gastos, los gráficos de la solapa Gráficos (donut + presupuesto vs real) o el autocomplete de categorías desactualizados hasta cambiar de solapa o recargar. Se agrega un helper `refreshAfterDataChange()` que recarga todo el set relevante (gastos, gráfico mensual, gráficos por categoría, presupuesto vs real, saldos, jerarquía+categorías, importaciones, vencimientos, cuentas) y se cablea en todos los puntos de mutación: corrida de scraper (antes solo refrescaba cuentas+saldos → ahora también gastos y gráficos), import de PDF y borrado masivo (faltaban los gráficos de la solapa), guardar categorías en Config (antes no refrescaba `_catList`/jerarquía → la categoría nueva no aparecía en la grilla ni se podía asignar), alta de movimiento manual, borrado individual, aplicar reglas, marcar/desmarcar transferencias y toggle de especiales. La edición de una sola celda (`saveCategoria`) refresca solo los gráficos (no `loadGastos`) para no perder ediciones en curso de otras filas.

## 0.9.6

- **Autocomplete de categorías: no se cierra al usar su scrollbar** (`static/app.js`): el dropdown (`.cat-ac`) tiene scroll propio (max-height 220px); al arrastrar su barra el `mousedown` caía sobre el contenedor, el input perdía foco y el `blur` lo cerraba. Ahora un `mousedown` sobre el contenedor (no sobre un item) hace `preventDefault` para no soltar el foco, así se puede scrollear la lista sin que desaparezca.
- **Autocomplete de categorías: buscar por el nombre del parent** (`static/app.js`): al tipear el nombre de una categoría padre (ej. "transporte") ahora aparecen también sus subcategorías, aunque no coincidan literalmente con el texto. El filtro mantiene un ítem si su propio nombre matchea O si el nombre de su parent matchea (y conserva el parent de los hijos para que el árbol siga legible). Útil para elegir una subcategoría sin recordar su nombre exacto.

## 0.9.5

- **AMEX backfill: expandir todos los paneles del acordeón dentro de la ventana** (`scrapers/amex.py`): los resúmenes están agrupados en acordeones por período (ej. "2026" y un panel colapsado "mar.-dic. 2025"). El código solo expandía el primer panel, así que un backfill largo nunca llegaba a los resúmenes de años anteriores. Ahora se recorren todos los botones `header-YYYY-...`, se expanden los colapsados cuyo año alcance la ventana (`_resumenes_cutoff`), y tras cada expansión se extraen y acumulan los links (dedup por URL) — robusto ante acordeones que colapsan el panel anterior al abrir otro. Paneles de años fuera de la ventana no se expanden (eficiencia).

## 0.9.4

- **AMEX backfill: fix resumen fuera de ventana por mes "sept"** (`scrapers/amex.py`): el título de los links de resumen usa "sept" (además de "sep"), pero `titleToDate` solo mapeaba "sep" → la fecha quedaba vacía → el filtro de ventana (que solo aplicaba con fecha) no lo excluía y se importaba un resumen viejo (ej. cierre 30/09/2025 al pedir 5 meses), arrastrando consumos de agosto. Fix: el lookup de mes normaliza a 3 letras (`slice(0,3)`), así "sept"→"sep". Además, salvaguarda: si un link no tiene fecha parseable se saltea (con log) en vez de importarse, para no traer resúmenes que no se pueden ubicar en la ventana.

## 0.9.3

- **Título dinámico en el chart Presupuesto vs real** (`static/index.html`, `static/app.js`): el título ahora muestra los totales del mes seleccionado en el combo box, ej. "Presupuesto (1.2M) vs Real (980K)". Se calcula sumando las categorías top-level del mes (sin doble conteo) y se actualiza al cambiar el mes. El texto se envolvió en `<span id="bud-chart-title-text">` y se actualiza desde `loadBudgetChart` vía el nuevo helper `_updateBudChartTitle`; formato compacto K/M con `_fmtCompactKM`. Si no hay datos vuelve a "Presupuesto vs real".

## 0.9.2

- **Borrado individual de gastos: hard delete genuino** (`db.py`, `static/app.js`): se revierte el marcado `estado='ignored'` introducido en 0.9.1 (era sobre-ingeniería). `delete_gasto_any` vuelve a borrar el gasto y su `movimientos_raw` vinculado. El delete está pensado para duplicados o registros mal importados: en un duplicado hay 2 filas raw y al borrar una sobrevive la otra (el dedup saltea el movimiento → no vuelve); si es un movimiento real único y el scraper lo re-trae, se re-importa, lo cual es correcto porque el gasto existe. No toca la tabla `importaciones`, así que el flujo de resúmenes PDF (fuente de verdad) queda intacto. Mensaje del confirm actualizado.

## 0.9.1

- **Borrado individual no resucita por re-import** (`db.py`, `static/app.js`): `delete_gasto_any` hacía hard-delete del `movimientos_raw` vinculado, pero como el dedup de `insert_movimientos_raw` busca por monto+fecha sin filtrar estado, al borrar la fila el scraper la re-insertaba en la corrida siguiente (el movimiento sigue en la ventana) y el duplicado resucitaba. Ahora el raw NO se borra: se marca `estado='ignored'` y se le suelta el `gasto_id`. El dedup lo encuentra y lo saltea (no re-importa), `auto_import_unmatched` solo toma 'unmatched' (no lo importa) y la conciliación solo mira 'imported' (no lo toca). Clave: si el movimiento aparece en un resumen PDF, se importa igual como gasto nuevo, respetando que el PDF es la fuente de verdad. Mensaje del confirm actualizado.
- **Backfill de resúmenes PDF de AMEX (N meses configurable)** (`scrapers/amex.py`, `scrapers/base.py`, `scraper_credentials.py`): mismo campo `resumenes_meses` (default 1) ahora también en el scraper `amex`. Antes bajaba solo el resumen más reciente con transacciones (corte al primero); ahora itera los links de resúmenes e importa todos los que tengan fecha de cierre dentro de la ventana y no estén ya importados. El helper de ventana `_resumenes_cutoff` (cálculo de cutoff + clamp 1..24) se movió a la clase base `BaseScraper` para compartirlo entre AMEX y BBVA; `BbvaScraper._resumenes_window` ahora lo reutiliza.

## 0.9.0

- **Backfill de resúmenes PDF de BBVA (N meses configurable)** (`scrapers/bbva.py`, `scrapers/bbva_tarjetas.py`, `scraper_credentials.py`): hasta ahora el auto-import de resúmenes bajaba solo el más reciente (Caja de Ahorro) o el último por tipo (VISA/MC). Se agrega el campo `resumenes_meses` (default 1) a los scrapers `bbva` y `bbva_tarjetas`: con N>1 el scraper baja e importa todos los resúmenes con fecha de cierre dentro de los últimos N meses que aún no estén importados (los ya importados se saltean vía `importacion_exists`). Útil para backfill tras un reset de cuenta. `_fetch_extractos` acepta una lista de años para cubrir el cruce de año (ej. enero con N=3 consulta también el año anterior). Nuevos helpers `_resumenes_window` (calcula cutoff + años, clamp 1..24) y `_parse_cierre` (parsea `DD/MM/YYYY`) en la clase base `BbvaScraper`. La conciliación por monto+fecha de 0.8.99 hace que el backfill sea seguro: los movimientos web de los mismos períodos se concilian con los PDF en vez de duplicarse.

## 0.8.99

- **Conciliación PDF↔scraper por monto+fecha (no por descripción)** (`scrapers_db.py`): `consolidate_scraper_duplicates` exigía similitud de descripción > 60% para conciliar. Como el PDF de Caja de Ahorro trae descripciones genéricas ("Transferencia inmediata") y el scraper las trae específicas ("OPERACION EN EFECTIVO TARJE … AV. CORDOBA"), el match fallaba y quedaban ambos registros duplicados. Ahora matchea por fuente+moneda+monto (±0.02)+fecha (±5 días); la similitud de descripción y el número de cuota se usan solo como desempate cuando hay varios candidatos del mismo monto en la ventana. El match es uno-a-uno (cada gasto-PDF y cada gasto-scraper se usan a lo sumo una vez) para no colapsar N transacciones iguales en una. Al conciliar: gana el gasto-PDF, se preserva la categoría del scraper, y si la descripción del PDF es genérica y la del scraper específica, se copia la específica (mejor descripción gana).
- **Borrado individual de gastos de cualquier origen** (`db.py`, `routes/gastos.py`, `static/app.js`): se agrega `delete_gasto_any`, que borra un gasto sin importar su origen (manual/scraper/PDF) y hace hard-delete de sus `movimientos_raw` vinculados para que el scraper no lo re-importe. El endpoint `DELETE /gastos/{id}` pasa a usarlo (antes rechazaba todo lo que no fuera de cuenta manual). En la tab de Gastos el botón ✕ ahora aparece en todas las filas con estilo discreto (opacidad baja, se resalta en rojo al pasar el mouse) y un confirm que aclara el efecto sobre el re-import.

## 0.8.98

- **Fix: database is locked bajo carga concurrente** (`scrapers_db.py`): `_conn()` abría SQLite sin timeout ni WAL, y corría `_ensure_scraper_tables` (con 5 writes) en cada apertura de conexión. Con múltiples requests paralelos del UI se producía contención total. Corrección: `timeout=30`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=10000`, y `_ensure_scraper_tables` se corre solo una vez por DB-path por proceso (guard `_initialized_dbs`), igual que `db.py`.

## 0.8.97

- **Refactor: resúmenes PDF Caja de Ahorro se mueven al scraper `bbva`** (`scrapers/bbva.py`, `scrapers/bbva_tarjetas.py`, `scraper_credentials.py`): la lógica de descarga e importación de PDFs de la Caja de Ahorro Pesos pertenece al scraper de cuenta (`bbva`), no al de tarjetas. Los métodos `_fetch_extractos`, `_fetch_pdf_bytes`, `_import_resumen` y las 4 constantes de endpoint se mueven a `BbvaScraper` (clase base), de donde los heredan ambos scrapers. Se agrega `_scrape_resumenes_cuenta` a `BbvaScraper`, que filtra la lista de extractos para "CAJA DE AHORROS PESOS" y llama a `_import_resumen` con `parser_key=bbva_cuenta`. Se agrega el checkbox `auto_resumenes` al scraper `bbva` en `scraper_credentials.py`. En `bbva_tarjetas.py` se revierte el soporte de `CUENTA_ARS` en `_scrape_resumenes` (que quedó erróneamente en 0.8.96) y se restaura `len(done)==2`.

## 0.8.96

- **Feature: auto-importar resumen PDF de Caja de Ahorro Pesos BBVA** (`scrapers/bbva_tarjetas.py`): `_scrape_resumenes` ahora detecta también el extracto "CAJA DE AHORROS PESOS" en la lista de la API y lo importa con `parser_key=bbva_cuenta` / `fuente_target=bbva_cuenta`. Agrega `bbva_cuenta` a `_RESUMEN_PARSERS` para que `consolidate_scraper_duplicates` elimine los duplicados del scraper al importar el PDF. Actualiza el early-exit a `len(done)==3` (VISA+MC+CUENTA_ARS).

## 0.8.95

- **Fix: extractos BBVA — statusCode 500 "Esta transacción no puede ser realizada"** (`scrapers/bbva_tarjetas.py`): BBVA bloquea `POST /extractos/extractos` si el browser no está en la sección "Resúmenes" del SPA Angular. El fix navega a `#/private/summaries`, espera 4 s para que Angular inicialice el módulo, hace el gate-check `GET /viewerAdobePdf/verificacion` (que Angular ejecuta automáticamente), y recién entonces llama al endpoint de extractos — replicando el flujo real del browser confirmado en el HAR.

## 0.8.94

- **Diagnóstico: extractos BBVA vacíos** (`scrapers/bbva_tarjetas.py`): cuando la API `POST /extractos/extractos` devuelve HTTP 200 pero lista vacía, el log ahora muestra el `statusCode` interno del JSON y los primeros 500 caracteres del body para identificar si es un error de sesión, CSRF o estructura inesperada.

## 0.8.93

- **Fix: ContextVar de usuario no se propagaba al thread del scraper** (`scrapers/base.py`): `BaseScraper.run()` usa `loop.run_in_executor()` para correr el scraper Selenium en un thread pool, pero el ContextVar `_user_data_dir` (que apunta a la DB del usuario activo) no se propagaba al hilo — causaba `RuntimeError: _find_db_path() SIN contexto de usuario` en `consolidate_scraper_duplicates` y potencialmente escribía gastos en la DB global `/data/gastos.db` en lugar de la del usuario. Corregido con `ctx = contextvars.copy_context(); loop.run_in_executor(None, ctx.run, self._run_sync, config)`.
- **Fix: logging diagnóstico de pág1 eliminado** (`scrapers/amex.py`): se quita el log temporal `pág1={...}` agregado en 0.8.90 para depurar el parser de PDF AMEX, que ya no es necesario.

## 0.8.92

- **Fix: `categorize_by_rules` no devuelve tupla** (`scrapers/amex.py`, `scrapers/bbva_tarjetas.py`): ambos scrapers desempaquetaban `cat, fuente_cat = categorize_by_rules(...)` pero la función devuelve `Optional[str]`, no una tupla — causaba `TypeError: cannot unpack non-iterable NoneType object` al importar el primer PDF con 0 reglas que matcheen. Corregido a `cat = categorize_by_rules(...); fuente_cat = "regla" if cat else None`.

## 0.8.91

- **AMEX: campo `Account Key` en config del scraper para filtrar resúmenes por tarjeta** (`scraper_credentials.py`, `scrapers/amex.py`): sin `account_key` el portal `/statements` muestra los resúmenes de la tarjeta adicional (Platinum Credit Card, 31004) en lugar de la principal. Ahora hay un campo opcional "Account Key (Resúmenes PDF)" en la config del scraper AMEX; si está configurado, el scraper navega a `/statements?account_key=VALOR` mostrando solo los resúmenes de esa tarjeta. El valor se obtiene del HAR del portal AMEX (parámetro `account_key` en la URL de la petición a `/statements`).

## 0.8.90

- **AMEX: loguear primeros 300 chars de pág1 del PDF descargado** (`scrapers/amex.py`): diagnóstico para entender qué documento real devuelve la API de resúmenes antes de seguir asumiendo causas.

## 0.8.89

- **AMEX: reintentar hasta 3 PDFs si el primero tiene 0 transacciones** (`scrapers/amex.py`): el portal mezcla resúmenes de la Platinum Card y la Platinum Credit Card; el primero en el DOM puede ser el de la tarjeta con saldo cero. Ahora itera hasta 3 links recientes (deteniéndose en el primero con `count > 0`).

## 0.8.88

- **AMEX: fix return en IIFE de extracción de links + timeout 45s** (`scrapers/amex.py`): dos bugs en la extracción de links PDF. (1) La función JS de extracción usaba `(function() { ... })()` sin un `return` al nivel del script — Selenium's `execute_script` solo devuelve un valor cuando hay un `return` top-level; el IIFE sin `return` externo siempre devolvía `None` → `[]`. Corregido a `return (function() { ... })()`. (2) El `WebDriverWait` para esperar los links usaba 15s, pero el log confirmó que los links aparecen ~15–16s después de la navegación (la SPA los carga async); el timeout se amplió a 45s.

## 0.8.87

- **AMEX: usar indexOf en JS en lugar de selector CSS para links de resúmenes** (`scrapers/amex.py`): el diagnóstico de 0.8.86 confirmó que los links de `/servicing/v1/documents/statements/` están en el DOM (74 `<a href>` presentes, 5 con esa ruta), pero el selector CSS `a[href*="..."]` devuelve 0 resultados en esta SPA de React. La extracción ahora itera todos los `<a href>` con `document.querySelectorAll('a[href]')` y filtra por `.indexOf()` en JS, el mismo método que funciona en el diagnóstico. El `WebDriverWait` también fue actualizado para usar el mismo enfoque JS en lugar de un CSS selector.

## 0.8.86

- **AMEX: esperar links aunque el panel ya esté expandido** (`scrapers/amex.py`): cuando `aria-expanded="true"` en la carga inicial el scraper saltaba directo a buscar links sin esperar que el contenido cargase. Ahora siempre aplica un `WebDriverWait(15s)` post-panel (tanto si se clickeó como si ya estaba abierto). Además, cuando no se encuentran links el log ahora muestra hasta 5 hrefs candidatos con "document"/"statement"/"servicing" en su URL para poder diagnosticar el formato real que usa la página.

## 0.8.85

- **Conciliación: no reutilizar gastos ya importados** (`conciliacion.py`): `_conciliar_uno` excluye de sus candidatos los gastos que ya están vinculados a otro movimiento_raw con `estado='imported'` (misma fuente). Esto evita que 3 raws idénticos se "matcheen" todos al mismo gasto ya existente (quedando `matched` y nunca creando gastos nuevos). Ahora quedan `unmatched` → `auto_import_unmatched` crea los 3 gastos faltantes → total 4 gastos para 4 pagos idénticos.

## 0.8.84

- **Scraper: guard final para N transacciones idénticas** (`scrapers_db.py`): v0.8.83 solo corregía el `fallback_descriptor` pero el cross-date match (que corre después) seguía encontrando el mismo ID sin exclusión, resultando en `via unknown` y colapsando igualmente. Ahora hay un guard justo antes del bloque `if existing:` que descarta cualquier resultado cuyo ID ya esté en `_used_raw_ids`, sin necesidad de modificar cada query individual. El resultado: 4 transacciones idénticas el mismo día generan 4 filas separadas en `movimientos_raw`.

## 0.8.83

- **Scraper: dedup correcto para N transacciones idénticas el mismo día** (`scrapers_db.py`): el `fallback_descriptor` en `insert_movimientos_raw` hacía `LIMIT 1` sin discriminar entre runs, por lo que 4 pagos idénticos (mismo día, monto y descripción, sin timestamp) colapsaban a un solo registro en `movimientos_raw` y se perdían las otras 3. Ahora se mantiene un set `_used_raw_ids` por run: cada ID ya matcheado o recién insertado se excluye del `fallback_descriptor` en las iteraciones siguientes, lo que permite insertar N filas distintas para N transacciones idénticas.

## 0.8.82

- **BBVA: log de resúmenes encontrados por la API** (`scrapers/bbva_tarjetas.py`): `_fetch_extractos` ahora lista cada resumen disponible (producto, fechaCierre, reporte ID) antes de decidir si se baja o no. Antes solo decía `"N disponibles"` sin detalles, lo que no permitía distinguir entre "API devolvió vacío" (período aún abierto) y "encontró pero ya importados". Si la API devuelve 0, ahora dice explícitamente "la API no devolvió resúmenes para YYYY (período aún abierto o sin resúmenes emitidos)".

## 0.8.81

- **AMEX: click en acordeón antes de extraer links PDF** (`scrapers/amex.py`): el panel de resúmenes en `/statements` carga el contenido de forma lazy — los links PDF no están en el DOM hasta que se clickea el botón del acordeón. El scraper ahora espera que aparezca `button[id^="header-"]` (hasta 30s), y si `aria-expanded="false"` lo clickea antes de buscar los links. Si el panel ya estaba expandido (p.ej. sesión reciente), lo detecta por `aria-expanded="true"` y no lo clickea.

## 0.8.80

- **AMEX: espera inteligente para links PDF en /statements** (`scrapers/amex.py`): reemplaza el `time.sleep(10)` fijo por un `WebDriverWait(30)` que espera a que aparezca el primer `<a href*="/servicing/v1/documents/statements/">` en el DOM. Si el wait expira, intenta extraer links de todos modos. Cuando no hay links, loguea la cantidad de `<a href>` en la página y si el texto "Estado" está presente.

## 0.8.79

- **AMEX: descarga de resúmenes PDF vía DOM** (`scrapers/amex.py`): reescritura de la estrategia de `_scrape_resumenes`. La versión 0.8.78 intentaba llamar a `GET /servicing/v1/documents/info/statements` con un `account_token` de sesión que no está accesible desde el browser context de Selenium. La nueva estrategia navega a `/statements` (One App React SPA), espera 10s a que renderice, y extrae los links de descarga directamente del DOM con `document.querySelectorAll('a[href*="/servicing/v1/documents/statements/"]')`. Las URLs ya incluyen el token preautenticado (`?account_key=...&client_id=OneAmex`); se descargan con `fetch(..., {credentials:'include'})`. La fecha del resumen se parsea desde el atributo `title` en español (`"26 de may de 2026" → "2026-05-26"`). Se eliminó `_fetch_amex_statements` y las constantes `_EP_DOC_INFO`/`_EP_DOC_DL` ya no son necesarias.

## 0.8.78

- **AMEX: auto-descarga de resúmenes PDF** (`scrapers/amex.py`, `scraper_credentials.py`): nueva opción "Descargar resúmenes PDF automáticamente" en la config del scraper AMEX. Cuando está activa, en cada run el scraper navega a la sección Resúmenes del portal moderno de AMEX, obtiene la lista de resúmenes vía `GET /servicing/v1/documents/info/statements` y descarga el más reciente como PDF binario (igual técnica que BBVA: `arrayBuffer()` + `btoa()` en el browser). Antes de importar, verifica por nombre de archivo (`importacion_exists`) y por mes (`importacion_exists_mes`) para no duplicar resúmenes ya subidos manualmente. La importación aplica categorización por reglas y llama a `consolidate_scraper_duplicates`.

## 0.8.77

- **BBVA Tarjetas: corrección detección de resúmenes ya importados manualmente** (`scrapers/bbva_tarjetas.py`, `db.py`): la lógica de v0.8.76 derivaba el `mes_resumen` a partir de `fechaCierre` del extracto, lo cual era incorrecto para Mastercard (cierra el 21, así que las transacciones son en su mayoría del mes anterior). Ahora el chequeo de mes se hace *después* de parsear el PDF, usando el mes más frecuente entre las fechas reales de las transacciones, igual que hace `upload.py`. El scraper sólo registra el stub en `importaciones` y retorna 0 si ese `(fuente, mes_resumen)` ya existe.

## 0.8.76

- **BBVA Tarjetas: evitar reimportar resúmenes subidos manualmente** (`scrapers/bbva_tarjetas.py`, `db.py`): antes de descargar un resumen, el scraper ahora verifica si ya existe una importación para el mismo `(fuente, mes_resumen)` derivado de la `fechaCierre` del extracto. Si el usuario ya subió el PDF manualmente ese mes (con cualquier nombre de archivo), el scraper no vuelve a importarlo. Además registra el `reporte` ID en `importaciones` para que la siguiente ejecución entre por el chequeo rápido por nombre de archivo.

## 0.8.75

- **BBVA Tarjetas: auto-descarga de resúmenes PDF** (`scrapers/bbva_tarjetas.py`, `scraper_credentials.py`): nueva opción "Descargar resúmenes PDF automáticamente" en la config del scraper. Cuando está activa, en cada run el scraper llama a `POST /extractos/extractos` para listar los resúmenes disponibles, detecta si el más reciente de VISA o Mastercard ya fue importado (por `reporte` ID único), y si no, lo descarga via `POST /extractos/getPdf` (respuesta binaria convertida a base64 en el browser) y lo procesa con el parser de PDF correspondiente (`bbva_visa`/`bbva_mc`). La importación aplica categorización por reglas (igual que el upload manual) y llama a `consolidate_scraper_duplicates` para limpiar duplicados del scraper de consumos.
- **Upload: protección contra PDF duplicado** (`routes/upload.py`, `db.py`): antes de parsear un archivo, se verifica si `importaciones` ya tiene una entrada con el mismo `(fuente, archivo)`. Si existe, retorna `ya_importado: true` sin insertar nada, evitando duplicar gastos al subir el mismo resumen dos veces por error.

## 0.8.74

- **MercadoPago: collector_id en descripción de transferencias salientes** (`scrapers/mercadopago.py`): las transferencias a otras cuentas MP ahora incluyen el ID del destinatario en la descripción, por ejemplo `"Transferencia [id:123456789]"` o `"Transferencia: nota [id:123456789]"`. Permite crear reglas de categorización por destinatario.

## 0.8.73

- **MercadoPago: evitar múltiples reportes por día** (`scrapers/mercadopago.py`): el scraper generaba un nuevo settlement report en cada ejecución, causando que MP enviara múltiples notificaciones por email cuando el scraper corría varias veces en el mismo día. Ahora `_download_latest_settlement` devuelve también la fecha del reporte más reciente, y `_fetch_settlement_report` solo solicita un nuevo reporte si no existe uno del día de hoy (hora ART).

## 0.8.72

- **Chart Presupuesto vs real: doble altura en mobile** (`static/app.js`): `aspectRatio: 1` en pantallas ≤ 600px (cuadrado) vs `2` en desktop. Con el ancho típico de un teléfono (~390px) el gráfico pasa de ~195px a ~390px de alto.

## 0.8.71

- **Presupuesto: categorías padre con hijos = suma automática** (`db.py`, `static/app.js`, `static/style.css`): si una categoría tiene subcategorías, su presupuesto se deriva siempre de la suma de los hijos (antes solo cuando el padre tenía 0). El campo pasa a ser read-only con badge "Σ hijos"; el botón ✕ desaparece de las filas padre-con-hijos. Al guardar, las filas padre se excluyen de la tabla `presupuestos` (los hijos son la fuente de verdad). Categorías padre SIN hijos mantienen input editable normal. El cálculo del backend usa pases iterativos para árboles de más de 2 niveles.

## 0.8.70

- **Tabs altura igual en Edge/Safari/iOS** (`static/style.css`): `.tab-text { line-height: 1 }`. La causa raíz era que `.tab-text` usaba el line-height default del browser (~1.5 Edge, ~1.2 Safari), por lo que el span de texto determinaba la altura del botón de forma diferente en cada browser. Con `line-height: 1` en ambos spans (`.tab-icon` ya lo tenía), la altura = sólo el padding + font-size y es idéntica en todos.
- **Botones de acción de pagos cuadrados y consistentes** (`static/style.css`): `.pago-action .tab-icon` tiene `width: 1.1em` fijo para que emojis anchos (✏️, 🗑) no cambien el ancho del botón. En modo "solo íconos" los botones son `34×34px` (escritorio) / `44×44px` (touch). `.btn-action` pasa a `display:inline-flex` con `width=height=26px` para ser verdaderamente cuadrado en todas las plataformas.

## 0.8.69

- **PWA / Pantalla de inicio en 3 columnas** (`static/index.html`, `static/style.css`): las secciones "Íconos por fuente", "Accesos rápidos" e "Instalar en iOS" se agrupan al final del sub-tab Interfaz en un layout flex de columnas (`.pwa-cols` / `.pwa-col`). En pantallas pequeñas se apilan; en desktop aparecen lado a lado.
- **Pagos manuales mensuales en tabla por mes** (`routes/cuotas.py`): los pagos con `recurrencia=mensual` ahora se expanden por todas las ocurrencias futuras hasta `fecha_fin` (o hasta un horizonte de 24 meses si no tiene fecha fin). Antes sólo aparecía el próximo mes.

## 0.8.68

- **Íconos levemente más grandes que el texto** (`static/style.css`): `.tab-icon { font-size: 1.15em; line-height: 1 }` compensa el achicamiento del selector de fuente y evita que el emoji infle el line-height del contenedor.
- **Tabs altura consistente entre Edge y Safari** (`static/style.css`): `.tab`, `.cfg-tab` y `.gtab` pasan a `display: inline-flex; align-items: center`. Los emojis en inline-block inflaban el line-height de forma distinta en cada browser; con flex la altura la determina sólo el padding.
- **Lápiz renderiza como emoji en Mac/PC** (`static/app.js`): `✏` (U+270F) tenía texto simple → ahora `✏️` (U+270F + U+FE0F, variation selector) fuerza renderizado emoji en todos los sistemas.
- **Tilde verde para "Marcar pagado"** (`static/app.js`, `static/style.css`): ícono cambiado a `✔` (U+2714, heavy check mark); clase `btn-pagado` pone el ícono verde (#16a34a) y ligeramente más grande.

## 0.8.67

- **Íconos en todos los botones de acción** (`static/index.html`, `static/app.js`): 💾 Guardar · ❌ Cancelar · ➕ Agregar · ▶ Probar · ✓ Aplicar · 👁/🚫 Widget · 🔍 Ver gastos (presupuesto) · 💾 en el botón inline de edición de descripción. El ❌ reemplaza al ✕ anterior como par natural de ✅.

## 0.8.66

- **Botones de fila en pagos manuales unificados** (`static/app.js`, `static/style.css`): reemplazados `mkBtn`/`mkIcon` por un único `mkAction` que genera botones con `<span class="tab-icon">` + `<span class="tab-text">`, controlables por el toggle de modo de pestañas (íconos / íconos+texto / texto). Íconos actualizados: ✓ Pagado, ⏹ Finalizar, ✏ Editar, 🗑 Borrar. Clase `.btn.pago-action` con `inline-flex` asegura la misma altura en todos los navegadores (Safari, Edge, iOS); el `min-height: 38px` en touch aplica igual a todos los botones de la fila.

## 0.8.65

- **Formulario pagos/vencimientos manuales alineado** (`static/index.html`, `static/style.css`): reemplazado el patrón `<label>X<br><input>` por `.pago-form` / `.pago-field` con flex-column. Todos los controles (text, number, select, date) comparten altura fija de 34 px y se alinean por la base con `align-items: flex-end` en el contenedor.

## 0.8.64

- **A1 — Botones del header Config/Categorías al alto correcto** (`static/index.html`): removido `btn-sm` de "Ver keywords", "⬇ Exportar" e "⬆ Importar" para que coincidan con "Guardar".
- **A2 — Botón Borrar de categorías movido al detalle** (`static/app.js`): el ✕ de cada fila desaparece; queda sólo el "+" para sub-categorías. Al expandir la categoría aparece "Borrar" al lado de "Probar". Las categorías nuevas (no guardadas) siguen teniendo ✕ en la fila.
- **Gráficos fijos con ← → para reordenar** (`static/index.html`, `static/app.js`): los charts "Presupuesto vs real" y "Movimientos ARS" ahora tienen botones de reorden iguales a los del grid. El orden se persiste en localStorage.
- **Pagos/Cuotas: botones del formulario alineados** (`static/index.html`): "Cancelar" y "Recargar" pasan de `btn-sm` a `btn` para igualar a "+ Agregar".
- **Pagos/Cuotas: botones de fila consistentes** (`static/app.js`): celda de acciones usa flex con gap uniforme; ✏ y ✕ usan `btn-action` (ícono cuadrado) mientras "✓ Pagado" y "■ Finalizar" son `btn-sm` estándar.
- **RG 5617 movido a Procesamiento → Importación** (`static/index.html`): el checkbox "Incluir devoluciones RG 5617" ahora vive al inicio del acordeón Importación en Procesamiento.
- **Botones de sección en Interfaz al alto correcto** (`static/index.html`): Save/Reset general, PWA e Íconos quitan `btn-sm`.
- **Colores en grid 2 columnas** (`static/index.html`, `static/style.css`): las 7 filas de color se consolidan en un único `ui-colors-grid` con layout 1-col en móvil y 2-col en pantallas ≥ 700 px. Sección "Categorías" se separa con un encabezado interno que ocupa todo el ancho.

## 0.8.63

- **Columna "💰 Pagos" en tabla por mes** (`routes/cuotas.py`, `static/app.js`, `static/style.css`). El desglose mensual de Pagos/Cuotas ahora incluye una columna extra con el total de pagos manuales pendientes (servicios, alquiler, etc.) agrupados por mes de vencimiento. Se muestra separada visualmente (borde izquierdo) a la derecha de las fuentes de tarjeta y antes del Total ARS. El total de la fila incluye cuotas + pagos manuales.

## 0.8.62

- **Íconos en todos los tabs y cfg-tabs** (`static/index.html`). Se agregó icono 📊 al tab Gráficos (que lo tenía faltando) y se completaron los iconos en todos los sub-tabs de Config: 🏷️ Categorías, 👥 Personas, 💳 Cuentas, ⚙️ Procesamiento, 🎨 Interfaz, 💾 Datos, 📋 Log. Los labels usan `<span class="tab-icon">` + `<span class="tab-text">` para soporte del nuevo toggle.
- **Toggle de modo pestañas** (`static/index.html`, `static/app.js`, `static/style.css`). Nueva preferencia "Pestañas" en Config → Interfaz → Preferencias: "Íconos + texto" (por defecto), "Solo íconos" o "Solo texto". Se aplica a todos los tabs principales y sub-tabs de Config. Guardado en `localStorage` como `tab_icon_mode`.
- **Avisos movido a Interfaz** (`static/index.html`, `static/app.js`). El sub-tab Avisos fue eliminado; su contenido (notificaciones push + configuración de vencimientos) vive ahora dentro de Config → 🎨 Interfaz bajo la sección "Notificaciones".

## 0.8.61

- **Pagos manuales: fecha de fin, edición y "Finalizar"** (`db.py`, `routes/pagos.py`, `static/index.html`, `static/app.js`). Nueva columna `pagos.fecha_fin` (con migración PRAGMA+ALTER): tope de la recurrencia mensual — al marcar pagado, si la próxima cuota caería después de `fecha_fin` no se regenera. Botón **✏ Editar** (carga la fila en el form, que pasa a "Guardar") y botón **■ Finalizar** (en mensuales: marca pagado sin regenerar, cierra la serie) → `POST /api/pagos/{id}/finalizar`. El form suma el campo "Hasta (si es mensual)".
- **Tab "Cuotas" → "📅 Pagos/Cuotas"** y los pagos manuales viven arriba de las cuotas de tarjeta en ese tab (`static/index.html`).
- **Íconos en los tabs principales**: 🧾 Gastos, 📅 Pagos/Cuotas, 🎯 Presupuesto, ⚙ Config (`static/index.html`).
- **Reordenado Config**: el sub-tab 🔔 Avisos pasó antes de Interfaz, para que el final quede Interfaz · Datos · Log (`static/index.html`).

## 0.8.60

- **"Probar aviso ahora" ahora es tolerante con los umbrales** (`vencimiento_notifier.py`, `static/app.js`). El test daba "no hay vencimientos en la ventana" cuando el item no caía justo en un día de umbral (ej. pago a 2 días con umbrales `[3,1]`). En producción el aviso sigue siendo **match exacto** de días (3 y 1 días antes), pero en modo `force` (el botón "Probar") ahora manda para **cualquier** tarjeta impaga o pago pendiente próximo (≤60 días, no vencido), así el test siempre demuestra. Mensaje del toast actualizado.

## 0.8.59

- **Pagos manuales movidos al tab Cuotas + aviso aclarado** (`static/index.html`, `static/app.js`). Los pagos/vencimientos manuales (b2) pasaron del sub-tab Config → 💰 Pagos al **tab Cuotas** (arriba de las cuotas de tarjeta), que es el que muestra el futuro. Se eliminó el sub-tab de Config; `loadPagos()` ahora se dispara al entrar a Cuotas. Además se aclaró el texto en Config → 🔔 Avisos: el toggle de notificación **siempre cubrió tarjetas Y pagos manuales** (comparten la config `venc_notif_*`), pero decía solo "tarjeta" → ahora dice "vencimientos de tarjeta y pagos" para que se entienda que un solo aviso cubre ambos.

## 0.8.58

- **Botón "Resetear duplicadas" para limpiar suscripciones push** (`routes/push.py`, `static/index.html`, `static/app.js`, `static/sw.js`). Si "Probar" mandaba notificaciones **duplicadas** era porque quedaban suscripciones huérfanas en la DB de antes del fix 0.8.56 (endpoints viejos aún vivos que el 410 no llegó a limpiar), y el envío hace fan-out a todas. Nuevo `POST /api/push/clear` borra TODAS las suscripciones del usuario; el botón además desuscribe el navegador local y vuelve a activar este dispositivo → queda una sola suscripción limpia. En los otros dispositivos hay que tocar "Activar" de nuevo. Bump caché SW `v0.2.39`.

## 0.8.57

- **Pagos / vencimientos manuales (feature b2)** (`db.py`, `routes/pagos.py` nuevo, `main.py`, `vencimiento_notifier.py`, `static/index.html`, `static/app.js`, `static/sw.js`). Para "idem para pagos": servicios, alquiler, expensas, etc. que no se scrapean.
  - Tabla `pagos` (per-usuario): descripción, monto, moneda, fecha_vencimiento, recurrencia (`unico`/`mensual`), estado (`pendiente`/`pagado`), categoría. CRUD `db.py` (`list_pagos`, `add_pago`, `update_pago`, `delete_pago`, `mark_pago_pagado`). Al marcar pagado un **mensual**, se genera solo la fila del mes siguiente (`_add_one_month`, clampea el día al último del mes).
  - Endpoints REST `GET/POST/PUT/DELETE /api/pagos` + `POST /api/pagos/{id}/pagar` (`routes/pagos.py`).
  - UI: nuevo sub-tab **Config → 💰 Pagos** con alta, listado, marcar pagado y borrar (render con `createElement`+`.onclick`, sin JSON en atributos).
  - El **notifier** (`vencimiento_notifier`) ahora además recorre los pagos `pendiente` y manda push con la misma antelación configurable (`💰 Alquiler vence en 3 días`). Dedup con clave `pago|id|fecha|umbral`. El botón "Probar aviso ahora" también los incluye.

## 0.8.56

- **Fix: el logout dejaba suscripciones push huérfanas → avisos duplicados** (`static/app.js`, `static/sw.js`). El handler de logout desregistra el service worker (para aislar caché entre usuarios), lo que destruye la suscripción push del navegador **sin avisarle al server** → quedaba huérfana en `push_subscriptions` y, al re-loguear y re-activar, se creaba otra con endpoint nuevo (de ahí "2 notificaciones desde la Mac"). Ahora el logout hace `POST /api/push/unsubscribe` de la suscripción actual **antes** de matar el SW (aún logueado, con `keepalive`). Las huérfanas previas se autolimpian: devuelven 410 en el próximo envío y `send_push` las borra. Bump caché SW `v0.2.37`.

## 0.8.55

- **Aviso de vencimientos de tarjeta por push (feature b1)** (`vencimiento_notifier.py` nuevo, `scraper_scheduler.py`, `db.py`, `user_config.py`, `routes/config_route.py`, `static/index.html`, `static/app.js`, `static/sw.js`). Manda un Web Push N días antes de cada vencimiento de tarjeta **impago**, reusando lo que ya existía: `list_vencimientos()` (sabe la fecha y si está pagado vía `pago_confirmado`/`pago_probable`) y `send_push()` (feature "a").
  - Config en **Config → 🔔 Avisos** (todo en UI, `user_config`): `venc_notif_activo` (opt-in, apagado por defecto), `venc_notif_dias_antes` (umbrales de antelación, default `[3,1]`), `venc_notif_hora` (hora local ART, default 9). Endpoints `GET/PUT /api/config/venc-notif`. Botón **"Probar aviso ahora"** (`POST /config/venc-notif/test`) que dispara el notifier al instante ignorando hora/opt-in/dedup, para verificar sin esperar.
  - Notifier: job **horario** del scheduler (`run_for_all_users`, corre a :05) que itera usuarios; cada uno recibe sólo a su hora elegida. Por cada tarjeta impaga cuyos días hasta el vto caen en un umbral → push *"💳 AMEX vence en 3 días — $X"*. Hora ART por offset fijo UTC-3 (sin depender de tzdata).
  - Dedup: tabla `venc_notificaciones` (clave `fuente|fecha_venc|umbral`) → no repite el mismo aviso. El job se agrega SIEMPRE (antes el scheduler hacía `return` temprano si no había scrapers).

## 0.8.54

- **Push debugging: el toast de "Activar" muestra el error real** (`static/app.js`) y bump de caché del SW a `v0.2.35` (`static/sw.js`). Diagnóstico del log: `subscribe` y `test` devuelven 200 (el server manda el push OK), pero en el dispositivo no se mostraba → el **service worker viejo (sin handler `push`) seguía activo**. En Edge, `pushManager.subscribe()` fallaba sin POST y el toast genérico no decía por qué; ahora muestra `name: message`. El bump de caché fuerza el ciclo de actualización del SW para que active el que tiene el handler `push`.

## 0.8.53

- **Push: el "sub" de VAPID se deriva de `allowed_domain`** (`routes/push.py`). Antes era `mailto:admin@localhost`, que Apple/Safari puede rechazar al validar el JWT de VAPID (rompería el push en iOS). Ahora por defecto es `mailto:admin@<allowed_domain>` (override por env `VAPID_SUB`).

## 0.8.52

- **Notificaciones Web Push (VAPID)** — feature "a" (`routes/push.py`, `db.py`, `main.py`, `requirements.txt`, `static/sw.js`, `static/index.html`, `static/app.js`). Push real sin app nativa, para iPhone (PWA agregada a inicio), Safari (Mac) y Edge/Chrome (PC):
  - Claves VAPID generadas con `cryptography` y persistidas atómicamente en `/data/vapid.json` (global). La pública se expone como `applicationServerKey`; la privada firma cada push vía `pywebpush`.
  - Tabla `push_subscriptions` per-usuario (en `gastos.db`); `endpoint` único con UPSERT. Las suscripciones muertas (404/410) se borran solas al enviar.
  - Endpoints `/api/push/public-key`, `/subscribe`, `/unsubscribe`, `/test`. El envío corre en threadpool con las subs leídas en contexto (no depende del ContextVar dentro del thread).
  - `sw.js`: handlers `push` (muestra la notificación) y `notificationclick` (enfoca/abre la app). Nuevo sub-tab **Config → 🔔 Avisos** con Activar / Probar / Desactivar.
  - Validado localmente: generación VAPID (punto P-256 de 65 bytes → applicationServerKey de 87 chars), `Vapid01.from_pem` carga el PEM, y `webpush()` cifra+firma OK (llega al POST).

## 0.8.51

- **Fin de los `/data/gastos.db` huérfanos: logs sin contexto ya no ensucian el root** (`app_log.py`, `scrapers_db.py`). Diagnóstico: el `/data/gastos.db` raíz tenía 0 gastos pero se actualizaba solo — eran logs sin dueño. El `DBLogHandler` está enganchado al root logger y dispara en cada `logger.*`; muchos (arranque, scheduler, tareas de fondo) corren **sin contexto de usuario**, y `get_db_path()` sin contexto apunta al `/data/gastos.db` raíz. Dos cambios:
  - `app_log.write_log` / `write_scraper_run_log`: si no hay contexto de usuario (`userctx._user_data_dir` es None), **no escriben en DB** (la línea igual sale al log del contenedor por stdout). Corta la fuente del huérfano.
  - `scrapers_db._find_db_path`: el fallback dejó de devolver el root en silencio y ahora **lanza `RuntimeError`** (fail loud). Si un llamador accede a la DB sin setear contexto, salta como bug en vez de crear/corromper un huérfano. Prerequisito para que la conciliación de vencimientos (próxima feature) no pueda escribir sin dueño.
- Nota operativa: la data real vive en `/data/{email}/gastos.db` (intacta). El `/data/gastos.db` raíz, `gastos.db.old` y el `rules.yaml` legacy eran descartables y se borraron manualmente.

## 0.8.50

- **Fix: la sesión se caía sola ("refresh me devuelve a login")** (`auth.py`). Dos causas, ambas evidentes en el log (sesión válida recién logueada y muerta minutos después, con 200/401 intercalados):
  - `_MAX_TOKENS_PER_USER` era **10**: al pasar de 10 tokens activos por usuario se expulsaba el **más viejo aunque siguiera activo**. Con iPhone PWA + desktop + la tanda de re-logins de un debugging, se echaban sesiones vivas → logout en el próximo request. Subido a **50** (holgura para varios dispositivos × varias re-logueadas).
  - `session_tokens.json` (y `users.json`, `settings.json`) se escribían **no atómicamente** (truncar + reescribir). Un reinicio del add-on a mitad de escritura dejaba el archivo truncado → `JSONDecodeError` → `_load_session_tokens` devolvía `{}` → **todas** las sesiones inválidas. Ahora se escribe vía `_atomic_write_json` (tmp + `os.replace`, atómico en el mismo filesystem).

## 0.8.49

- **Backup/restore COMPLETO desde el panel Admin** (`routes/admin.py`). Nueva sección "Copia de seguridad completa" (solo admin) con dos acciones:
  - `GET /admin/export-all`: descarga un `.zip` con **todo `/data`** — `users.json` (todas las cuentas de login), `settings.json`, y la carpeta de cada usuario (`gastos.db` con `movimientos_raw`, logs `app_log`, cuentas, presupuestos y **credenciales de scrapers cifradas sin vaciar**, reglas, sesiones). Cada `.db` se copia con `VACUUM INTO` (snapshot consistente aunque esté en WAL). A diferencia del export-backup per-usuario de Config (que es de un solo usuario y vacía las credenciales), este se lleva **absolutamente todo** para reinstalar el add-on de cero y restaurar sin pérdida.
  - `POST /admin/import-all`: restaura ese `.zip` sobrescribiendo los archivos del backup (merge, no wipe). Valida que traiga `users.json`, que cada `.db` sea SQLite real, borra WAL/SHM viejos, y **defiende contra zip-slip** (`_safe_target`: rechaza rutas absolutas y `..`, nunca escribe fuera de `DATA_DIR`).
  - Las credenciales de scrapers solo se descifran tras restaurar si la opción `scraper_encryption_key` del add-on sigue siendo la misma (los blobs cifrados viajan, la clave no). La sesión admin sobrevive al restore porque el admin se autentica con la password del add-on (`verify_admin`), no con `users.json`.

## 0.8.48

- **Se revierte el renombre de carpeta `finance-me` → `gastos-tarjetas`** (`config.yaml` url, `finance-me-mobile/README.md`). El rename de carpeta de la 0.8.47 rompía la actualización del add-on ya instalado: Home Assistant cachea la ruta de origen del add-on instalado (`gastos-tarjetas/`) y, tras renombrar la carpeta, tanto Rebuild como Update fallaban con "dockerfile is missing" (construían desde la ruta vieja). Ni `ha addons reload` ni `ha supervisor restart` reescribían ese binding. La marca visible **sigue siendo "Finance Me"** (el nombre de carpeta no se ve en ningún lado: es solo el directorio del repo y la ruta que HA usa para buildear). Se mantiene `name: "Finance Me"` en config.yaml y todos los textos de UI; solo vuelve el nombre del directorio para que la ruta coincida con lo que el Supervisor espera.

## 0.8.47

- **Rebrand a "Finance Me"** (`config.yaml`, `rootfs/app/main.py`, `static/index.html`, `static/quick.html`, `static/manifest.json`, `static/sw.js`, `routes/auth.py`, `run.sh`, `DOCS.md`). Se renombró la carpeta del add-on `gastos-tarjetas` → `finance-me` y el nombre visible de la marca pasó de "Gastos" a "Finance Me" en todos los puntos de UI: navbar (al lado de la versión), `<title>`, `apple-mobile-web-app-title`, manifest PWA (estático y dinámico), pantalla de login/registro y log de arranque. **El `slug` del add-on se mantiene como `gastos_tarjetas` a propósito**: es la clave con la que Home Assistant mapea el volumen `/data` (DB `gastos.db`, sesiones, claves de scrapers cifradas); cambiarlo haría que HA lo trate como un add-on nuevo y se perdería todo el estado. Los **términos de dominio** (`/api/gastos`, tabla `gastos`, `gastos.db`, funciones `loadGastos`, tab "Gastos", hoja Excel "Gastos") **no se tocaron** — son el modelo de datos, no la marca; su traducción/renombre queda como trabajo aparte.

## 0.8.46

- **Presupuesto: el padre de una subcategoría presupuestada ahora siempre se muestra (para anidar)** (`db.py`, `static/app.js`). Si presupuestabas una subcategoría cuyo padre no tenía gasto ni presupuesto propio, la subcategoría se mostraba plana (el padre no tenía fila). Ahora `stats_presupuesto_vs_actual` conserva la categoría si ella **o cualquier descendiente** está en la tabla `presupuestos` (`budget_in_subtree`), así el padre siempre aparece como fila contenedora. El frontend además agrega la fila del padre en el merge para feedback instantáneo antes del reload.

## 0.8.45

- **Presupuesto: agregar categorías/subcategorías ahora usa un selector de existentes y permite presupuestar aunque no tengan gasto** (`static/app.js`, `db.py`). Dos bugs:
  - El botón "+" usaba un prompt de **texto libre** → se podían "inventar" categorías que no existían, y encima no aparecían. Ahora es un **selector de las categorías y subcategorías existentes** (las subcategorías se muestran como `Padre › Hija`), excluyendo las que ya están en la tabla. No se pueden cargar categorías nuevas, solo las del modelo.
  - Una categoría/subcategoría **sin gasto no se podía ver ni presupuestar**: `renderPresupuesto` armaba la tabla sólo desde `vs_actual` (lo que tiene gasto), y el backend `stats_presupuesto_vs_actual` descartaba las categorías con `gastado==0 y presupuesto==0`. Ahora: (a) el front mergea las categorías agregadas al presupuesto aunque no tengan gasto, anidándolas bajo su padre vía la jerarquía ya cargada (`_catParentOf`/`_catHierarchy`); (b) el back conserva toda categoría presente en la tabla `presupuestos` (incluso con monto 0 = "trackeada"); (c) `savePresupuesto` persiste también las agregadas con monto 0, y `updatePresupItem` ya no contamina el presupuesto con ceros de categorías que sólo se muestran por tener gasto.

## 0.8.44

- **Consumo de tarjeta: ahora resta los reintegros de comercio (matchea el total de "Cargos" del banco)** (`scraper_scheduler.py`, `user_config.py`, `routes/config_route.py`, `static/index.html`, `static/app.js`). El cálculo anterior sumaba sólo los cargos positivos (`monto > 0`), así que cuando un crédito era un **reintegro de compra** (ej. AMEX `COTO 091 DIGITAL 000984` por −$37.785,57, que AMEX muestra en la columna "Pagos" pero **descuenta de los Cargos**) el widget quedaba inflado por ese monto. Ahora `_apply_tarjeta_consumo()` suma los cargos y **resta los créditos que NO son pagos**: un crédito (monto < 0) se ignora si su descripción matchea un patrón de pago/acreditación/percepción/ajuste, o se resta si no (= reintegro de comercio). Verificado contra el resumen real de AMEX: ARS $1.267.987,75 y USD $20,00 exactos.
- **Nuevo setting configurable `tarjeta_consumo_pago_patrones`** (Config → Importación): lista de patrones (substring, case-insensitive) que identifican un crédito como "no consumo". Defaults: `PAGO`, `ACREDITAC`, `AJUSTE`, `PERCEPCION`, `RG 5617`. Se aplica sólo a montos negativos, así que los cargos positivos (ej. `MERPAGO*TECNOFAST`) nunca se ven afectados. Los otros scrapers (Galicia/BBVA/Visa) no cambian su número: sus pagos negativos siguen matcheando `PAGO` y se siguen excluyendo.

## 0.8.43

- **Widget de tarjetas: ahora muestra siempre el consumo scrappeado del período abierto** (`scraper_scheduler.py`, `db.py`, `static/app.js`, `static/style.css`). Antes los chips de tarjeta sólo se basaban en el último resumen PDF (`importaciones`) y al tocar mostraban ese detalle. Ahora:
  - **Backend**: al guardar el resultado de un scraper de tarjeta, el scheduler suma los egresos (`monto > 0`, separados ARS/USD) del snapshot completo que trae el scraper (`result.movimientos` — los 4 scrapers devuelven el período vigente entero en cada run, así que no hace falta fecha de cierre) y lo guarda en `cuentas.saldo`/`saldo_usd` de la cuenta `credit_card` vía el nuevo `set_tarjeta_consumo()`. Los pagos/créditos vienen con monto negativo y quedan excluidos. Nuevo helper `_apply_tarjeta_consumo()` (paralelo a `_apply_saldo_delta`) y `get_credit_card_fuentes()` para distinguir tarjetas (incluye fuentes custom, no sólo `_CC_FUENTES`).
  - **Frontend**: el widget de tarjetas pasa a una fila tipo "saldos" — cada tarjeta muestra **siempre** su consumo en vivo (`$ … · U$S …`) como número principal, con el borde derecho de estado del scrape y un badge de días-a-vencimiento cuando hay resumen importado. Al tocar sigue expandiendo el detalle del último resumen PDF (fecha de cierre/vencimiento, total, RG 5617). La lista de tarjetas ahora sale de las cuentas `credit_card`, así que una tarjeta aparece aunque todavía no se haya subido ningún PDF (con su consumo scrappeado). El PDF queda sólo para la info de cierre/vencimiento.


- **FIX de seguridad: sesiones de browser de scrapers ahora son per-usuario** (`scrapers/base.py`, `scrapers/galicia.py`): el dir de sesiones era la constante global `_SESSIONS_DIR = /data/sessions`, así que los scrapers guardaban las cookies de sesión bancaria en `/data/sessions/{fuente}.json` **compartido entre todos los usuarios**. Dos usuarios con el mismo banco (ej. dos con AMEX) pisaban/compartían cookies → un usuario podía correr el scraper con la sesión del otro. (BBVA/Galicia usan `save_session=False` y no persistían; AMEX/MP/IOL heredan el default `True` y sí.) Ahora `_sessions_dir()` y `_period_state_path()` (Galicia) resuelven en **runtime** desde el ContextVar de userctx → cada usuario guarda en `/data/{email}/sessions/`. Cierra el último gap de aislamiento multi-usuario de la familia de la migración legacy. Las sesiones globales viejas en `/data/sessions/` quedan huérfanas (se pueden borrar; el próximo scrape hace login limpio y guarda en el dir correcto).

## 0.8.41

- **FIX de seguridad: fin de la fuga de datos entre usuarios (migración legacy)** (`userctx.py`, `scrapers_db.py`): la causa raíz del problema que originó toda esta tanda. `set_user_context` copiaba `/data/gastos.db` raíz + `rules.yaml`/`match_rules.yaml`/`user_config.json` al **primer usuario que logueaba**, guardado solo por un sentinel best-effort. Resultado: quien entraba primero (o cualquier usuario nuevo si el sentinel fallaba al escribirse) **heredaba TODA la data legacy de otro** — gastos, cuotas, cuentas, credenciales.
  - **Se eliminó la copia de data legacy.** Un usuario nuevo ahora arranca con una DB **limpia** que crea `init_db()` (schema + 7 cuentas default + categorías), y un `rules.yaml` sembrado desde los **defaults bundleados** (`default_rules.yaml`) — nunca desde la data de otro usuario. `match_rules.yaml` y `user_config.json` quedan ausentes (los lectores los tratan como vacío/defaults, que es lo correcto para un usuario nuevo). Los usuarios existentes no se ven afectados (su data ya vive en su dir). Para asignar data legacy a un usuario puntual: `cp /data/gastos.db /data/{email_sanitizado}/gastos.db` antes de su primer login.
  - **`_find_db_path()` ya no elige una DB arbitraria sin contexto** (`scrapers_db.py`): el fallback `sorted(glob(...))[0]` agarraba la DB del primer usuario alfabético cuando no había contexto de usuario, otra vía de cruce de datos. Ahora cae al `/data/gastos.db` raíz (huérfano) y loguea un error — todos los llamadores legítimos setean el contexto antes, así que en la práctica nunca se usa.
- **FIX AMEX login: 'element not interactable'** (`scrapers/amex.py`, `scrapers/base.py`): el login fallaba con `ElementNotInteractableException` porque `wait_for` usa `presence_of_element_located` y devuelve el **primer** match del DOM, que puede ser un input OCULTO (coexisten el form legacy `#eliloUserID` y el del SPA con el mismo campo). Al hacer `send_keys`/`click` sobre el oculto, salta el error. Nuevo helper `wait_visible()` en `base.py` que devuelve el primer elemento **visible+habilitado**; `do_login` lo usa para usuario, contraseña y submit. Además, helpers `_type_into()`/`_click_el()`/`_find_visible()` con scroll-into-view previo y **fallback JS** (setear `value` + disparar `input`/`change`, o click vía JS) si Selenium reporta el elemento no interactuable.

## 0.8.40

- **Hardening de seguridad (DOM-XSS + logging de credenciales)** (`static/app.js`, `scrapers/galicia.py`): producto de la auditoría de las zonas 1 (DOM-XSS) y 2 (credenciales).
  - **`escHtml` ahora también escapa la comilla simple** (`'` → `&#39;`): defense-in-depth para que valores escapados que terminen en atributos con comillas simples no puedan romperlos. Los datos de origen externo (descripciones bancarias, errores/logs de scraper) ya se escapaban de forma consistente; esto cierra un footgun latente. (No se tocaron las ~80 interpolaciones de `${fuente}` porque `fuente` siempre sale de `_slugify()` → `[a-z0-9_]`, no es inyectable.)
  - **Galicia: no loguear el alias/usuario de homebanking** (`galicia.py`): el log de arranque del scraper imprimía el valor del alias (`alias=%r`). Ahora solo registra si está presente o vacío. La contraseña nunca se logueaba (solo su longitud); el `config` con credenciales descifradas tampoco se vuelca a ningún log. Nota de postura: si `SCRAPER_ENCRYPTION_KEY` no está seteada, las credenciales quedan en plaintext en `gastos.db` (fallback documentado).

## 0.8.39

- **Fix: dedup por saldo conciliaba movimientos de distinta fecha (rangos largos)** (`scrapers_db.py`, `db.py`): el check de dedup por saldo (0.8.35) y la migración de limpieza (0.8.36) buscaban un movimiento con el mismo `(fuente, moneda, monto, saldo)` **sin acotar la fecha**. Pero el saldo corriente **no es globalmente único**: la cuenta puede volver al mismo saldo en otra fecha (sube y baja al mismo valor — p.ej. `4.357,29` aparece dos veces el mismo día en una cuenta BBVA). Al importar rangos largos (ej. 60 días), un movimiento podía conciliarse con otro de **otra fecha** que casualmente tenía igual monto y saldo, perdiéndose o pisándose registros viejos.
  - **Live dedup** (`insert_movimientos_raw`): el match por saldo ahora se acota a una **ventana de ±2 días** alrededor de la fecha del movimiento (cubre el corrimiento de fecha contable de BBVA sin permitir coincidencias lejanas).
  - **Migración de limpieza** (`dedup_bbva_saldo_v1`): la clave de agrupación ahora **incluye la fecha**, así que solo fusiona duplicados de la **misma fecha** + monto + saldo. (Las DBs que ya corrieron la migración con la lógica anterior pueden recuperar movimientos fusionados re-corriendo el scrape BBVA sobre el rango afectado.)

## 0.8.38

- **FIX de seguridad: XSS reflejado en `/quick`** (`main.py`): la ruta `/quick` inyectaba los query params `label` y `fuente` **sin escapar** en el `<title>`, en el atributo `content="..."` y en el `href` del manifest. Un atacante podía mandarle a un usuario logueado un link same-origin tipo `/quick?label=</title><script>…</script>` y ejecutar JS en su sesión autenticada (robo/exfiltración de todos sus datos, acciones en su nombre). Ahora `title` se escapa con `html.escape(quote=True)` y `label`/`fuente` se URL-encodean (`urllib.parse.quote`) antes de interpolarse. Igual hardening en `/quick-icon/{fuente}.svg`, que interpolaba `fuente` y los `lines` de la config de usuario en el SVG. Nota: el hardening XSS de v0.6.15 cubrió `admin.py` y login pero `/quick` quedó afuera porque no estaba en ese diff — esta clase de bug solo se ve con una auditoría de todo el código, no con el review acotado al diff de una rama.

## 0.8.37

- **FIX de seguridad: el logout ahora invalida la sesión del lado servidor** (`auth.py`, `routes/auth.py`, `main.py`, `static/index.html`, `static/app.js`): la sesión vivía 100% en una cookie firmada, sin estado server-side. Eso hacía que el logout solo le *pidiera* al navegador borrar la cookie; cuando el navegador no la borraba (PWA standalone de iOS, cookie duplicada por `path` reescrito por el proxy, etc.), la cookie vieja **seguía autenticando** y un logoff→login dejaba ver/loguear al usuario anterior tras un refresh — una fuga de datos entre usuarios.
  - **Tokens de sesión por dispositivo** (`auth.py`): nuevo `session_tokens.json` con el set de tokens activos por usuario. Cada login emite un token (`stoken`) que viaja dentro de la cookie; cada request valida que el token siga en el set. El logout **revoca el token de ese dispositivo** (`revoke_session_token`), así la cookie vieja deja de autenticar aunque sobreviva en el navegador. El reset de password y el borrado de usuario revocan **todos** los tokens (cierran sesión en todos lados).
  - **Validación en el middleware** (`main.py`): si la cookie trae un token revocado o anterior a este esquema, se limpia la sesión (SessionMiddleware borra la cookie) y el request se trata como no autenticado → redirige a login. Esto corta el "vuelvo a quedar logueado como el usuario anterior".
  - **Borrado explícito de cookie en logout** (`routes/auth.py`): `delete_cookie("session", path="/")` además del que hace SessionMiddleware.
  - **Limpieza de caché del cliente en logout** (`app.js`/`index.html`): al cerrar sesión se borran las caches del service worker, se desregistra el SW y se limpia `localStorage`, para que no queden datos ni preferencias del usuario anterior visibles antes del refresh.
  - **Nota de upgrade**: las sesiones existentes (cookies sin `stoken`) quedan invalidadas en el primer request tras actualizar — todos los usuarios deben loguearse una vez.

## 0.8.36

- **Limpieza one-shot de duplicados BBVA preexistentes** (`db.py`, migración `dedup_bbva_saldo_v1`): el fix de dedup por saldo (0.8.35) evita nuevos duplicados, pero los que ya estaban en la DB seguían ahí. Esta migración corre una sola vez al arrancar: agrupa las filas BBVA por `(fuente, moneda, monto, saldo-corriente-real)` —un saldo idéntico ⇒ es el MISMO movimiento— y deja una sola fila por grupo, borrando las copias y sus gastos vinculados (más sus `transfer_pairs`). Conserva la fila de descripción más específica (prefiriendo la ya importada) y preserva categoría/descripción editada si la copia las tenía. Solo actúa sobre filas con saldo real ≠ 0 (no toca cuentas legacy con `saldo=0` ni pares legítimos opuestos, que tienen saldos distintos). Idempotente vía `db_migrations`.

## 0.8.35

- **BBVA: dedup por saldo corriente real + arreglo de duplicados y pares opuestos** (`scrapers_db.py`): en modo `filtro_fecha_api=False` ("saldo real"), BBVA devuelve el saldo resultante de cada movimiento, pero `insert_movimientos_raw` lo ignoraba por completo y deduplicaba solo por descripción. Eso causaba dos errores:
  - **Duplicados por enriquecimiento de descripción**: un movimiento scrapeado sin `detalleservicio` se guardaba con la descripción base (ej. `PAGO DE SERVICIOS TARJETA 84296031 OP1409`); un run posterior agregaba el sufijo del detalle (`— SJOSE P DIOS`) y, como no hay `numeroOperacion` y la descripción no es genérica, ningún check matcheaba → fila duplicada. Le pasaba a cualquier extracción/pago con detalle que se enriqueciera en un run posterior.
  - **Pares legítimos opuestos colapsados/dados vuelta** por el heurístico `dedup-opuesto` (v0.6.10): una extracción de +460K y una transferencia entrante de −460K del mismo día son movimientos distintos, pero se descartaba/sobreescribía uno como "contraasiento". Ese heurístico era un parche de la época en que BBVA devolvía `saldo=0`.
  - **Fix**: nuevo check primario que deduplica por `(fuente, moneda, monto, saldo)` cuando hay saldo real (≠ 0) — el saldo es único por operación y estable entre runs, inmune a cambios de descripción y de fecha contable; conserva la descripción más específica. El heurístico `dedup-opuesto` ahora solo corre en modo legacy sin saldo real. Gateado a "saldo presente y ≠ 0", no afecta MP/AMEX/Galicia ni cuentas viejas.

## 0.8.34

- **Gastos: Categorías siempre visibles + botón "Filtros" recuerda su estado** (`static/index.html`, `static/app.js`, `static/style.css`): en el tab Gastos → Movimientos, el slicer de **Categorías** se sacó del panel colapsable y ahora queda **siempre visible**. El botón "Filtros" muestra/oculta **solo** los filtros de detalle (fuente, persona, mes, moneda, tipo, importación), arranca **colapsado** ("Filtros +") y **recuerda** si lo dejaste abierto/cerrado vía `localStorage` (`gastos-filters-open`). Label cambia entre "Filtros +" (cerrado) y "Filtros −" (abierto).

## 0.8.33

- **Fix: el scheduler programaba schedules sin migrar en multi-usuario** (`scraper_scheduler.py`): al arrancar, `on_startup()` corre `init_db()` solo sobre la DB raíz; las migraciones de cada DB de usuario corren *lazy* (en el primer request del usuario, vía middleware). Pero `start_scheduler()` también corre al arranque y leía las instancias de cada DB de usuario **antes** de que su migración `scraper_schedule_interval_v1` se aplicara, programando el schedule legacy (`"07:45"` diario) en vez de `every:4h`. Síntoma: MercadoPago mostraba "Próximo: mañana 7:45" en vez de cada 4h. Ahora `start_scheduler()` corre `init_db()` para cada DB de usuario antes de leer sus instancias, garantizando que las migraciones estén aplicadas. (También aplica a `reload_scheduler()`, que reusa `start_scheduler()`.)

## 0.8.32

- **Scheduler por intervalo (cada N horas) en vez de 1 vez al día** (`scraper_scheduler.py`, `db.py`, `scraper_credentials.py`, `routes/scrapers.py`, `routes/scraper_instances_routes.py`, `static/app.js`): el schedule de cada instancia deja de ser una hora fija diaria y pasa a un intervalo configurable. Mínimo cada 2h (para no martillar el homebanking), default cada 4h.
  - Nuevo formato de schedule `"every:Nh"` con N ∈ {2,3,4,6,8,12,24}. Se sigue soportando el formato legacy `"HH:MM"` (diario) por compatibilidad. `parse_schedule()` arma el `CronTrigger` (`hour=*/N`); el caso 24h corre 1 vez al día a la hora 0 (porque `*/24` no es válido en cron). Cada instancia recibe un offset de minutos estable derivado de su id para escalonar las corridas y no pegarle a todos los bancos al mismo instante.
  - Migración `scraper_schedule_interval_v1`: convierte los schedules legacy `"HH:MM"` de las instancias existentes a `every:4h`. Los defaults de las plantillas (`BANKS`) también pasan a `every:4h`.
  - UI: el campo "Hora diaria" del panel de cada cuenta (y la card legacy de Scrapers) se reemplaza por un selector de "Frecuencia" (cada 2/3/4/6/8/12/24h). Si una instancia trae un schedule legacy se muestra como opción extra hasta que se elija un intervalo. La validación de los endpoints acepta ambos formatos.
- **Barrita de estado del último scrape en los chips de la home** (`db.py`, `static/app.js`, `static/style.css`): cada chip de cuenta (saldos) y de tarjeta (vencimientos) muestra una barra de color en el borde derecho según cómo le fue al último scrape: verde = corrió OK, rojo = falló (o sesión expirada), amarillo = no corrió a horario (sin un OK reciente, > 2× el intervalo). Las cuentas manuales (sin scraper) no muestran barra.
  - `get_cuentas()` ahora hace LEFT JOIN con `scraper_instances` y expone `scraper_estado`/`scraper_ultimo_run`/`scraper_ultimo_ok`/`scraper_schedule`/`scraper_enabled`/`scraper_error_msg` por cuenta. El color y el cálculo de "atraso" se hacen en el front (`_scraperStatusColor`), usando el intervalo del schedule para definir el umbral del amarillo. El chip muestra el detalle (último OK / error) en el tooltip.

## 0.8.31

- **Ordenar cuentas con flechas ▲▼** (`db.py`, `routes/cuentas.py`, `static/app.js`, `static/style.css`): ahora se puede definir el orden de las cuentas y se respeta en todos lados (tab Cuentas, chips de saldos de la home y combos de filtro de fuente), porque todos consumen `get_cuentas()` en orden de array.
  - DB: nueva columna `cuentas.orden` (INTEGER). Migración con backfill del orden actual (activa primero, luego alfabético) para no alterar nada al actualizar. Cuentas nuevas (`create_cuenta_auto`/`create_cuenta_manual`) reciben `orden = max+1` (van al final). `get_cuentas()` ordena por `orden`.
  - `reorder_cuentas(fuentes)` reasigna el orden según la lista recibida; expone `POST /api/cuentas/reorder`.
  - UI: cada tarjeta del tab Cuentas tiene flechas subir/bajar en el header (deshabilitadas en los extremos). El reorden es optimista (re-render inmediato + persiste; si falla, resync y toast de error) y refresca chips y combos. Se eligieron botones en vez de drag&drop por robustez en la PWA de iOS (el drag nativo no anda por touch en Safari).

## 0.8.30

- **IOL: separar saldo en pesos y dólares en dos cuentas** (`scrapers/invertironline.py`, `routes/cuentas.py`, `db.py`, `static/app.js`): hasta ahora InvertirOnline volcaba ARS y USD en una sola cuenta `MULTI` (un chip "ARS · USD"). Ahora el scraper rutea por `product_key` igual que BBVA: lee `__cuentas__`, resuelve `fuente_ars`/`fuente_usd` y, si existe una cuenta linkeada con product_key="USD", entra en **modo split** (saldo y operaciones en dólares van a la cuenta USD; pesos a la ARS). Si no hay cuenta USD, mantiene el **modo MULTI** legacy intacto (compatibilidad hacia atrás).
  - `_resolve_fuentes()` nuevo helper que decide split vs MULTI y loguea el mapeo.
  - `_fetch_operaciones`/`_op_to_movimiento` ahora reciben `fuente_ars`/`fuente_usd` y asignan la fuente de cada operación según su moneda.
  - Backend (`routes/cuentas.py`): al crear una cuenta auto linkeada a una instancia IOL, el `product_key` se fuerza a la moneda (ARS/USD), análogo a BBVA. Al crear la cuenta USD se invoca `split_iol_multi_to_ars()` que migra la cuenta MULTI preexistente a ARS pura (moneda='ARS', product_key='ARS', `saldo_usd=0`).
  - UI (`static/app.js`): el modal "Crear nueva cuenta" ya asigna `product_key` por moneda también para InvertirOnline (antes solo BBVA), y el hint lo aclara. Flujo: crear cuenta "InvertirOnline USD" (moneda USD, tipo Scraper) y linkearla a la **misma instancia IOL** existente — no hace falta un segundo login ni un parser nuevo.

## 0.8.29

- **Chips de la home más bajos** (`static/style.css`): se sacó el `min-height:3rem` (y el centrado vertical) de los chips de saldos y vencimientos, y se bajó el padding, volviendo al alto compacto anterior. Además los grids ahora usan `align-items:start`: las celdas ya no se estiran a la más alta, así un chip que envuelve (ej. IOL multi-moneda) crece solo él sin agrandar a los demás. Se mantiene el ancho uniforme (columnas iguales). El formato de IOL (moneda y valor en dos renglones) se dejó tal cual a pedido.

## 0.8.28

- **Widgets de la home: chips uniformes** (`static/app.js`, `static/style.css`): los chips de saldos y de vencimientos quedaban del ancho de su contenido (tamaños dispares). Ahora ambos widgets vuelven a `display:grid` con columnas iguales (`minmax(190px,1fr)`) y cada chip llena su celda (`width:100%`, `min-height:3rem`, esquinas redondeadas de 10px), así quedan parejos. La línea "Tarjetas al día" ocupa toda la fila.
- **Vencimientos respetan el nombre custom de la cuenta** (`static/app.js`): el widget de tarjetas mostraba el label fijo de la fuente (`_FUENTE_LABELS`, ej. "BBVA Mastercard") en vez del nombre editado en Config → Cuentas. Se agregó `_cuentaNombre(fuente)` que toma `cuenta.nombre` de `/api/cuentas` (con fallback al label fijo). Como saldos y vencimientos se cargan en paralelo, `loadSaldos` ahora re-renderiza los vencimientos al terminar (cacheados en `_vencData`) para garantizar que los chips muestren el nombre correcto sin importar el orden de carga.

## 0.8.27

- **Fix scraper BBVA tarjetas: signo de "SU PAGO EN PESOS/DOLARES"** (`scrapers/bbva_tarjetas.py`): el `else: abs(monto)` forzaba positivo cualquier transacción cuyo `transactionType.id` no estuviera en `_CREDITO_TYPES`, pisando el signo negativo que manda la API para los pagos. Ahora: si el monto ya viene negativo de la API, se respeta como crédito (`monto < 0`) sin importar el tx_type.

## 0.8.26

- **Scraper BBVA tarjetas: log de transactionType** (`scrapers/bbva_tarjetas.py`): agrega línea `[tx]` al log por cada transacción, mostrando `concept`, `transactionType.id`, `transactionType.description` y `amount` tal como los devuelve la API. Permite diagnosticar el signo correcto para "SU PAGO EN PESOS/DOLARES" y otros tipos.
- **Parser BBVA: comentario corregido** (`parsers/bbva.py`): el comentario sobre "SU PAGO" decía "monto < 0" cuando ahora se importa como positivo.

## 0.8.25

- **Parser BBVA: "SU PAGO EN PESOS/DOLARES" como positivo** (`parsers/bbva.py`): el PDF de BBVA muestra estos registros con monto negativo (crédito sobre el saldo). Ahora se aplica `abs()` al monto para que queden positivos (`monto > 0` = egreso), consistente con la convención del sistema y con cómo aparece "Pago de Tarjeta" desde el lado del banco.

## 0.8.24

- **Fix: barra de estado de iOS pisaba el navbar** (`static/index.html`): en la PWA agregada a la pantalla de inicio, el reloj/batería de iOS se superponían con "Gastos" y el email (la versión quedaba tapada). Se cambió `apple-mobile-web-app-status-bar-style` de `black-translucent` a `black`: así iOS reserva el espacio de la barra de estado en vez de dibujar el contenido por debajo, sin depender de que `env(safe-area-inset-top)` resuelva correctamente (estaba dando 0 en ese contexto). La barra negra combina con el navbar azul oscuro.

## 0.8.23

- **Versión más legible en el navbar** (`static/style.css`): el número de versión junto a "Gastos" (`.app-version`) pasó de `#94a3b8` a `#cbd5e1`, bastante más claro, para que se lea bien sobre el fondo oscuro del navbar (también en iOS PWA).

## 0.8.22

- **pago_confirmado (tilde verde) ahora cubre pagos del propio scraper/PDF de la TC** (`db.py`): antes solo se ponía verde si había un vínculo `transfer_pairs` (banco↔TC emparejados). Ahora también se activa cuando existe un gasto con `categoria="Pago de Tarjeta"` y `fuente = fuente_de_la_TC` (es decir, el pago fue importado desde los propios movimientos de la tarjeta — scraper Galicia, scraper BBVA, o parser PDF). Diferencia con amarillo: amarillo acepta pagos de cualquier fuente; verde exige que sea la TC misma quien confirme el pago recibido.
- **Parser BBVA MC/Visa: importar "SU PAGO EN PESOS" y "SU PAGO EN DOLARES"** (`parsers/bbva.py`): estos registros eran skipeados por `_SKIP_RE`. Ahora se importan como ingresos (`monto < 0`). Taggeados como "Pago de Tarjeta" activan el tilde verde de pago confirmado.

## 0.8.21

- **Diagnóstico vencimientos en Log unificado** (`db.py`): `list_vencimientos()` ahora loguea en `[venc]` la config de matching (días, tolerancia, categorías) y una línea por fuente con `sum_ars`, `total_ars`, `pago_confirmado` y `pago_probable`. Visible en Config → Log filtrando por origen `db`. Se dispara cada vez que se carga la pantalla principal.

## 0.8.20

- **Fix crítico: tabla app_log nunca se creaba** (`db.py`): `_run_migrations(conn)` intentaba crear la tabla `app_log` llamando a `init_app_log_table()`, que internamente abría una **segunda conexión** a la misma DB. Como `init_db()` ya tenía una transacción activa en la primera conexión, SQLite tiraba "database is locked" luego del timeout → la tabla nunca se creaba → todos los `write_log()` fallaban en silencio. Fix: crear la tabla directamente con el `conn` ya abierto que recibe `_run_migrations`, sin abrir una segunda conexión.

## 0.8.19

- **Fix log tab** (`static/app.js`): corregido `ReferenceError: Can't find variable: apiFetch` — las funciones `loadLogs`, `loadLogSources` y `clearLogs` usaban `apiFetch()` que no existe; reemplazado por `fetch(\`${BASE}/api/...\`)` como el resto de la app.

## 0.8.18

- **Log unificado** (`app_log.py`, `routes/logs.py`, `main.py`, `scraper_scheduler.py`, `db.py`): todos los eventos de la app ahora se guardan en la tabla `app_log` de cada usuario (ring buffer de 2000 entradas en `gastos.db`). Un nuevo `DBLogHandler` se adjunta al root logger en el startup para capturar todo `logger.info/warning/error` de los módulos Python. Los runs de scrapers también escriben su log detallado (incluyendo el desglose de saldo por movimiento) al finalizar cada ejecución, vía `write_scraper_run_log`. Nueva pestaña **Config → Log** en la UI con tabla de logs, filtros por origen y nivel, autorefresh cada 30 segundos y botón para borrar. Resuelve el problema fundamental de que los `logger.info()` de los módulos Python eran invisibles en el log del add-on (solo uvicorn loggueaba).
- **Cleanup diagnóstico 0.8.17** (`routes/stats.py`): se eliminó el endpoint temporal `/stats/vencimientos/debug` y el import de `_conn as _db_conn` en ese archivo.

## 0.8.17

- **Diagnóstico vencimientos** (`db.py`): log temporal de `pago_confirmado`/`pago_probable` por fuente y de los gastos candidatos a "pago" evaluados en `list_vencimientos`. Aparece en el log del add-on como `[venc-diag]` y `[venc-diag-cand]`. Se eliminará una vez resuelto el issue de detección de pago en galicia_mc.

## 0.8.16

- **Saldo delta: desglose por movimiento con saldo corriente** (`scraper_scheduler.py`): cuando el auto-saldo está activo y hay movimientos nuevos, el log ahora muestra una línea por movimiento (ordenados cronológicamente) con el efecto sobre el saldo y el saldo acumulado resultante. Facilita identificar drifts cuando el saldo calculado no coincide con el real. Ejemplo: `2026-06-06  Merpago*knowhere  -$91.300,00  →  +$2.600.294,75`

## 0.8.15

- **Widget vencimientos: detectar pago importado por el scraper de la misma tarjeta** (`db.py`): el `pago_probable` exigía `monto > 0`, asumiendo que el pago siempre viene de la cuenta bancaria (egreso). Pero el scraper de Galicia (y en general cualquier scraper de TC) importa el "Pago de tu tarjeta" con `monto < 0` (crédito en la TC). El fix: cambiar la condición a `monto != 0` y usar `ABS(monto)` en la comparación de importe, para que funcione en ambas direcciones.

## 0.8.14

- **Galicia: pagos al resumen no importaban** (`scrapers/galicia.py`): el BFF de Galicia no usa `transaction_date` ni `date` para los pagos, sino campos como `payment_date`, `posting_date`, `operation_date`, `processing_date`, `value_date` o `submission_date`. `_parse_payment` ahora prueba todos esos nombres en orden. También se agregó un log de los campos disponibles cuando el pago se saltea por falta de fecha, para facilitar futuros diagnósticos.

## 0.8.13

- **Home más compacta: resumen colapsable + chips** (`static/index.html`, `static/app.js`, `static/style.css`): la zona superior (saldos + tarjetas), que antes ocupaba media pantalla en *todas* las tabs, se rediseñó en una sola UI más liviana.
  - **Gráfico mes-a-mes movido a la tab Gráficos**: el `home-chart-card` salió del tope global y vive ahora dentro de Gráficos (junto a "Presupuesto vs real"). Se agregó un `_monthlyChart?.resize()` al activar la tab para evitar que Chart.js quede mal dimensionado al volver. La carga inicial no cambia: `loadMonthlyChart()` sigue corriendo al arranque (mantiene el poblado del filtro de meses y el primer `loadGastos`).
  - **Resumen colapsable**: saldos + tarjetas quedan arriba (visibles en todas las tabs) envueltos en un contenedor con botón "Resumen ▾/▸" que pliega/despliega todo, recordando el estado en `localStorage` (`home-summary-collapsed`).
  - **Saldos como chips**: cada cuenta es un chip `NOMBRE $X`; el tap abre el input de edición inline (se reusa `toggleSaldoEdit`/`saveSaldo`, mismos IDs).
  - **Vencimientos como chips**: las pendientes se muestran prominentes (`💳 AMEX $X · 3d`, coloreadas por urgencia) y las **pagadas** (✓ confirmado o probable) colapsan a un chip tenue `✓ AMEX` al final. Si están todas pagadas, una sola línea "💳 Tarjetas al día". El **tap sobre el chip expande la card completa** (monto, RG 5617, PDF, próximos), donde sigue funcionando el doble-clic para ver el monto sin RG.

## 0.8.12

- **Config: menos pestañas, mejor agrupadas** (`static/index.html`, `static/app.js`): la barra de Config pasó de 10 a 6 pestañas. Se creó la pestaña **Procesamiento** que junta Categorización + Importación (dedup) + Período + Vencimientos como **secciones colapsables** (mismo patrón de acordeón que Personas, con estado recordado en `localStorage` vía `_restoreCfgSections`). **Interfaz** quedó como anteúltima y **Datos** como última. La pestaña **Datos** ahora absorbe la antigua **⚠ Borrar** (como sección al pie) y suma el export a Excel. Orden final: Categorías · Personas · Cuentas · Procesamiento · Interfaz · Datos.
- **Exportar a Excel movido a Config → Datos** (`static/index.html`, `static/app.js`): se sacó el botón "Exportar Excel" de la barra de filtros de Gastos y se llevó a Config → Datos como "⬇ Exportar gastos (.xlsx)". Ya **no** respeta los filtros de la tab Gastos: baja siempre el dataset completo (el endpoint `/api/gastos/export` se llama sin parámetros), acorde a su nuevo lugar en la sección de datos.
- **Presupuesto: salto rápido a los gastos de cada fila** (`static/app.js`): cada fila con gasto > 0 (categoría o subcategoría) muestra un botón **↗** que abre la tab Gastos ya filtrada por esa categoría (incluye descendientes) y por el mes seleccionado en el presupuesto. La selección se refleja en los chips de categoría. El botón se cablea con `data-presup-jump` + `.onclick` (robusto ante apóstrofos en el nombre, evita data dinámica en atributos `onclick`).

## 0.8.11

- **Gastos: lista como tarjetas en móvil** (`static/index.html`, `static/style.css`, `static/app.js`): en pantallas ≤640px cada movimiento se muestra como una tarjeta apilada en vez de una tabla con scroll horizontal. Se mantiene un único DOM (la misma `<tr>/<td>`); en móvil el `<tr>` pasa a `display:flex` y cada celda se reordena con `order` (fecha + monto grande arriba, descripción a ancho completo, fuente + persona, y categoría + acciones). Como el orden del DOM no cambia, todos los handlers de edición (fecha, persona, categoría con su autocomplete flotante, descripción in-place, borrar) siguen funcionando sin tocar el JS de eventos. El escritorio queda idéntico (tabla normal).
  - Se restauró el indicador de moneda (ARS/USD) en la tarjeta, que en móvil estaba oculto.
  - Se agregó `placeholder="Categoría"` al input de categoría para que las celdas vacías sean claras.
  - Se eliminó la meta-línea `mov-mobile-meta` introducida en 0.8.10 (ya no hace falta: fuente y persona son celdas propias dentro de la tarjeta), lo que además corrige que esa línea se borrara al editar la descripción.
- **Barra de orden en móvil** (`static/index.html`, `static/style.css`, `static/app.js`): como en modo tarjeta se oculta el `<thead>` (donde vivía el ordenamiento por columna), se agregó una barra "Ordenar:" con un select (Fecha / Monto / Categoría / Descripción / Persona) y un botón para invertir la dirección, visible solo en móvil y sincronizada con el estado de orden (`_gastosSort`).

## 0.8.10

- **Usabilidad móvil — tap targets y safe-area del notch** (`static/index.html`, `static/style.css`): se agregó `viewport-fit=cover` al viewport y padding con `env(safe-area-inset-*)` en navbar, contenedor y botón "volver arriba", para que en PWA standalone el contenido no quede bajo el notch / barra de estado. En dispositivos táctiles (`@media (pointer: coarse)`) se ampliaron las áreas táctiles: botones de acción 40×38px, selects/inputs de fila ≥38px, tabs ≥42px. (Las columnas de Transferencias ya colapsaban a 1 columna en móvil.)
- **Config → Categorías: filas como tarjetas en móvil** (`static/style.css`, `static/app.js`): la tabla de categorías era demasiado ancha en iPhone (scroll horizontal). En móvil ahora cada fila se apila como tarjeta: el nombre ocupa la primera línea y los campos "Padre"/"Especial" bajan etiquetados (`data-lbl` + `::before`). El select de categoría padre pasa a ancho completo.
- **Gastos: lista más angosta en móvil** (`static/index.html`, `static/style.css`, `static/app.js`): las columnas Fuente y Persona se ocultan en móvil y su info se muestra como meta-línea (badge de fuente + persona) debajo de la descripción, que ahora puede usar todo el ancho. El monto se agranda y se pone en negrita para destacarlo.

## 0.8.9

- **Usabilidad en iOS — fin del zoom automático al tocar campos** (`static/style.css`): Safari/iOS hace zoom-in (y no vuelve) cuando se enfoca un input con `font-size < 16px`, lo que rompía la navegación en iPhone porque casi todos los controles estaban en `.85rem`. Se agregó una media query `@media (pointer: coarse)` que fuerza `font-size:16px` en `input`/`select`/`textarea` en dispositivos táctiles (con `!important` para ganarle a los estilos inline que genera `app.js`; se excluyen checkbox/radio/color/range/file que no disparan el zoom).
- **Teclado numérico en campos de monto** (`static/app.js`): los inputs de saldo (`saldo-input-*`, `ce-inp-*`) y de presupuesto (`presup-input`, `presup-u-input`) son `type="text"` porque usan formato con separadores (`1.234,56`), así que no podían ser `type="number"`. Se les agregó `inputmode="decimal"` para que en móvil abran el teclado numérico en vez del alfabético.

## 0.8.8

- **Backup completo (.zip) y restore desde la UI** (`routes/config_route.py`, `static/index.html`, `static/app.js`): la sub-pestaña **Config → Datos** ahora ofrece un backup completo, no solo la DB suelta.
  - `GET /api/config/export-backup` arma un `.zip` con `gastos.db` (snapshot consistente vía `VACUUM INTO`, sin credenciales de scrapers) + los archivos de config/reglas que viven fuera de la DB (`rules.yaml`, `match_rules.yaml`, `user_config.json`) + un `backup_manifest.json` informativo. El snapshot de la DB se factorizó en el helper `_snapshot_db_no_creds()`, reusado también por el export de solo-DB.
  - `POST /api/config/import-backup` restaura ese `.zip`: valida que traiga un `gastos.db` con header SQLite e `integrity_check=ok` (read-only) **antes** de pisar nada, borra los `-wal`/`-shm` viejos para que no se apliquen sobre la base nueva, reemplaza la DB de forma atómica (`os.replace`), restaura los archivos de config por whitelist de basename (sin zip-slip) y corre `init_db()` para re-migrar si el backup viene de un esquema más viejo.
  - UI: botones "Backup completo (.zip)" y "Solo base de datos (.db)", más "Restaurar desde backup (.zip)" con confirmación (`showConfirm`) por ser destructivo; tras restaurar recarga la página.

## 0.8.7

- **FIX backfill: corregir titular incorrecto de corridas viejas** (`scrapers_db.py`): el backfill de 0.8.6 tenía un guard "no pisar un cardholder ya seteado", que impedía corregir los movimientos que corridas antiguas (≤0.8.1, cuando el fallback estampaba el primer titular del selector) habían marcado mal con un único titular (ej. todos como "ALBERTO ELISE"). Por eso en la UI aparecía un solo titular. Como el `cardholder` proviene del scrape y NO es editable por el usuario, ahora el backfill **sobrescribe** el titular almacenado cuando difiere del recién scrapeado. El caller solo invoca con titular no vacío, así que el fallback (cardholder vacío) nunca borra uno correcto. Tras correr el scraper con esta versión, los tres titulares aparecen en Config → Usuarios.

## 0.8.6

- **Backfill de titular sobre movimientos ya importados** (`scrapers_db.py`): hasta ahora, si un movimiento se importaba sin titular (ej. AMEX en período abierto antes de poder separarlos) y luego el scraper lo volvía a ver con titular, el dedup lo salteaba y el titular nunca se completaba. Ahora, al detectar un duplicado, si el movimiento nuevo trae `cardholder` y el existente no lo tenía, se completa en `raw_data` y —si el gasto ya fue importado— se propaga el usuario según el mapeo titular→persona, **solo si el gasto todavía tiene el usuario por defecto de la fuente (o NULL)**, para no pisar asignaciones manuales ni por regla. Nuevo helper `_backfill_cardholder()`.
  - La propagación del usuario al gasto se intenta en cada corrida (no solo la primera), así que si configurás el mapeo en Config → Usuarios **después** de que el titular ya se detectó, la siguiente corrida del scraper corrige el usuario de los gastos existentes. Idempotente: no reescribe un usuario ya distinto del default.
  - Flujo para los movimientos AMEX actuales: (1) actualizar a esta versión y correr el scraper → completa el titular en los 17 movimientos existentes y los tres titulares aparecen en Config → Usuarios; (2) mapear cada titular a su persona; (3) correr el scraper otra vez → los gastos quedan atribuidos.

## 0.8.5

- **AMEX: atribución por titular en período abierto, vía HTML crudo del servidor** (`scrapers/amex.py`): se logró separar los movimientos por titular también en el período abierto. El HTML CRUDO que devuelve `statement.do` SÍ trae las secciones `div#txnsCard0/1/2` (una por titular), pero el JavaScript de AMEX las **colapsa en una lista plana** tras cargar la página, por eso Selenium veía 0 secciones en el DOM en vivo (analizado con un HAR de la sesión). La solución: traer el HTML crudo con un **XHR síncrono same-origin** y parsearlo con el **`DOMParser` del browser** (que NO ejecuta scripts → las secciones quedan intactas), devolviendo las filas ya estructuradas a Python. Es la vía primaria; el parseo del DOM en vivo queda como fallback si el XHR falla.
  - Nuevos métodos `_scrape_raw_txns()` (XHR + DOMParser + log de conteo por titular) y `_row_from_raw()` (convierte cada fila cruda en `MovimientoRaw`, misma lógica de fecha/monto/moneda que `_parse_row`).
  - **Validado offline** contra el HTML real de un resumen abierto: 17 filas → 17 movimientos, repartidos Alberto 1 / Magdalena 6 / Sebastián 10, con montos y fechas que cruzan con el log de dedup.
  - _Nota:_ los movimientos ya importados (sin titular) no se reasignan solos por el dedup; aplica a importaciones nuevas.

## 0.8.4

- **AMEX: revertida la separación por titular en período abierto** (`scrapers/amex.py`): la iteración del selector `#cardAccount` agregada en 0.8.3 no funciona y se quitó. Confirmado en vivo: en la vista "Últimos Movimientos" (período abierto), seleccionar cada titular deja las **mismas 17 filas** (`17 coinciden con baseline` para los tres → `0 asignados`). El selector solo togglea client-side las secciones `txnsCard*`, que en el período abierto **no existen**, así que filtrar no separa nada. La iteración costaba 3 page-loads por corrida sin beneficio. Se vuelve al fallback simple: con un único titular se asigna; con varios, `cardholder` queda vacío y el import resuelve por el default de la fuente. **La atribución por titular solo es posible desde resúmenes CERRADOS** (secciones `txnsCard0/1/2`), que el scraper ya maneja. Eliminados `_separar_por_titular()`, `_select_cardholder()` y `_mov_key()`.

## 0.8.3

- **AMEX: separación por titular en el período abierto** (`scrapers/amex.py`): en la vista "Últimos Movimientos" (período abierto) la página no trae las secciones `txnsCard*` por titular, así que los movimientos venían mezclados y sin atribuir (en 0.8.2 quedaban con `cardholder` vacío). Ahora, cuando hay varios titulares, el scraper itera el selector `#cardAccount`: selecciona cada titular, lee la lista filtrada y asigna cada movimiento al titular bajo cuyo filtro aparece **de forma exclusiva**.
  - **Auto-correctivo**: se cruza contra la vista completa (`baseline`) por clave `fecha|descripción|monto|moneda`. Si el filtro no separa (cada titular muestra todo) o cambia de producto (colisión `name="sorted_index"`), los movimientos quedan ambiguos → `cardholder` vacío y el import resuelve por el default de la fuente. Nunca asigna de más.
  - **Diagnóstico en el log**: por cada titular se loguea cuántas filas muestra y cuántas coinciden con el baseline, más un resumen "N asignados, M ambiguos". Esto revela si el filtro de AMEX realmente separa en el período abierto.
  - Nuevos helpers `_separar_por_titular()`, `_select_cardholder()` y `_mov_key()`.
  - _Nota:_ los movimientos ya importados no se reasignan retroactivamente (el dedup los saltea); la separación aplica a resúmenes/movimientos nuevos.

## 0.8.2

- **AMEX: atribución de movimientos por titular de tarjeta** (`scrapers/amex.py`, `scrapers_db.py`, `user_config.py`, `routes/config_route.py`, `static/index.html`, `static/app.js`): las tarjetas AMEX con adicionales (ej. Magdalena, Sebastián, Alberto) ahora pueden asignar cada movimiento a la persona correcta. El scraper ya leía el titular del selector `#cardAccount` y lo guardaba en `raw_data.cardholder`, pero ese dato nunca se usaba: al importar, el movimiento solo miraba `raw_data.usuario` y caía al default por fuente, quedando todo bajo una sola persona.
  - **Nuevo mapeo titular → persona en la UI** (Config → Usuarios → "Titular de tarjeta → persona"): tabla editable que mapea cada titular (texto exacto del resumen, ej. `SEBASTIAN ALB - 11005`) a una persona configurada. Se guarda en `user_config.cardholder_usuario`. Los titulares se autocompletan desde los que ya aparecieron en `movimientos_raw` (endpoint `GET /api/config/cardholders`).
  - **Resolución de usuario al importar** (`importar_a_gastos`): nueva prioridad intermedia — 1) `raw_data.usuario` explícito → 2) mapeo `cardholder_usuario` → 3) default por fuente. El renombre de personas propaga al mapeo.
  - **FIX período abierto**: en la vista "Últimos Movimientos" (período abierto) la página no separa por titular (`txnsCard*` ausentes); el fallback fijaba todos los movimientos al primer titular del selector (Alberto), lo que era incorrecto. Ahora solo asigna titular si hay uno único; con varios, deja `cardholder` vacío y el import resuelve por el default de la fuente. La separación real por titular en el período abierto (iterando el selector) queda pendiente de validar con un log en vivo.

## 0.8.1

- **Export de la base de datos desde la UI** (`routes/config_route.py`, `static/index.html`, `static/app.js`): nueva sub-pestaña **Config → Datos** con un botón "Exportar base de datos (.db)". El endpoint `GET /api/config/export-db` genera un snapshot consistente de la DB del usuario actual con `VACUUM INTO` (íntegro aunque la DB esté en modo WAL con escrituras en curso, a diferencia de copiar el archivo crudo) y lo descarga. Por seguridad, las credenciales cifradas de scrapers se vacían del snapshot (`scraper_instances.config='{}'`, `config_encrypted=0`) antes de enviarlo: si se restaura, hay que reingresarlas. El archivo temporal se borra tras la descarga vía `BackgroundTask`.

## 0.8.0

Compliance del add-on con la documentación oficial de Home Assistant (apps) y limpieza de configuración (`config.yaml`).

- **Ingress deshabilitado, acceso por puerto 8000** (`config.yaml`): se quitaron `ingress: true`, `ingress_port` y `panel_icon` (este último solo aplica con ingress). El add-on ya no aparece en la barra lateral de HA; se accede directo por `http://<ip-ha>:8000`, que es el modo de uso real. El manejo de `X-Ingress-Path` en `main.py` se deja como está (inocuo: sin ingress el header no llega y el prefijo queda vacío).
- **`url` agregada** (`config.yaml`): link a la página del add-on (`.../tree/main/gastos-tarjetas`), que es lo que muestra el botón "Visit add-on page".
- **`stage: stable`** (`config.yaml`): se declara explícito el estado del add-on (antes era el default implícito).
- **`watchdog` agregado** (`config.yaml`): `tcp://[HOST]:[PORT:8000]` para que el Supervisor detecte si el proceso se cae y reinicie el add-on.
- **`map: data:rw` eliminado** (`config.yaml`): `/data` siempre se monta persistente y escribible sin declararlo; la entrada era redundante.
- **Limpieza de iconos viejos**: se borraron `icono-sb.ico/png/svg` de la raíz del add-on (redundantes con `icon.png` y `logo.png`, los únicos que usa HA). Las copias en `rootfs/app/static/icono-sb.*` se mantienen porque las usa la web app.

## 0.7.2

- **FIX: el grid de los widgets no se aplicaba (estilo inline lo pisaba)** (`static/app.js`): en 0.7.1 pasé `.saldos-widget` y `.vencimientos-widget` a `display:grid` en el CSS, pero `renderSaldos()` y `renderVencimientos()` setean `widget.style.display` **inline** al mostrar el widget, y ese valor era `"flex"` — que tiene mayor prioridad que la hoja de estilos y dejaba ambos widgets en flex (anchos por contenido, cards de distinto ancho). Cambiados los dos a `widget.style.display = "grid"`. Verificado en preview: ahora las columnas son iguales (mismo ancho) y los vencimientos quedan alineados debajo de los saldos.

## 0.7.1

- **Galicia: próximo cierre y próximo vencimiento** (`parsers/galicia.py`): el parser leía la fila de 6 fechas de Galicia pero solo usaba el cierre/venc actual (índices 2 y 3) y descartaba el próximo cierre/venc (índices 4 y 5), por eso los widgets de vencimiento de Galicia nunca mostraban "Próx. cierre · venc.". `_detect_statement_dates()` ahora devuelve también esos dos y `parse()` los expone en `self.proximo_cierre` / `self.proximo_venc` (leídos por `upload.py`). Verificado con los PDFs de muestra (ej. próx. cierre 28-May-26 · venc. 08-Jun-26). **Requiere re-importar el PDF** para poblar los imports existentes.
- **Widgets de saldos y vencimientos con tamaño consistente** (`static/style.css`): los contenedores usaban `display:flex`, que dimensionaba cada card según su contenido (anchos dispares; ej. el card con la línea larga de "Próx. cierre…" quedaba más ancho). Pasan a `display:grid` con `repeat(auto-fill, minmax(190px, 1fr))`: columnas de igual ancho y, por el stretch de grid, igual alto por fila. En pantallas angostas baja a una columna. Verificado en preview.
- _Nota BBVA Mastercard:_ el parser de BBVA sí extrae el próximo cierre/venc correctamente (probado contra los PDFs de muestra Visa y Master, incl. May26). Si una tarjeta no lo muestra es porque ese import es anterior a la feature — **re-importá el PDF** y aparecerá.

## 0.7.0

Tanda de mejoras de seguridad, performance y configurabilidad (review del código).

**Seguridad**
- **CORS eliminado** (`main.py`): se quitó el `CORSMiddleware` con `allow_origins=["*"]` + `allow_credentials=True`. Esa combinación permitía que cualquier sitio web hiciera requests con la cookie de sesión del usuario y leyera sus datos. La app es una PWA same-origin (ingress / puerto propio), no necesita CORS. Además la cookie de sesión ahora declara `same_site="lax"` y `max_age` explícito.
- **Rate limiter de login a prueba de spoofing** (`routes/auth.py`): `_client_ip()` usaba `X-Forwarded-For` / `X-Real-IP`, headers que el cliente controla; con el puerto expuesto directo (sin la auth de HA) un atacante los cambiaba en cada intento y evadía el límite de fuerza bruta. Ahora se usa siempre el peer TCP real (`request.client.host`), que no se puede falsificar.
- **`verify_password` timing-safe** (`auth.py`): reemplaza `==` por `hmac.compare_digest()` al comparar el hash (igual que `verify_admin`).

**Performance**
- **Índices en la tabla `gastos`** (`db.py`): se agregaron índices en `fecha`, `fuente`, `categoria`, `import_id` y compuesto `(moneda, fecha)`. Antes todos los listados/agregados hacían full-scan + sort. Es la mejora de mayor impacto.
- **WAL + busy_timeout** (`db.py`): `journal_mode=WAL` + `synchronous=NORMAL` (lecturas concurrentes con la escritura del scheduler sin bloquearse) y `busy_timeout=5000` en cada conexión (espera en vez de tirar "database is locked").
- **Cache de `get_special_categorias`** (`db.py`): se cacheaba en cada llamada (abría conexión + leía YAML, varias veces por request). Ahora se cachea por usuario, invalidado por mtime de la DB (+ `-wal`), `rules.yaml` y `user_config.json`.
- **Tope de seguridad en `GET /gastos`** (`db.py`, `routes/gastos.py`): `list_gastos` acepta `limit`/`offset` y el endpoint aplica un cap (`_GASTOS_SAFETY_CAP=20000`) para que el caso "ver todo" no traiga toda la historia a memoria. El uso normal ya va acotado por mes.
- _Nota:_ `monto` se deja como está (ya se trata como float en todo el flujo: SQL agrega con `CAST AS REAL`, el front hace `parseFloat`); migrar la columna no daba ganancia real y se evita el riesgo sobre datos financieros.

**Configurable desde la UI** (antes hardcodeado en Python)
- **Categorización por IA** (`categorizer.py`, `user_config.py`, `config_route.py`, `index.html`, `app.js`): el prompt y la lista de categorías sugeridas dejaron de estar fijos en `categorizer.py`. Editables en `Config → Categorización`, persistidos en `user_config.json` (`categorizer_prompt` con placeholders `{categorias}`/`{desc}`, `categorizer_categorias`) vía `GET/PUT /api/config/categorizacion`.
- **Categorías especiales fijas** (`db.py`, `user_config.py`, `config_route.py`, `index.html`, `app.js`): las antes hardcodeadas `_BUILTIN_SPECIALS` (Transferencia, Transferencia Intercuentas, Pago de Tarjeta) ahora se editan en `Config → Categorización` (`categorias_especiales_builtin`, `GET/PUT /api/config/especiales`); el default sigue siendo el mismo.
- **Paleta de íconos PWA por fuente** (`main.py`, `user_config.py`, `config_route.py`, `index.html`, `app.js`): la antes hardcodeada `_FUENTE_ICON_STYLES` (color de fondo, color de texto y siglas por banco) se edita en `Config → Interfaz → Íconos PWA` (`fuente_icon_styles`, `GET/PUT /api/config/iconos`, validación hex). `_icon_style()` mergea las overrides del usuario sobre los defaults.

## 0.6.20

- **Config → Categorías: la subcategoría nueva se inserta debajo del padre** (`app.js`): al tocar el `+` de una categoría padre, el input de la nueva subcategoría ahora aparece indentado justo debajo de los hijos de ese padre, en vez de mandarse al final de toda la lista. `renderCategoriasManaged()` agrupa los ítems `_new` por `parent_nombre` (`newByParent`) y los emite dentro del bloque de su padre; las categorías nuevas de nivel superior (sin padre) siguen yendo al final. El foco tras crear apunta al input por `data-i` en vez de "el último del DOM".

## 0.6.19

- **Selector de categoría en Gastos: árbol + sin crear categorías nuevas** (`app.js`): el autocompletado de la columna Categoría en la grilla de Gastos ahora muestra las categorías en forma de árbol (padres y, debajo, sus hijos indentados con `└`), construido desde `_catHierarchy` vía el nuevo helper `_orderedCatTree()`. Al filtrar por texto se conserva el padre de cualquier hijo que matchee para mantener legible la jerarquía. Además, `saveCategoria()` rechaza valores que no existan en `_catList` (salvo vacío para limpiar) mostrando un toast de error: ya no se crean categorías nuevas tipeando desde la grilla; hay que elegirlas de la lista o crearlas en `Config → Categorías`.
- **Config → Categorías: subcategorías y expansión por toque** (`app.js`): cada categoría padre (fila de nivel superior) muestra un botón `+` para crear una nueva subcategoría asociada (precarga `parent_nombre` y enfoca el input). El detalle de keywords ahora se expande/colapsa con un solo clic sobre el nombre de la categoría (con cursor `▸`/`▾` como indicador), reemplazando el antiguo botón `+`/`−`; el doble clic sigue renombrando (se usa un timer de 220 ms para distinguir click simple de doble).

## 0.6.18

- **Badge "pago probable": categorías de pago configurables** (`db.py`, `config_route.py`, `user_config.py`, `index.html`, `app.js`): la confirmación heurística solo miraba gastos con categoría exactamente `Pago de Tarjeta`, así que un pago categorizado como transferencia (ej. "PAGO DE TARJETA VISA" quedó como `Transferencia Intercuentas`) no encendía el badge. Ahora la lista de categorías que cuentan como pago es configurable en `Config → Vencimientos` (default `Pago de Tarjeta`, una por línea), persistida en `user_config.json` vía `venc_pago_match_categorias` en `GET/PUT /api/config/venc-match`. La consulta usa `categoria IN (...)` con placeholders generados internamente (sin inyección).

## 0.6.17

- **FIX: session_secret leído desde archivo en Python** (`main.py`): en lugar de depender de que `run.sh` exporte `SESSION_SECRET` como env var (frágil si el supervisor reinicia uvicorn directamente), `_load_session_secret()` lee el archivo `/data/session_secret` en Python al arrancar. Si no existe lo genera y lo persiste. Esto garantiza que el secreto sea siempre el mismo entre reinicios y evita el logout inesperado al recargar la página.

## 0.6.16

- **REFACTOR: credenciales bancarias migradas a DB exclusivamente** (`scraper_credentials.py`): `scraper_credentials.json` ya no se escribe. Todas las lecturas/escrituras de credenciales van directo a `scraper_instances` (cifradas con Fernet si `SCRAPER_ENCRYPTION_KEY` está configurada). Se eliminaron `read_creds` y `write_creds`; `get_bank_config`, `set_bank_config`, `creds_for_api` y `find_all_enabled_configs` usan `scraper_instances_db`. El módulo `BANKS` se conserva solo como metadatos de UI. Los archivos `.json` viejos en disco son inofensivos y pueden borrarse manualmente.

## 0.6.15

- **SEGURIDAD: SESSION_SECRET auto-generado** (`run.sh`): se genera un secret único de 48 bytes al primer arranque y se persiste en `/data/session_secret`. Elimina el fallback público `"changeme-in-prod"` que permitía forjar cookies de sesión. En `main.py` el fallback también pasó a `secrets.token_urlsafe(48)` (sesiones no persistentes si no hay secret en disco, pero sin secreto predecible).
- **SEGURIDAD: Rate limiting en login** (`routes/auth.py`): 10 intentos fallidos por IP en 15 minutos disparan un bloqueo temporal. Previene brute force desde internet.
- **SEGURIDAD: Validación de X-Ingress-Path** (`main.py`, `routes/auth.py`, `routes/admin.py`): el header se valida contra regex `^(/[a-zA-Z0-9_/-]*)?$` antes de usarlo en redirects y en HTML/JS. Cierra XSS y open redirect via header injection.
- **SEGURIDAD: XSS en panel admin** (`routes/admin.py`): emails de usuarios se escapan con `html.escape()` en todos los lugares donde se inyectan en HTML (spans, inputs hidden, onclick, flash messages).
- **SEGURIDAD: Comparación timing-safe de ADMIN_PASSWORD** (`auth.py`): reemplaza `==` por `hmac.compare_digest()`.
- **SEGURIDAD: Cifrado de scraper_credentials.json** (`scraper_credentials.py`): si `SCRAPER_ENCRYPTION_KEY` está configurada, el JSON completo de credenciales bancarias se cifra con Fernet al escribir. Los archivos en formato plaintext se leen sin cambios (migración transparente).

## 0.6.14

- **FIX CRÍTICO: scraper_uid check ahora filtra por fecha** (`scrapers_db.py`): el check de UID en raw_data NO tenía `AND fecha = ?`, así que UIDs genéricos (como `numero_operacion="00001"`) que se repiten en múltiples días causaban falsos positivos cross-date. Ejemplo: id=108 (858625.0 del 05-08) se usaba como "existing" para el movimiento 288000.0 del 06-03 porque ambos compartían el mismo UID genérico. Ahora el scraper_uid check requiere fecha exacta para el match, evitando estos falsos positivos. **Esto debería resolver los movimientos faltantes del 06-03** (288K ARS, 736.56 USD).

## 0.6.13

- **Logging granular: mostrar QUÉ check encontró el existing en cada [dedup-skip]** (`scrapers_db.py`): el log ahora incluye `via scraper_uid`, `via fallback_descriptor`, etc., para identificar exactamente cuál check está causando cada skip. Así se puede debuggear falsos positivos como el id=108 (05-08) siendo usado para un movimiento del 06-03.

## 0.6.12

- **Fix: logging de existing_id ahora muestra el ID real en los [dedup-skip]** (`scrapers_db.py`): en v0.6.11 todos mostraban `(existing_id=?)` porque el Row de SQLite no soporta `.get()`. Ahora accede correctamente al 'id' del Row, así que el próximo run mostrará el ID verdadero de los registros encontrados para cada skip.

## 0.6.11

- **Logging mejorado para debugging de dedup falsos positivos** (`scrapers_db.py`): el log de `[dedup-skip]` ahora muestra el `existing_id` para que se pueda rastrear cuál registro se encontró y por qué. Esto ayuda a diagnosticar casos donde se loguea skip pero el movimiento no existe en la DB (falso positivo de dedup).

## 0.6.10

- **Dedup de contraasientos (movimientos opuestos BBVA)** (`scrapers_db.py`): BBVA devuelve algunos movimientos DOS VECES con signo opuesto (ej. -460.000 y +460.000 el mismo día). Nuevo chequeo en `insert_movimientos_raw`: si llega un movimiento y existe otro con monto opuesto (fuente/fecha/moneda iguales), se skipea el nuevo si el existente es igual/más específico, o se reemplaza el existente si el nuevo es más específico. Emite `[dedup-opuesto-skip]` o `[dedup-opuesto-update]` en el log. Esto resuelve los "duplicados" que veías de $460K y $2.298M del 01/06.

## 0.6.9

- **Logging de dedup en el log del run** (`scrapers_db.py`, `scraper_scheduler.py`): `insert_movimientos_raw` ahora acepta `_log_fn` opcional; cuando se pasa, emite `[dedup-skip]` para cada movimiento descartado como duplicado y `[dedup-insert]` para cada uno efectivamente insertado. El scheduler pasa un colector y extiende `result.log_lines` con esas líneas, haciéndolas visibles en el log del panel de scrapers.

## 0.6.8

- **Fix badge "pago probable": ahora también matchea contra el TOTAL del PDF** (`db.py`): la confirmación heurística (0.6.7) solo comparaba el Pago de Tarjeta contra el saldo *computado* sin RG 5617. En resúmenes con discrepancia parser/PDF (donde el saldo calculado difiere del total real —por eso aparece la línea `PDF: $...` en el widget) el pago nunca matcheaba. Ej. real: Galicia MC con saldo computado $935.666,53 pero total PDF y pago efectivo de $1.822.263,66. Ahora el lado ARS acepta el pago si coincide (±tol_ars) con el saldo sin RG **o** con `i.total_ars` (TOTAL A PAGAR del PDF). Mismo criterio para el lado USD (`i.total_usd`). El gate de "tiene saldo USD" también considera el total del PDF.

## 0.6.7

- **Widget de vencimientos: badge amarillo de "pago probable" (confirmación heurística sin emparejado)** (`db.py`, `config_route.py`, `user_config.py`, `index.html`, `app.js`, `style.css`): hasta ahora el `✓` verde solo aparecía si existía un `transfer_pairs` confirmado bank→tarjeta. Se agregó un segundo estado en `list_vencimientos()` (`pago_probable`) que enciende un **badge amarillo** ("pago hecho pero no 100% validado") cuando hay un gasto categoría **"Pago de Tarjeta"** cerca del vencimiento que matchea el saldo del resumen, aunque no esté emparejado:
  - Lado ARS: un Pago de Tarjeta (ARS, egreso) dentro de **±N días** del vencimiento cuyo monto coincide (±tolerancia ARS) con el saldo en pesos **sin RG 5617** (`net_ars − rg5617`).
  - Lado USD: si el resumen tiene saldo en dólares, además se exige un Pago de Tarjeta (USD, egreso) en la misma ventana que coincida (±tolerancia USD) con `net_usd`. Si no hay saldo USD, ese lado no se evalúa.
  - El pago vive en una cuenta bancaria (fuente distinta a la tarjeta), por eso el monto es la única forma de asociarlo al resumen. El emparejado explícito sigue mostrando el `✓` verde y tiene prioridad sobre el amarillo.
- **Config en la UI** (`Config → Vencimientos`): nueva sub-tab con activar/desactivar la confirmación heurística, ventana de días (default 8), tolerancia ARS (default 5000) y tolerancia USD (default 1). Persisten en `user_config.json` vía `GET/PUT /api/config/venc-match`. La consulta de `list_vencimientos()` lee estos valores en vez de hardcodearlos.

## 0.6.6

- **Ciclo de cobro: se reemplaza el día-ancla por un modelo de DELTA de días** (`db.py`, `config_route.py`, `user_config.py`, `index.html`, `app.js`): en vez de un día fijo del calendario, ahora se configura "cuántos días antes de fin de mes cobrás" (`periodo_delta_dias`, 0..28). Los últimos N días de cada mes se imputan al período del mes siguiente. El delta es relativo al fin de mes —que es como cae el cobro (anteúltimo día hábil)— así que el corte ya no se desfasa según el largo del mes y desaparecen los casos especiales de febrero/bisiesto/overflow.
  - La expresión SQL se simplifica a `substr(date(fecha,'+D days'),1,7)` (correr la fecha D días y tomar el mes). Los overrides pasan a ser `{YYYY-MM: delta}` (delta distinto para un mes calendario puntual) vía un `CASE` por mes. `_periodo_de_fecha` usa `date + timedelta`.
  - UI: input "Delta de días" con texto explicativo en vivo; las excepciones ahora son `YYYY-MM = delta`. Se eliminó el helper `_last_day` (ya no hace falta).
  - Default delta = 2; inactivo de fábrica (comportamiento calendario idéntico al previo cuando está apagado o con delta 0).

## 0.6.5

- **Día-ancla del período ahora admite 1..31 (antes 1..28)** (`db.py`, `config_route.py`, `index.html`, `app.js`): el límite de 28 impedía configurar cortes a fin de mes (anteúltimo día hábil suele caer 29/30). Ahora la fórmula de período *clampea el corte al último día del mes* cuando el mes es más corto que N (p.ej. con ancla 30, en febrero el corte es el 28; en bisiesto, el 29). Reescrita `_mes_sql` con `strftime('%d', ...último día...)` + comparación de día contra el corte clampeado; `_periodo_de_fecha` y los overrides usan la misma lógica con `_last_day()` (vía `calendar.monthrange`). Validado contra bisiestos y cruces de año.

## 0.6.4

- **Fix real del guardado de Período (y de dedup)** (`app.js`): las funciones llamaban a `_authHeaders()`, una función que **no existe** en el código → `ReferenceError` que abortaba el fetch antes de enviarse, tanto en Período como en Config → Importación (dedup). La autenticación es por cookie de sesión (como todos los demás fetch), así que se eliminó el uso de `_authHeaders()` y se dejó solo `Content-Type: application/json` en los PUT. Este era el motivo de que el guardado "no anduviera" pese al fix de `${BASE}` en 0.6.2.

## 0.6.3

- **Bump de versión** para forzar la actualización del add-on en HA (sin cambios de código respecto a 0.6.2).

## 0.6.2

- **Fix: la config de Período no se guardaba bajo ingress de HA** (`app.js`): los fetch de `/api/config/periodo` (y los de `/api/config/dedup`, mismo bug latente) no anteponían `${BASE}` (el prefijo de ingress), así que el PUT/GET pegaban a una ruta inexistente → el guardado fallaba en silencio y al refrescar volvían los defaults. Ahora usan `${BASE}/api/...` como el resto de los fetch.
- **Fix: el input de día-ancla quedaba más chico que el font de la página** (`index.html`): los controles `<input type=number>` no heredan la tipografía por defecto; se le agregó `font:inherit` + padding/borde consistentes con los demás campos de Configuración.

## 0.6.1

- **Ciclo de cobro / período contable configurable** (`db.py`, `user_config.py`, `config_route.py`, `gastos.py`, `index.html`, `app.js`): nueva sección Config → Período para usuarios que cobran cerca de fin de mes y tienen desfasaje entre los gastos del mes y el sueldo. Cuando está activo, los agregados (gráficos, estadísticas y presupuesto) reasignan cada movimiento a su período de cobro en vez del mes calendario; los listados y el detalle siguen mostrando la fecha real.
  - Modelo **día-ancla** (1–28) con etiqueta = "mes que financia" (el período "junio" con ancla 26 abarca del 26-may al 25-jun). Más **overrides por mes** (`YYYY-MM = día`) para los meses donde el corte cayó otro día, con el default cubriendo el resto.
  - Helpers nuevos en `db.py`: `_periodo_cfg()`, `_mes_sql(col)` (expresión SQL aritmética a prueba de overflow de días + `CASE` para overrides), `_periodo_de_fecha()` y `periodo_actual()`. Reemplazan los `substr(fecha,1,7)` y filtros `fecha LIKE` en `monthly_summary`, `stats_monthly_by_category`, `stats_pivot`, `stats_forecast`, `_base_where` y `get_gastos`.
  - El endpoint `/api/gastos/monthly` ahora devuelve `{meses, actual}` para que el front elija el mes por defecto según el período corriente (no el mes calendario). El "mes actual" del forecast/presupuesto también usa el período.
  - Inactivo por defecto: con el ciclo apagado todo queda idéntico al comportamiento calendario previo.

## 0.6.0

- **Bump a versión 0.6**: marca el salto de minor con la incorporación del scraper BBVA enriquecido (campos extra, endpoints de detalle, dedup cross-run configurable desde UI), la tab Config → Importación con reglas de dedup editables, y la regla de proyecto "toda configuración va en la UI".

## 0.5.124

- **Config → Importación: prefijos y exactos de dedup configurables desde la UI** (`index.html`, `app.js`, `config_route.py`, `scrapers_db.py`, `CLAUDE.md`): los sets `_GENERIC_PREFIXES` y `_GENERIC_DESCS` ya no son hardcodeados — se guardan en `user_config.json` y se editan desde Config → Importación con dos textareas (uno por línea). `insert_movimientos_raw` los carga una vez por llamada vía `_load_dedup_config()`. Los defaults hardcodeados siguen siendo el fallback si no hay config guardada. También se actualiza `CLAUDE.md` con la regla: toda configuración debe ir en la UI, no hardcodeada.

## 0.5.123

- **Dedup: agrega "PAGO SERVICIOS Nro:" a prefijos genéricos** (`scrapers_db.py`): "PAGO SERVICIOS Nro:852962" es la descripción temporal que BBVA muestra antes de liquidar el pago de servicio como "PAGO DE SERVICIOS TARJETA 84296031 OP2962 — MASTERCARD". Al no estar en `_GENERIC_PREFIXES`, ambas versiones se insertaban como duplicados. Agregado el prefijo para que la versión enriquecida (específica) reemplace a la genérica en lugar de duplicarla.

## 0.5.122

- **Fix BBVA tarjetas: headers extra para /cards/v1/** (`scrapers/bbva_tarjetas.py`): el endpoint `/cards/v1/cards/{pan}/transactions` devolvía HTTP 500 porque requiere tres headers extra que `/cliente/productos/` no necesita: `tsec` (JWT que BBVA devuelve en el *response header* de `GET /seguridad/cliente/obtenerTsec`), `timestamp-uid` (timestamp actual en hora Argentina) y `uid` (UUID v4 por request). Agrega `_fetch_tsec()` que captura el header tsec de la respuesta via fetch JS, y `_api_request_cards()` que inyecta los tres headers en la llamada a transactions.

## 0.5.121

- **Dedup cross-run para consumos BBVA tarjeta** (`scrapers_db.py`): agrega `"CONSUMO EN PESOS"` y `"CONSUMO EN DOLARES"` a `_GENERIC_DESCS`. El API de BBVA devuelve esa descripción genérica mientras la transacción está autorizada; unos días después aparece el nombre real del comercio. Con este cambio, cuando el scraper vuelve a correr y encuentra la descripción actualizada, el sistema la actualiza in-place en lugar de crear un duplicado — igual que con las descripciones temporales de cuentas BBVA.

## 0.5.120

- **Scraper BBVA tarjetas: endpoint correcto confirmado por HAR** (`scrapers/bbva_tarjetas.py`): reescritura completa basada en `bbvalogin6.har`. El token de cada tarjeta está en el campo `numeroPan` de la respuesta de `/cliente/productos/tarjetas`. Los consumos se obtienen con `GET /cards/v1/cards/{numeroPan}/transactions` (responde con array `data[]` con campos `localAmount.amount`, `concept`, `operationDate`). El saldo viene de `GET /cliente/productos/tarjetas/{id}/datosultimoproximoresumen` → `result.estadoActual.saldoPesos`. Se eliminan los ~11 candidatos de endpoint y el interceptor de fetch, reemplazados por el flujo exacto del HAR.

## 0.5.119

- **Scraper BBVA tarjetas: más candidatos de endpoint + GET con ID en path** (`scrapers/bbva_tarjetas.py`): los HARs disponibles no tienen la llamada de consumos de tarjeta (solo capturan login + cuentas). Se amplían los candidatos con variantes GET (`/tarjetas/{id}/consumos`, `/tarjetasCreditoVisa/{id}/consumos`) y variantes con el tipo en minúsculas. El interceptor de fetch/XHR (v0.5.118) mostrará el endpoint real si ningún candidato acierta.

## 0.5.118

- **Fix interceptor fetch BBVA tarjetas: log sin filtro + XHR** (`scrapers/bbva_tarjetas.py`): el interceptor descartaba calls sin `"servicios"` en la URL; ahora loguea todas sin filtro. Agrega interceptor de `XMLHttpRequest` además de `fetch` (Angular usa XHR en algunos builds).
- **UI: tilde verde en widget de vencimientos cuando el pago está confirmado** (`db.py`, `app.js`, `style.css`): `list_vencimientos` ahora incluye el campo `pago_confirmado` (subquery sobre `transfer_pairs`) que indica si existe un pago banco→tarjeta confirmado dentro de la ventana de 90 días antes del vencimiento. Cuando es verdadero, el widget muestra un badge circular verde con ✓ al lado del nombre de la tarjeta.

## 0.5.117

- **Fix scraper BBVA tarjetas: bug tipo_clave doble "Credito" + interceptor fetch** (`scrapers/bbva_tarjetas.py`): corregido el bug en el template de endpoint que generaba `tarjetasCreditoCreditoVisa` (ahora `tipo_clave` es `"Visa"`/`"Mastercard"` sin el prefijo extra). El interceptor de `window.fetch` ahora navega dentro del SPA con `window.location.hash` en lugar de `driver.get()`, que recargaba la página y perdía el monkey-patch; además loguea todas las calls a `/servicios/` para identificar el endpoint real de consumos.

## 0.5.116

- **Fix: categoría "Pago de Tarjeta" (con "de")** (`db.py`, `routes/gastos.py`, `app.js`): el código usaba `"Pago Tarjeta"` pero la categoría ya existente en la DB era `"Pago de Tarjeta"`. El mismatch hacía que `detect_card_payments` no excluyera entradas ya categorizadas y que "Ya emparejados" no las mostrara. Renombrado en los 4 lugares donde aparecía.

## 0.5.115

- **Fix "Ya emparejados" incluye pagos de tarjeta** (`db.py`, `app.js`): la sección inferior del workspace ahora muestra los pares de categoría "Pago Tarjeta" además de "Transferencia Intercuentas". La reconstrucción legacy ya no excluye fuentes CC del lado ingreso (necesario para pares banco→tarjeta). Los pares explícitos (en `transfer_pairs`) devuelven la `categoria` para distinguirlos visualmente: los pagos de tarjeta muestran badge 💳 y flecha → en lugar de ⇄.

## 0.5.114

- **UI: selector de tipo de cuenta en Config → Cuentas** (`app.js`, `db.py`, `routes/cuentas.py`): cada cuenta muestra un selector 🏦 Banco / 💳 Tarjeta en el header de la card. Persiste vía `PUT /api/cuentas/{fuente}` con campo `cuenta_tipo`. `update_cuenta` en db.py acepta el nuevo parámetro. Los valores por defecto (banco para bbva_cuenta/mp/iol, tarjeta para amex/bbva_mc/bbva_visa/galicia_mc) se setean automáticamente al crear la columna.

## 0.5.113

- **Workspace transferencias: matching de pagos de tarjeta** (`db.py`, `routes/gastos.py`, `index.html`, `app.js`, `style.css`): nueva columna `cuentas.cuenta_tipo` ('bank' / 'credit_card') que generaliza la clasificación de cuentas. `detect_transfers` ahora matchea solo `bank→bank` via JOIN con `cuentas`. Nueva función `detect_card_payments` (ventana ±1 día) matchea `bank→credit_card`. Nueva categoría especial "Pago Tarjeta" (excluida de totales). Workspace muestra nueva zona "Pagos de tarjeta detectados" (visual azul) con Parear/Ignorar por fila y "Agregar todas a cola". La cola de confirmación incluye ambos tipos; al confirmar llama a `mark-transfers` para transferencias y `mark-card-payments` para pagos (categoría diferente).

## 0.5.112

- **amex scraper: revierte filtro de ACREDITACION/5617** (`scrapers/amex.py`): se revierte el filtro introducido en v0.5.111. El usuario usa esas entradas (pagos al resumen y devoluciones RG 5617) para conciliar con los movimientos de sus cuentas bancarias; deben quedar en gastos.

## 0.5.110

- **BBVA: checkbox "Filtrar fechas en la API" en la UI del scraper** (`scraper_credentials.py`, `app.js`): el flag `filtro_fecha_api` ahora aparece como checkbox en la configuración de la instancia BBVA. Activado por default (comportamiento anterior). Al desactivarlo, el scraper envía fechas vacías y BBVA devuelve el saldo corriente real por movimiento. También se corrige el renderizado de checkbox con `default: true` en campos de scrapers — si el key no estaba en la config guardada, el checkbox ahora respeta el default del campo en lugar de aparecer siempre desmarcado.

## 0.5.109

- **BBVA: flag `filtro_fecha_api` para elegir entre filtrado server-side o client-side** (`scrapers/bbva.py`): `filtro_fecha_api: true` (default) mantiene el comportamiento actual — fechas en el payload de la API, BBVA filtra server-side pero devuelve `saldo=0` en cada movimiento. `filtro_fecha_api: false` — envía fechas vacías, BBVA devuelve el saldo real por movimiento (útil como discriminador de dedup), el filtrado por rango se hace client-side. El modo activo aparece en el log al iniciar el scraping.

## 0.5.108

- **Fix: `_rcnBuildModal` — faltaba `}` de cierre de función** (`app.js`): SyntaxError al cargar la app. La función no tenía su brace de cierre.

## 0.5.107

- **Fix: `_rcnBuildModal` — faltaba `}` de cierre de función** (`app.js`): SyntaxError al cargar la app. La función no tenía su brace de cierre.
- **Dedup mismo-día: check de unicidad de monto antes de fusionar genérico↔específico** (`scrapers_db.py`): los pasos 3 y 4 (specific→generic UPDATE y generic→skip) ahora verifican primero que el monto aparezca exactamente una vez en esa fecha. Si hay 2+ registros del mismo monto el mismo día (p.ej. dos retiros de cajero de $460.000), no se fusiona ninguno — se deja insertar el nuevo para evitar mezclar operaciones distintas. El mismo criterio de unicidad ya existía en el paso cross-date ±1 día; ahora es consistente en todos los niveles.

## 0.5.106

- **Dedup: "BANELCO Nro:..." y otros prefijos temporales cubren el match genérico/específico** (`scrapers_db.py`): se reemplaza el frozenset `_GENERIC_DESCS` (solo coincidencia exacta) por helpers `_is_generic(desc)`, `_generic_sql_cond()` y `_not_generic_sql_cond()` que incluyen también prefijos por startswith (`"BANELCO Nro:"`, `"DB TRF"`, `"TRANSF DEBITO"`). Así "BANELCO Nro:003164" se reconoce como genérico y cuando llega "OPERACION EN EFECTIVO TARJE 84296031 OP3164" (específico, mismo monto) se actualiza en lugar de insertar un duplicado.

## 0.5.105

- **Modal de reconciliación al subir PDF/XLS** (`routes/cuentas.py`, `routes/upload.py`, `routes/gastos.py`, `db.py`, `app.js`, `style.css`): al importar un archivo, se corre un dry-run de conciliación antes de insertar. Si hay algo que revisar (registros nuevos que el scraper no vio, matches de baja confianza, gastos scraper huérfanos en el período, o reimportaciones duplicadas), se muestra un modal comparativo. Cada registro del archivo se clasifica contra `movimientos_raw` usando el mismo algoritmo de `conciliacion.py` (`_score`). Los gastos scraper huérfanos se pueden marcar para borrar al confirmar. El modal se salta cuando todo matchea limpiamente (`skip_modal=true`). Funciona para todos los parsers; prioridad inicial MercadoPago y BBVA Cuenta.

## 0.5.104

- **Fix: Galicia cuotas — off-by-one en la fórmula de fecha** (`scrapers/galicia.py`): cuota 1 es la del mes original, cuota 2 es +1 mes, cuota N es +(N-1) meses. Corregido `+numero` → `+(numero-1)`.

## 0.5.103

- **Fix: Galicia cuotas — fecha = transaction_date + N meses** (`scrapers/galicia.py`): lógica más simple y correcta. Si la compra fue el 27/05 y es la cuota 2, la fecha es 27/07. Equivalente a `_installment_date` del parser PDF y coincide exactamente con lo que Galicia reporta en el resumen. 

## 0.5.102

- **Fix: Galicia cuotas — usar `submission_date` como fecha** (`scrapers/galicia.py`): para cuotas (`installment_plan > 0`), la fecha pasa a ser `submission_date` (cuando la cuota fue acreditada al período actual, ej. `2026-06-01`) en lugar de `transaction_date` (fecha original de la compra). Esto coincide con la fecha que aparece en el PDF de Galicia y mejora la conciliación scraper↔PDF en caso de subir el resumen de un período abierto.

## 0.5.101

- **Cross-date: cubre también movimientos con descripción específica y fecha cambiada (DEBIN, etc.)** (`scrapers_db.py`): se agrega el "Caso B" en el bloque cross-date ±1 día: cuando la descripción nueva es específica (no genérica) y ya existe un registro con la misma descripción pero fecha distinta dentro de la ventana y monto único, se actualiza solo la `fecha` al valor más reciente. Cubre el escenario "DEBITO DEBIN Nro:XXXXX" u otros movimientos donde BBVA mueve la fecha contable sin cambiar el concepto.

## 0.5.100

- **Fix regla de merge descripción/fecha: descripción del TRF INM COE, fecha más reciente** (`scrapers_db.py`): corrección de la lógica cross-date. En el match cross-date (±1 día, monto único): (1) cuando llega un "CR/DB TRF INM COE" y existe un genérico → UPDATE con la descripción específica + `MAX(fecha_nueva, fecha_existente)`; (2) cuando llega un genérico y existe el específico → solo UPDATE `fecha` si la nueva es más reciente, la descripción del específico se preserva intacta.

## 0.5.99

- **Al actualizar descripción genérica → específica, también actualiza la fecha** (`scrapers_db.py`): cuando un movimiento existente con descripción genérica ("Transferencia inmediata") se reemplaza por uno específico ("CR TRF INM COE Nro:..."), ahora se actualiza tanto `descripcion` como `fecha` con los valores del registro específico — que corresponde a la fecha de liquidación de BBVA, más confiable que la fecha de operación original.

## 0.5.98

- **Cross-date match: ventana reducida de ±3 días a ±1 día** (`scrapers_db.py`): ventana más conservadora para el match cross-date con unicidad de monto.

## 0.5.97

- **Cross-date match con unicidad de monto (ventana ±3 días)** (`scrapers_db.py`): cuando BBVA cambia la fecha contable de un movimiento entre runs, el match por fecha exacta falla. Se agrega una segunda pasada: si el monto aparece exactamente una vez en ±3 días (único → sin ambigüedad), se aplica la misma lógica de actualización/skip que el match mismo-día. Si hay 2+ registros con el mismo monto en la ventana no se actúa, evitando fusionar movimientos distintos que coinciden en importe.

## 0.5.96

- **Revert diferimiento TRF INM COE + actualización de descripción genérica → específica** (`scrapers/bbva.py`, `scrapers_db.py`): se elimina el diferimiento de 0.5.95. En su lugar, `insert_movimientos_raw` actualiza la descripción del registro existente cuando la nueva descripción es específica ("CR TRF INM COE Nro:...") y la existente es genérica ("Transferencia inmediata", "TRANSFERENCIA", etc.) para el mismo `(fuente, fecha, moneda, monto)`. Así el registro conserva la descripción detallada de BBVA sin crear duplicados.

## 0.5.95

- **BBVA: diferimiento de movimientos "TRF INM COE" hasta consolidación** (`scrapers/bbva.py`): los movimientos cuyo concepto empieza con `CR TRF INM COE` o `DB TRF INM COE` se omiten durante los primeros 2 días desde su fecha, ya que BBVA puede cambiar tanto la descripción como la fecha contable durante ese período. Con `dias >= 3` en la configuración del scraper, en la siguiente corrida ya estarán consolidados y se importarán con la descripción e fecha definitivas. En el log aparece `[defer] ... pendiente de consolidación BBVA`.

## 0.5.94

- **Fix: chips de Gastos muestran solo categorías raíz** (`app.js`): re-aplicado el filtro que excluye categorías hijas del chip row principal. Los hijos siguen apareciendo en el sub-chip row cuando se selecciona su padre.

## 0.5.93

- **Fix: Galicia cuotas — formato `NN/NN` igual al parser PDF** (`scrapers/galicia.py`): el scraper formateaba `2/6` pero el parser PDF produce `02/06`. Ahora usa zero-padding de 2 dígitos (3 para planes > 99), igualando el formato del PDF para que la conciliación scraper↔PDF no genere duplicados.

## 0.5.92

- **Config: Galicia `save_session = False`** (`scrapers/galicia.py`): no tiene sentido guardar la sesión cuando el scraper corre una sola vez por día. Simplifica el flujo: siempre hace login completo, igual que BBVA.

## 0.5.91

- **Fix: `check_session` con cookies de tarjetas** (`scrapers/galicia.py`): la sesión se guarda en el dominio `tarjetas.bancogalicia.com.ar`. `check_session` ahora navega directo a `/tarjetas/ini` en lugar de intentar ir a `/inicio` (que requeriría cookies del dominio principal que no tenemos). Esto permite reutilizar la sesión guardada en runs siguientes y evitar el re-login innecesario.
- **Fix: selector de click para movements** — `#__next a:not([href*='login'])` (confirmado funcional) queda primero en la lista.

## 0.5.90

- **Fix: Galicia movements — trigger via click en la SPA** (`scrapers/galicia.py`): la SPA solo llama `movements-tc` ante interacción del usuario, y el fetch directo falla por CORS. Ahora, si el interceptor no capturó movements en el page load, se intenta hacer click en el elemento de tarjeta de la SPA (usando ~15 selectores en orden de especificidad) para que ella misma dispare el call y el interceptor lo capture. Loguea todos los botones/links encontrados para ayudar a calibrar el selector correcto.

## 0.5.89

- **Fix: `driver` no definido en `_scrape_card`** (`scrapers/galicia.py`): al refactorizar el método se sacó `driver` de la firma pero se seguía usando en el fallback `_bff_request`. Corregido: `driver` vuelve a ser el primer parámetro y se pasa correctamente desde `scrape()`.

## 0.5.88

- **Fix: Galicia movements — fallback a BFF directo** (`scrapers/galicia.py`): la SPA solo llama `movements-tc` ante interacción del usuario, no en el page load. Si el interceptor no lo capturó, ahora se llama directamente al BFF con `_bff_request()` usando los datos de la tarjeta del overview (account_number, last_digits, fechas de período). La sesión está activa en ese punto (overview funcionó), por lo que el fetch directo debería tener el contexto correcto.

## 0.5.87

- **Fix: Galicia interceptor — no borrar datos capturados por do_login** (`scrapers/galicia.py`): `scrape()` ya no llama `_reset_bff_capture()` ni recarga la página al inicio; primero verifica si la SPA ya llamó al BFF durante la navegación SSO de `do_login()`. Solo re-navega (via dashboard → SSO) si no hay datos. Esto preserva la captura del load inicial que es cuando la SPA efectivamente llama al BFF.
- **Fix: interceptor XHR agregado** — el proxy ahora cubre también `XMLHttpRequest` (axios, jQuery) además de `fetch()`, por si la SPA de tarjetas usa una de esas librerías.
- **Fix: `check_session` navega via SSO** para garantizar contexto de autenticación correto al verificar la sesión.

## 0.5.86

- **Fix: Galicia BFF — interceptor de fetch via CDP** (`scrapers/galicia.py`): en lugar de inyectar nuestro propio `fetch()` (que falla por CORS preflight), se inyecta un proxy de `window.fetch` en cada página nueva mediante `Page.addScriptToEvaluateOnNewDocument`. Cuando la SPA de tarjetas hace sus propias llamadas al BFF (`overview/cards`, `movements-tc`) con las cookies y el contexto correcto, el proxy captura las respuestas en `window.__galiciaBff`. `scrape()` navega a `/tarjetas/ini`, espera que la SPA llame al BFF (hasta 20s) y lee los datos capturados. `check_session()` usa el mismo mecanismo. Elimina completamente los problemas de CORS.

## 0.5.85

- **Fix: Galicia BFF fetch — eliminar headers que rompen CORS preflight** (`scrapers/galicia.py`): se removieron `Cache-Control` y `Pragma` del fetch al BFF; algunos servidores no los listan en `Access-Control-Allow-Headers` y el preflight falla con "Failed to fetch". Solo se envía `id_channel: onlinebanking` como header custom.
- **Fix: Galicia scrape — navegar explícitamente a `/tarjetas/ini`** antes de llamar el BFF para garantizar el contexto correcto de la SPA; loguea la URL al inicio del scrape.
- **Debug: fetch error mejorado**: el catch ahora incluye `e.name`, `e.message`, `window.location.href` y la URL target para diagnóstico más claro.

## 0.5.84

- **Fix: Galicia login — send_keys primario para contraseña** (`scrapers/galicia.py`): el campo password de Galicia acepta teclado normal, así que `send_keys()` es ahora la estrategia principal; el teclado virtual queda solo como fallback si send_keys falla. El logging diagnóstico del teclado se mantiene pero ya no bloquea el flujo.

## 0.5.83

- **Debug: Galicia login — logging diagnóstico completo** (`scrapers/galicia.py`): `do_login` loguea cada paso con resultado (selector matcheado o no); `_dump_form_structure` enumera todos los `<input>` y `<button>` de la página de login; `_dump_keyboard_structure` lista contenedores, cantidad de `.hg-button` y sus valores `data-skbtn`; `_type_on_keyboard` loguea hits/misses por carácter; detección de TOTP ampliada con 9 selectores alternativos; mensaje de error final explica las causas del "seguimos en login".

## 0.5.82

- **Feature: Scraper Banco Galicia — implementación completa** (`scrapers/galicia.py`): reescritura desde cero sobre la base del stub anterior. Login vía Selenium en `onlinebanking.bancogalicia.com.ar/login` (formulario con DNI + alias + teclado virtual simple-keyboard); navega automáticamente a `tarjetas.bancogalicia.com.ar` vía SSO. Consumos y cuotas obtenidos con `fetch()` directo a los BFF endpoints (`bff-cards-overview-pota-cards`, `bff-cards-movements-tc-pota-cards`). Detecta cierre de período (`settlement_closing_dates.current`) y hace reset de `movimientos_raw` cuando comienza un nuevo resumen, mostrando solo el período vigente.
- **Config: campo DNI para Galicia** (`scraper_credentials.py`): se agrega `tercer_dato` (alias homebanking) y se renombra `usuario` a "Número de DNI" para alinear la UI con el formulario real de Galicia Online Banking.

## 0.5.81

- **Fix: budget chart chips — categorías hoja se muestran a sí mismas** (`app.js`): si `_budgetSelectedCat` no tiene hijos, el chart filtra a esa única categoría en lugar de mostrar todas. Antes caía al fallback y mostraba todo.
- **Fix: donut drill-down sin gris al volver** (`app.js`): el drill-down usa `_donutDrillCat` (estado separado, sin llamada API) en lugar de `setCrossFilter`. Clic en padre → drill-down visual client-side con datos cacheados en `_donutData`; clic en hoja → cross-filter normal. Volver con × limpia `_donutDrillCat` y restaura el donut sin recargar todo.

## 0.5.80

- **Fix: chips de Gastos — todas las categorías visibles** (`app.js`): revertido el filtro que ocultaba categorías hijas del chip row principal; todas las categorías vuelven a aparecer. Los sub-chips del segundo renglón siguen funcionando igual.
- **Feature: renombrar desde tab Categorías** (`app.js`, `db.py`): doble clic sobre el nombre de una categoría en Config → Categorías abre un input inline para renombrarla. Actualiza tanto la tabla `categorias` como `gastos.categoria` y los chips de gastos en un solo paso.

## 0.5.79

- **Fix: sub-chips se pueden seleccionar** (`app.js`): `_renderSubChips` ahora mantiene el renglón visible cuando el seleccionado es un hijo (antes desaparecía porque el hijo no tiene hijos propios). `_syncChipUI` marca el chip padre como activo cuando un hijo suyo está seleccionado.
- **UX: budget chart chips drill-down** (`app.js`): tap chip de presupuesto = mostrar las barras de sus subcategorías; tap mismo chip = volver a todas. Reemplaza el modelo de hide/show por `_budgetSelectedCat`.
- **UX: sub-chips borde celeste claro** (`app.js`, `index.html`): sub-chips con `border-color:#7dd3fc`; sin barra negra izquierda en el contenedor.

## 0.5.78

- **Fix: chips de Gastos muestran solo categorías raíz** (`app.js`): se filtran los hijos del árbol del renglón principal; aparecen solo en el sub-chip row cuando se selecciona el padre.
- **Fix: donut drill-down — botón × sube al padre** (`app.js`): `clearCrossFilter` ahora navega un nivel arriba si el filtro actual tiene categoría padre, en lugar de limpiar todo. Segundo × limpia completamente.
- **UX: chips de presupuesto — exclusive select** (`app.js`): tap chip = mostrar solo esa categoría en el chart de presupuesto; tap el único visible = mostrar todas. Igual que los chips de Gastos.

## 0.5.77

- **Fix: SyntaxError _expandedCats declarada dos veces** (`app.js`): renombrada la función de expansión de categorías a `_catFilterParam()` para evitar conflicto con el `let _expandedCats` del category manager.

## 0.5.76

- **UX: chips de categoría — nuevo comportamiento** (`app.js`): tap chip activo con múltiples seleccionados = colapsar a solo ese (1 tap para cambiar de vista). Tap chip activo cuando es el último = volver a Todas. Tap chip inactivo = ADD (multi-select continúa igual).
- **UX: sub-chips de subcategorías en Gastos** (`app.js`, `index.html`): al seleccionar un padre aparece un segundo renglón con sus hijos. Tap sub-chip = filtrar exclusivamente a esa subcategoría. El query de gastos expande descendientes automáticamente (seleccionar "Comida" incluye Supermercado, Delivery, etc.).
- **UX: drill-down en donut de categorías** (`app.js`): si el cross-filter apunta a una categoría con hijos, el donut muestra solo esos hijos en lugar de todos.
- **Backend: `GET /api/categorias/hierarchy`** (`routes/categorias_route.py`): mapa `{parent:[child,...]}` cargado al startup.

## 0.5.75

- **Fix: BBVA importaba duplicados cuando el concepto cambiaba entre runs** (`scrapers_db.py`): BBVA a veces devuelve un concepto genérico ("TRANSFERENCIA") en un run y uno específico ("TRANSF CREDITO Nro:709675") en otro para el mismo movimiento. Como el fallback de dedup usaba `(fuente, fecha, moneda, monto, descripcion)` exacto, ambos pasaban y se creaban duplicados. Fix: se agrega un set `_GENERIC_DESCS` con descripciones temporales/genéricas conocidas; cuando la descripción nueva es genérica y ya existe cualquier registro con mismo `(fuente, fecha, moneda, monto)`, se descarta el nuevo en lugar de insertar un duplicado.

## 0.5.74

- **UX: colores de categoría padre/hijo configurables** (`app.js`, `index.html`): nuevas variables CSS `--color-cat-parent` y `--color-cat-child` aplicadas en el árbol de Categorías y en la tabla de Presupuesto. Defaults: padre `#111827` (casi negro), hijo `#4b5563` (gris oscuro legible). Ambos colores se pueden cambiar desde Config → Interfaz → sección "Categorías".

## 0.5.73

- **Fix: BBVA descartaba ingresos como duplicados cuando saldo=0** (`scrapers/bbva.py`): la dedup usaba `(fecha, abs_importe, saldo)` como clave; cuando BBVA devuelve `saldo=0,00` en todos los movimientos, un egreso y un ingreso del mismo monto el mismo día colisionan (ej. DEBITO DEBIN $2.298.000 y CR TRF INM COE $2.298.000). Corrección: solo se activa la dedup cuando `saldo_val != 0.0` — es decir, cuando BBVA expone un saldo corriente real que sirva como fingerprint único.

## 0.5.72

- **Fix: reaplicar reglas crasheaba con 500** (`categorizer.py`): reglas con `patron: null` en el YAML asignaban `pattern = None`, y `re.search(None, ...)` lanzaba `TypeError` que no era capturado por `except re.error`. Fix: `regla.get("patron")` en lugar de `"patron" in regla` (skipea null/vacío), y se agrega `TypeError` al except.

## 0.5.71

- **UX: presupuesto padre hereda suma de hijos** (`db.py`): si una categoría padre no tiene presupuesto explícito definido, `stats_presupuesto_vs_actual` calcula automáticamente su presupuesto como la suma de los presupuestos de sus categorías hijas. La barra de progreso y el porcentaje se calculan contra ese valor derivado.

## 0.5.70

- **Feature: editor de keywords inline en tab Categorías** (`app.js`, `index.html`): cada categoría tiene un botón `+` que expande su sección de keywords directamente en la tabla. Las palabras clave se muestran como chips, con detección de duplicados en rojo (igual que la tab Reglas). Enter en el input agrega la keyword y guarda. Botón "Ver keywords" expande/colapsa todas a la vez.
- **Botones globales en Categorías**: Reaplicar, ⬇ Exportar, ⬆ Importar (mueven la funcionalidad de la tab Reglas).
- **Elimina tab Reglas** (`index.html`, `app.js`): la tab "Reglas de categorización" y "Reglas de emparejado" se eliminan de la UI. La lógica de backend (`/api/rules`, `/api/rules/apply`, etc.) se mantiene intacta.
- **Tab Categorías es ahora la tab activa por defecto** en Config.

## 0.5.69

- **Fix: categorías nuevas aparecen en gastos y reglas** (`db.py`): `list_categorias()` ahora une `DISTINCT categoria FROM gastos` con `nombre FROM categorias`, así las categorías virtuales (sin gastos asignados aún) aparecen en el datalist de la tabla de gastos y en el campo categoría del editor de reglas.
- **UX: reglas sugieren categorías existentes** (`app.js`): el input `categoria` en el editor de reglas usa `list="cat-datalist"` para guiar hacia categorías gestionadas, evitando nombres nuevos por typo.
- **UX: botón ↺ en tab Categorías** (`index.html`, `app.js`): recarga la lista desde el servidor sin necesidad de navegar a otra tab.

## 0.5.68

- **Feature: jerarquía de categorías** (`db.py`, `routes/categorias_route.py`, `app.js`, `index.html`): nueva tabla `categorias` con campo `parent` auto-referenciado que permite definir categorías padre/hijo. Migration `categorias_seed_v1` siembra la tabla desde `rules.yaml` en el primer arranque. Nueva sub-tab "Categorías" en Config para asignar padres y gestionar el flag `especial` desde la UI. El presupuesto mensual muestra las categorías hijo indentadas bajo su padre (con rollup del gastado); el total excluye filas hijas para evitar doble-conteo. El budget chart filtra a categorías de nivel raíz. `GET/PUT /api/categorias/managed` son los endpoints de CRUD.

## 0.5.67

- **Mejora: settlement report incluye EXTERNAL_REFERENCE automáticamente** (`mercadopago.py`): al inicio de cada fetch del settlement report, se consulta la config de columnas en la API de MP y si `EXTERNAL_REFERENCE` no está, se agrega con un PUT (idempotente — después del primer run no hace nada). Permite cruzar las transferencias del reporte con la referencia externa del pago original.

## 0.5.66

- **Fix: settlement report se regenera en cada ejecución** (`mercadopago.py`): el código anterior usaba el reporte existente como primera opción y solo generaba uno nuevo si no había ninguno, lo que resultaba en reutilizar indefinidamente el reporte más viejo (ej. del 29-05) y no capturar transferencias CBU/CVU posteriores. Ahora siempre se descarga el reporte disponible (paso 1) y además se dispara la generación de uno nuevo sin esperar (paso 2), de modo que la próxima ejecución siempre tiene un reporte actualizado — diseño "generar hoy, usar mañana".

## 0.5.65

- **Fix: acciones discretas en reglas ahora guardan inmediato** (`app.js`): el mismo problema de debounce de 0.5.64 afectaba a todas las acciones no-textuales: agregar keyword (Enter), eliminar keyword, eliminar regla, drag-and-drop, checkbox "Solo egresos" (que además no tenía listener propio y dependía solo del focusout). Ahora todas estas acciones llaman `_doSaveRules()` directamente. El debounce de 800ms queda solo para los campos de texto (nombre de categoría) donde sí tiene sentido.

## 0.5.64

- **Fix: checkbox "Especial" no guardaba si se hacía Ctrl+R antes de 800ms** (`app.js`): la lógica de guardado estaba completamente debounceada (800ms). Al tildar "Especial", si el usuario refrescaba antes de que el timer disparara, el cambio se perdía aunque hubiera visto un toast de "reglas guardadas" de un save previo. Fix: se extrae `_doSaveRules()` como función directa; los checkboxes "Especial" cancelan el debounce pendiente y guardan de inmediato, sin esperar los 800ms. Los inputs de texto siguen usando el debounce normal.

## 0.5.63

- **UX: botón "Nueva regla" hace scroll y foco automático** (`app.js`): al agregar una regla nueva, la card ahora se centra en pantalla (`block: "center"` en lugar de `"nearest"`) y el campo de categoría recibe el foco de inmediato, evitando tener que hacer scroll manual.

## 0.5.62

- **Fix: regla nueva marcada como "especial" desaparecía al guardar** (`app.js`): el filtro previo al save exigía `palabras.length > 0`, descartando silenciosamente cualquier regla sin palabras clave aunque tuviera categoría y `especial=true`. Ahora se permite guardar reglas con `especial=true` y categoría aunque no tengan palabras clave, ya que su función es marcar esa categoría como excluida de gráficos/totales.

## 0.5.61

- **Fix: movimientos_raw huérfanos bloqueaban re-importación del scraper** (`db.py`): `delete_all_gastos()` borraba registros de la tabla `gastos` (al re-subir un PDF o borrar una importación) sin actualizar `movimientos_raw`. Los registros quedaban con `estado='imported'/'matched'` apuntando a `gasto_id` inexistentes, impidiendo que el scraper los volviera a insertar (bloqueados por dedup) y que `auto_import_unmatched` los procesara (no estaban en `'unmatched'`). Fix: al borrar gastos, `delete_all_gastos()` ahora resetea a `'unmatched'` todos los movimientos_raw con referencias huérfanas. Se agrega migración `fix_orphaned_movimientos_raw_v1` que corrige el estado actual de las DBs afectadas.

## 0.5.60

- **Fix: tooltip de categoría mostraba fuente desactualizada** (`app.js`): al editar la categoría de un gasto manualmente, el tooltip del input (que dice "Fuente: regla" / "Fuente: manual") no se actualizaba porque la tabla de gastos no se recarga tras el PATCH. Ahora se actualiza el `title` del input directamente en el DOM al guardar con éxito, reflejando inmediatamente "Fuente: manual" (o vacío si se limpió la categoría). El valor en DB siempre fue correcto; solo era un bug visual de stale data.

## 0.5.59

- **gastos: edición inline de descripción** (`db.py`, `routes/gastos.py`, `routes/cuotas.py`, `static/app.js`, `static/style.css`): se agrega la posibilidad de editar el texto descriptivo de cualquier gasto sin perder el original. Se guarda en el nuevo campo `descripcion_editada` (NULL = sin cambios). El motor de cuotas (`cuotas.py`) usa el texto editado si existe para detectar patrones de cuota (uso principal: gastos importados sin formato `NN/NN` que igual se van a ver en cuotas). La conciliación contra el scraper sigue usando el texto original para evitar falsos no-matches. UI: click en la descripción abre un input inline; confirmar con ✓ o Enter, cancelar con ✕ o Escape; vaciar y confirmar restaura el original. Los gastos con descripción editada se muestran en itálica con ícono ✏ y tooltip con el texto original.

## 0.5.58

- **motor de reglas: keywords con caracteres especiales no matcheaban** (`categorizer.py`, `db.py`): el patrón usaba `\b` (word boundary), que falla cuando el keyword empieza o termina con un carácter no-alfanumérico (`%`, `=`, `*`, `.`, etc.). Por ejemplo `\bIVA 21%\b` nunca matcheaba porque el `\b` final requiere un alfanumérico después de `%`. Se reemplaza `\b` por lookarounds `(?<!\w)` / `(?!\w)` que funcionan con cualquier carácter y mantienen la protección contra partial matches (ej. "coto" en "PSICOTOLOGO"). Afecta `categorize_by_rules`, `apply_match_rules`, `preview_user_rule_matches` y `preview_rule_matches`.

## 0.5.57

- **categorizer: reglas "Solo egresos" se saltean al importar PDF** (`categorizer.py`, `routes/upload.py`): `categorize()` recibía siempre `monto=0.0` por defecto, lo que hacía que el filtro `solo_egresos` skipeara esas reglas en cada importación de PDF (el `monto <= 0` era siempre True). Se agrega `monto` y `fuente` como parámetros a `categorize()`, y `upload.py` calcula el monto efectivo (normalizado al convenio `>0=egreso`) antes de categorizar, igual a como lo hace `apply_rules_to_all()`.
- **UX: toast informativo cuando el keyword ya está registrado** (`app.js`): al guardar una categoría a mano, si el keyword ya existe en la regla correcta el sistema ahora muestra un toast "keyword ya registrado en X" en vez de hacer silencio, explicando por qué no apareció el prompt de aprendizaje.

## 0.5.56

- **cuotas.py: excluye fechas de servicio tipo "MM/26"** (`routes/cuotas.py`): descripciones como `PERSFLOW49010001 03/26` (servicio mensual Galicia donde el denominador es el año 2026) dejaban de ser detectadas como cuota 3 de 26. La regla es: para fracciones standalone (`_FRAC_CAP`), solo se acepta `2 ≤ total ≤ 24`; cualquier total ≥ 25 es interpretado como año (`25`=2025, `26`=2026, …) y se descarta. Los planes reales de cuotas en tarjetas argentinas son de 2–24 meses. El umbral mantiene planes de 24 cuotas que sí existen.

## 0.5.55

- **AMEX parser: captura "Cuota NN de NN" de líneas de continuación** (`parsers/amex.py`): AMEX imprime el indicador de cuota en una línea ~8pt debajo de la línea de la transacción (e.g. "Cuota 02 de 02" o "Plan de Cuotas . Cuota 01 de 03"). El parser ahora inspecciona hasta 3 filas de continuación buscando ese patrón y lo normaliza a "CUOTA NN/NN" al final de la descripción. Cubre cuota anual (2 cuotas) y compras en cuotas ("Plan de Cuotas"). Las descripciones resultantes son detectables por el tab Cuotas.
- **cuotas.py: excluye rangos de fechas de la detección de cuotas** (`routes/cuotas.py`): patrones del tipo "04/26 - 03/27" (período de vigencia de la cuota anual AMEX) ya no son detectados falsamente como "cuota 4 de 26". El `_DATE_RANGE_RE` los elimina antes de aplicar `_FRAC_CAP`.

## 0.5.54

- **BBVA parser: preserva indicador de cuotas en descripción** (`parsers/bbva.py`): en lugar de borrar el sufijo `C.03/12` al importar el PDF, ahora lo normaliza al formato `03/12` al final de la descripción (consistente con Galicia). Esto hace que las cuotas BBVA aparezcan en el nuevo tab Cuotas. El cambio mejora además la conciliación: el tie-breaker `_CUOTA_RE` de `conciliacion.py` ahora puede distinguir cuota 3/12 de cuota 7/12 del mismo comercio y evitar falsos matches. Los PDFs ya importados necesitan re-importarse para ver las cuotas BBVA en el tab.

## 0.5.53

- **Tab Cuotas** (`routes/cuotas.py`, `index.html`, `app.js`, `style.css`): nuevo tab a la derecha de Gastos que calcula cuotas pendientes en cuotas detectadas en las descripciones. Detecta formato AMEX (`CUOTA 01/12 DESCRIPCION`) y Galicia (`DESCRIPCION 03/12`). Agrupa por compra tomando la cuota más alta vista en el historial, proyecta los pagos restantes mes a mes y muestra: tarjetas de resumen (próximo mes + total adeudado separados por ARS/USD), tabla por mes con totales por tarjeta, y tabla de detalle por compra con cuota actual/total, monto por cuota, cuotas restantes y total adeudado. Los mismos filtros de Gastos (fuente, persona, moneda, sin especiales). Filas de meses pasados se muestran en gris (implica cuotas no importadas aún).

## 0.5.52

- **BBVA scraper: CBU destino para transferencias inmediatas salientes** (`scrapers/bbva.py`): se agrega `_fetch_detalleinmediata` que llama a `POST /banelco/transferencias/detalleinmediataemitida` para movimientos con `codigoAccion=06`. Requería guardar el string original del `importe` en `raw_data["importe_raw"]` (también agregado). El log muestra `[detalleinmediata] cbuDestino='...'` y el CBU se persiste en `raw_data["cbu_destino"]`.

## 0.5.51

- **BBVA scraper: endpoint de detalle de servicios** (`scrapers/bbva.py`): reemplaza la implementación incorrecta de 0.5.50. Análisis de HAR confirmó que el endpoint real para pagos de servicios es `POST /banelco/detalleservicio` (no `/movimientodetalle`), con parámetros `fecha/claveConcepto/codigoTipoMovimiento/procedencia`. El trigger correcto es `procedencia ~ "OP\d+"` (codigoAccion=02 "OPERACION EN EFECTIVO TARJE" y codigoAccion=03 "PAGO DE SERVICIOS TARJETA"). La respuesta incluye el campo `servicio` con el nombre del servicio pagado (ej. "SJOSE P DIOS"), que se incorpora a la descripción del movimiento y se guarda en `raw_data["servicio"]`. También se guardan `cajero_entidad` y `hora_operacion`.

## 0.5.50

- **BBVA scraper: endpoint de detalle de movimiento** (`scrapers/bbva.py`): se agregan `_fetch_detalle`, `_extract_nombre_detalle` y `_enrich_with_detalle`. Para cada movimiento que tenga `codigoAccionDetalleMovimientoCuenta` y `numeroOperacion`, se llama a `POST /cliente/productos/cuentas/movimientodetalle` y se loguea la respuesta completa `[detalle]`. Si se detecta un nombre de contraparte (destinatario/remitente), se agrega a `raw_data["destinatario"]` y se incorpora a la descripción ("concepto — Nombre"). El endpoint y los campos de respuesta se validan en esta primera corrida.

## 0.5.49

- **Fix: "Último intento" mostraba siempre la misma fecha que "Último OK"** (`scraper_scheduler.py`): en los 4 paths de error (excepción + `result.error`, tanto en run manual como en job programado), `update_instance_status` no actualizaba `ultimo_run`. Al fallar un run, la UI mostraba el timestamp del último run exitoso en ambos campos. Corrección: todos los paths de error ahora pasan `ultimo_run=now_iso`.
- **Fix: año de 2 dígitos en timestamps de scrapers** (`static/app.js`): `_fmtTs()` usaba `dateStyle:"short"` que en `es-AR` genera año de 2 dígitos ("31/5/26"). Cambiado a opciones explícitas con `year:"numeric"` → "31/5/2026, 8:34 p. m.".

## 0.5.48

- **Fix: BBVA sigue viendo "Sesión guardada en disco: sí" tras 0.5.47** (`scrapers/base.py`): `clear_session()` se llamaba solo al *terminar* el run, pero el archivo stale del deploy anterior ya se había restaurado al *iniciar*. Corrección: cuando `save_session=False`, se borra el archivo de sesión al inicio de `_run_sync`, antes de intentar cualquier restore — garantizando que BBVA siempre arranque con login limpio.

## 0.5.47

- **BBVA scraper: no guardar sesión al terminar el run** (`scrapers/base.py`, `scrapers/bbva.py`): se agrega `save_session: bool = True` a `BaseScraper`; cuando es `False`, al terminar el run se borra cualquier sesión en disco en lugar de guardar las cookies nuevas. `BbvaScraper` lo setea en `False` y elimina el `session_ttl_seconds` que ya no tiene sentido: con sesiones de 5 min y runs cada 30+ min las cookies siempre estaban vencidas y solo generaban redirects a `/desconexion.html`.

## 0.5.46

- **Fix: transferencia a Reserva MP aparecía como ingreso en lugar de egreso** (`scrapers/mercadopago.py`): `partition_transfer` (mover dinero a la Reserva de MP) aparece en ambas queries de la API (payer=user, collector=user). El código lo deferiba en la query de payer y lo capturaba en la de collector con `sign=-1` (ingreso). Corrección: se difiere en la collector query y se captura en la payer (sign=+1, egreso), generando correctamente "Transferencia hacia Reserva" con monto positivo.

## 0.5.45

- **BBVA scraper: captura campos extra del endpoint de movimientos** (`scrapers/bbva.py`): se agregan a `raw_data` los campos `denominacionCuenta`, `numeroCuenta`, `claveOperacion`, `codigoSucursal`, `origen`, `procedencia`, `numeroCheque` y `codigoAccionDetalleMovimientoCuenta`, que ya venían en la respuesta API pero no se guardaban. En el log se emite una línea `[extra]` por movimiento mostrando los campos no vacíos, para evaluar qué datos trae cada tipo de operación y decidir si incorporarlos a la descripción.

## 0.5.44

- **Tabla transfer_pairs: vínculo explícito entre los dos lados de cada par** (`db.py`, `routes/gastos.py`): `mark_transfers` ahora escribe en la nueva tabla `transfer_pairs(id_out, id_in)` además de setear la categoría. `get_existing_transfer_pairs` lee primero de esa tabla (exacto, sin límite de fechas) y solo usa reconstrucción por monto+fecha para los pares legacy confirmados antes de esta versión. `unmark_transfers` también borra la fila de `transfer_pairs`. Esto elimina el workaround de la ventana de 60 días y los pares con cualquier diferencia de fechas se muestran siempre juntos.

## 0.5.43

- **Fix workspace transferencias: pares con más de 3 días de diferencia aparecen como "sueltos"** (`routes/gastos.py`): la reconstrucción de pares ya confirmados usaba la misma ventana de 3 días que la detección automática. Como el usuario ya confirmó esos pares, la reconstrucción para display ahora usa 60 días — así pares entre BBVA y MP con 4, 5 o más días de diferencia aparecen juntos en el mismo renglón de "Ya emparejados". La ventana de detección de nuevas sugerencias sigue siendo 3 días.

## 0.5.42

- **Workspace transferencias: Ignorar persiste en DB** (`db.py`, `routes/gastos.py`, `index.html`, `app.js`): el botón "Ignorar" en sugerencias automáticas ahora guarda el par en la tabla `transfer_ignores` — persiste entre recargas y el par no vuelve a aparecer en sugerencias. Nueva sección colapsable "Sugerencias ignoradas" al pie del workspace con botón "Restaurar" para reactivar cualquier par ignorado. `detect_transfers` excluye automáticamente los pares en `transfer_ignores`.

## 0.5.41

- **Fix dedup BBVA: priorizar descripción estable sobre la temporal** (`db.py`, `scrapers/bbva.py`): "DB TRF INM COE Nro:…" y "TRANSF DEBITO Nro:…" son descripciones que BBVA asigna transitoriamente y reemplaza después por "Transferencia inmediata" / "TRANSFERENCIA". La migración `dedup_bbva_same_saldo_v1` y el dedup in-batch del scraper ahora penalizan las descripciones con "Nro:" o prefijo "DB TRF"/"TRANSF DEBITO", conservando la descripción estable. Si en el mismo batch el duplicado tiene la descripción estable y el ya-almacenado es temporal, el scraper actualiza la descripción on the fly (log `[dup→stable]`).

## 0.5.40

- **Fix: BBVA importa la misma transferencia con dos descripciones distintas** (`scrapers/bbva.py`, `db.py`): la API de BBVA devuelve el mismo movimiento con dos valores de `concepto` diferentes (p.ej. "Transferencia inmediata" + "DB TRF INM COE Nro:XXXXXX"). El scraper ahora deduplica dentro del mismo batch usando `(fecha, abs_importe, saldo_resultante)` como clave — mismo saldo post-transacción = mismo movimiento real. Además, se agrega la migración `dedup_bbva_same_saldo_v1` que limpia los duplicados ya existentes en la DB: para cada grupo `(fuente, fecha, monto, moneda)` con más de una entrada, conserva la descripción más específica (tiene número de referencia) o la categorizada por el usuario, y borra las demás preservando la categoría en la entrada que queda.

## 0.5.39

- **Workspace transferencias: sección "Sugerencias automáticas" con Parear/Ignorar** (`index.html`, `app.js`, `style.css`): las sugerencias auto-detectadas ahora se muestran como lista de pares antes de las columnas, con botón "Parear" (agrega a cola) e "Ignorar" (descarta la sugerencia de la sesión) por fila. El botón "Auto-sugerir" de la toolbar y el botón "Agregar todas a cola" de la sección hacen lo mismo. Las columnas de candidatos ya no muestran ítems en amarillo si la sugerencia fue ignorada.
- **Fix detect_transfers: evitar que el mismo ID aparezca en dos pares** (`db.py`): el dedup ahora también excluye `id_out` e `id_in` ya usados en pares anteriores del mismo resultado, eliminando la causa de "sueltos duplicados" cuando BBVA tiene dos entradas con el mismo monto el mismo día.

## 0.5.38

- **Workspace transferencias: columnas con headers y sort** (`index.html`, `app.js`, `style.css`): las columnas de egresos e ingresos ahora tienen una barra de encabezados con Fecha / Fuente / Descripción / Monto. Click en cualquier encabezado ordena ambas columnas (click repetido invierte dirección). Orden por defecto: monto descendente (mayor primero).

## 0.5.37

- **Fix workspace transferencias: «Deshacer» activa «Mostrar todos» si el movimiento desmarcado no tiene match automático** (`app.js`): cuando se desmarca una transferencia «suelta» (sin contrapartida en sugerencias), el movimiento quedaba invisible porque el filtro por defecto solo muestra candidatos con match. Ahora `twUnmark` detecta ese caso y activa el checkbox «Mostrar todos» automáticamente con un toast informativo.

## 0.5.36

- **Workspace transferencias: filtro por candidatos con match** (`app.js`, `index.html`): por defecto las columnas muestran solo los movimientos que tienen al menos un par detectado automáticamente, no todos los movimientos de cuentas. Checkbox "Mostrar todos" para ver el universo completo cuando sea necesario parear manualmente algo que no fue auto-detectado. Los ítems ya en la cola de confirmación siempre permanecen visibles.

## 0.5.35

- **Workspace de transferencias inter-cuentas** (`static/index.html`, `app.js`, `db.py`, `routes/gastos.py`): reemplaza el modal de detección automática por un sub-tab "Transferencias" dentro de Gastos con interacción individual. Dos columnas (egresos / ingresos) con items clickeables para armar pares manualmente; botón "Auto-sugerir" pre-llena la cola con los pares detectados automáticamente; cola de confirmación con botón ✕ por par; sección colapsable "Ya emparejados" con botón "Deshacer" por par; "Marcar solo este" para transferencias sin contrapartida importada. La detección automática ya no está hardcodeada a bbva_cuenta↔mercadopago — ahora soporta cualquier par de cuentas no-tarjeta (bbva_cuenta, mercadopago, invertironline, etc.). Nuevos endpoints: `GET /api/gastos/transfer-workspace` y `POST /api/gastos/unmark-transfers`.

## 0.5.34

- **Fix: "Último intento" y "Último OK" mostraban hora UTC en lugar de hora local**: los timestamps se guardaban como UTC (`datetime.utcnow()`) y se mostraban con un simple `.replace('T',' ').slice(0,16)` sin conversión de zona horaria. Ahora se usa `new Date(iso + 'Z').toLocaleString('es-AR')` igual que ya se hacía con `scraped_at` y el próximo run, mostrando siempre la hora de Argentina.
- **Scraper BBVA tarjetas: discovery de endpoint consumos** (`scrapers/bbva_tarjetas.py`): prueba múltiples candidatos de endpoint en orden (`tarjetasCreditoVisa/consumos`, `tarjetasCreditoMastercard/consumos`, etc.) hasta encontrar el que devuelva HTTP 200. Si ninguno funciona, activa un interceptor de `window.fetch` que loguea todas las llamadas que hace el SPA al navegar a la página de consumos, mostrando el endpoint real en el log.

## 0.5.33

- **Parser Galicia MC: intereses de financiación y punitorios** (`parsers/galicia.py`): cuando no se paga el saldo completo, los intereses aparecen solo en el resumen CONSOLIDADO (sin fila con fecha en DETALLE). Se agregan dos nuevos patrones regex (`_INTERES_FINANC_RE`, `_INTERES_PUNITOR_RE`) y la función `_extract_intereses()` que los extrae del texto de las primeras páginas. Si están presentes, se registran como egresos individuales en la fecha de cierre del resumen, igual que la comisión. El saldo pendiente no se agrega porque ya figura en los gastos del mes anterior.

## 0.5.32

- **Fix scraper BBVA tarjetas: endpoint consumos** (`scrapers/bbva_tarjetas.py`): el endpoint correcto es `/cliente/productos/tarjetas/consumos` (no `/movimientos`). También se ignoran explícitamente las `tarjetasDebito` para no generar ruido en el log.

## 0.5.31

- **Fix scraper BBVA tarjetas: detección de tarjetas** (`scrapers/bbva_tarjetas.py`): la API devuelve las tarjetas bajo claves `tarjetasCreditoVisa` y `tarjetasCreditoMastercard` (no `tarjetas`). `_extract_tarjetas` ahora itera sobre todas las claves del `result` e infiere el tipo (VISA/MC) del nombre de la clave; como fallback busca en los campos `alias`/`tipoProducto.descripcion` del item.

## 0.5.30

- **Scraper BBVA Tarjetas — reescritura con API via fetch()** (`scrapers/bbva_tarjetas.py`): abandona el enfoque DOM/shadow-DOM y adopta exactamente la misma estrategia que el scraper de cuentas: hereda `BbvaScraper` (login, sesión, `_api_request`) y solo overridea `scrape()` para llamar `GET /cliente/productos/tarjetas` y `POST /cliente/productos/tarjetas/movimientos`. Detecta Visa/MC por el texto del campo `marca`/`descripcion`/`alias` de la API. El primer run loguea la estructura completa del JSON para calibrar nombres de campos y endpoints si BBVA los cambia.

## 0.5.29

- **Scraper BBVA Tarjetas — shadow DOM traversal** (`scrapers/bbva_tarjetas.py`): reescritura completa de la detección de tarjetas y extracción de movimientos para atravesar el shadow DOM de los Lit web components de BBVA. Tres estrategias en cascada: (A) links con texto Visa/MC en shadow DOM via JS, (B) deep text scan + click-y-observar-URL si hay texto pero no links, (C) dump diagnóstico amplio para calibración manual. Los movimientos se extraen con `_JS_EXTRACT_MOVEMENTS` que recorre shadow roots buscando web components con atributos `date`/`concept`/`amount` y lista items con fecha+descripción+monto en el texto. El dump de diagnóstico ahora incluye hasta 8000 chars del shadow DOM del MFE de tarjetas.

## 0.5.28

- **Nuevo scraper BBVA Tarjetas de Crédito** (`scrapers/bbva_tarjetas.py`): scraper Selenium que navega el homebanking BBVA Argentina y extrae los movimientos del período en curso de las tarjetas Visa y Mastercard directamente desde el DOM (sin API). Registrado como `"bbva_tarjetas"` en el scheduler y con su propia entrada en Scrapers con los mismos campos de credenciales que BBVA Cuentas. Emite movimientos con `fuente="bbva_visa"` y `fuente="bbva_mc"`, compatibles con los PDFs existentes. El mapeo tarjeta→fuente se puede overridear vía `product_key` en la tab Cuentas (VISA o MC). Incluye múltiples estrategias de extracción del DOM (web components, listas, tablas, divs) con log de diagnóstico para calibrar selectores tras el primer run.

## 0.5.27

- **Auto-learn inteligente: detecta si el keyword ya existe en otra categoría** (`app.js`): al categorizar un gasto a mano, en lugar de ofrecer siempre "¿Agregar?", ahora el flujo es:
  - Si alguna palabra del keyword sugerido ya está en la misma categoría destino → no pregunta nada (regla ya cubre el caso).
  - Si está en una categoría distinta → muestra "¿Mover 'X' de '[CategoriaOrigen]' a '[CategoriaDestino]'?" con Confirmar/Cancelar. Al confirmar, elimina la palabra de la regla origen y la agrega a la destino, guardando en un solo PUT.
  - Si no está en ninguna regla → comportamiento anterior: prompt editable para agregar.
  - Las reglas se cargan lazy si el tab Config no fue abierto aún.

## 0.5.26

- **Filtro ingreso/egreso en solapa Gastos** (`index.html`, `app.js`): nuevo selector "Todos / Egreso / Ingreso" en la barra de filtros. Se aplica client-side sobre los datos ya cargados (sin re-fetch). Default: Todos.

## 0.5.25

- **Reglas de persona: misma lógica que reglas de categorización** — todas las mejoras de v0.5.24 aplicadas a la sección "Reglas de asignación de persona":
  - **Word boundary fix** (`db.py`): `apply_user_rules` usaba `p.upper() in desc_upper` (substring sin límite de palabra). Ahora usa `\b...\b` con regex, igual que el motor de categorías.
  - **Filtro por fuentes** por regla: nuevo campo `fuentes` preservado en `PUT /config/usuarios` y pasado al motor. Si se completa, la regla solo aplica a movimientos de esas fuentes.
  - **Drag-to-reorder** con handle `⠿` en cada tarjeta de persona.
  - **Warning de keywords duplicadas** en rojo cuando una palabra aparece en más de una regla.
  - **Export / Import** (`GET /config/usuarios/rules/export`, `POST /config/usuarios/rules/import`) con validación YAML.
  - **Dry-run "Probar"** por regla: reutiliza el modal existente con modo `"user"` — muestra persona actual vs. nueva, selección por checkbox y `POST /config/usuarios/apply-selected` para aplicar los seleccionados.
  - Número de orden `#N` visible en cada tarjeta.

## 0.5.24

- **Fix: coincidencia parcial silenciosa en reglas de categorización** (`categorizer.py`): el regex no tenía word boundaries, por lo que "coto" matcheaba "PSICOTOLOGO", "dia" matcheaba "MEDIACION", etc. Ahora cada keyword se envuelve con `\b...\b` para coincidir solo en límites de palabra.
- **Cache de reglas** (`categorizer.py`): `load_rules()` ya no lee y parsea el YAML en cada transacción. Cachea en memoria y usa `os.path.getmtime` para invalidar automáticamente cuando el archivo cambia.
- **Auto-learn con confirmación editable**: al categorizar un gasto a mano, en lugar de agregar la descripción completa como keyword silenciosamente, ahora aparece un prompt en pantalla con el texto editable (pre-recortado a las 3 primeras palabras) para que el usuario confirme o ajuste antes de guardar en las reglas.
- **Filtro por fuentes en reglas** (`ReglaCategoria`): nuevo campo `fuentes: list[str]` — si se completa, la regla solo aplica a movimientos de esas fuentes. Se configura desde un dropdown multi-select con checkboxes en cada tarjeta de regla.
- **Filtro solo_egresos en reglas** (`ReglaCategoria`): nuevo campo `solo_egresos: bool` — cuando está marcado, la regla ignora ingresos (monto ≤ 0). Útil para distinguir pagos de cobros de la misma fuente (ej. MercadoPago).
- **Drag-to-reorder en lista de reglas**: las tarjetas de regla tienen un handle `⠿` para reordenar por drag & drop. El orden importa: gana la primera regla que coincide.
- **Estado de secciones persistido**: el expand/collapse de cada sección de Config se guarda en `localStorage` y se restaura al volver a la pestaña.
- **Warning de keywords duplicadas**: si una keyword aparece en más de una regla, se marca en rojo en ambas tarjetas para alertar sobre ambigüedad.
- **Export / Import de reglas**: botones "Exportar" e "Importar" en la cabecera de Reglas de categorización. Exporta el `rules.yaml` completo; importa desde archivo con validación.
- **Dry-run por regla con rango de fechas** (`POST /api/rules/preview`): botón "Probar" en cada regla abre un modal para buscar qué movimientos coincidirían en un período, mostrando categoría actual vs. nueva. Se pueden seleccionar individualmente y aplicar con `POST /api/rules/apply-selected`.
- **Nuevo campo `patron` en modelo** (`ReglaCategoria`): preserva reglas antiguas en formato regex al hacer PUT, evitando pérdida silenciosa de datos.
- **`default_rules.yaml` ampliado**: agregados merchants argentinos faltantes y 6 categorías nuevas: Impuestos, Seguros, Hogar, Deporte, Mascotas, Belleza.
- **`apply_rules_to_all` pasa monto y fuente** al categorizador para respetar los nuevos filtros `solo_egresos` y `fuentes` al reaplicar.

## 0.5.23

- **Consolidación preserva categoría del scraper al reemplazar con PDF**: cuando `consolidate_scraper_duplicates` elimina un gasto del scraper y lo reemplaza con el del PDF, ahora hereda la categoría del scraper si corresponde. Reglas: categoría `manual` del scraper siempre gana sobre la del PDF (salvo que el PDF también sea `manual`); categoría por `regla` se copia solo si el PDF no tiene ninguna. Así las categorizaciones hechas a mano no se pierden al subir el resumen.

## 0.5.22

- **Fix: saldo se reducía $5.000 en cada run por SUBE duplicado no insertado**: tres bugs combinados causaban que el movimiento `id=156859342409` (SUBE $5.000, 04/05) se detectara como nuevo en cada ejecución pero nunca se guardara en DB, y el delta de saldo igual se descontaba.
  - **Bug A** (`scrapers_db.py`): el LIKE de dedup buscaba `"payment_id": "123"` (string) pero MP guarda IDs como entero en JSON: `"payment_id": 123`. Ahora se buscan ambas formas.
  - **Bug B** (`scrapers_db.py`): cuando fallaba el match por ID, caía al fallback por descriptor (fuente+fecha+monto+desc), que encontraba otro SUBE $5.000 del mismo día y asumía que era el mismo movimiento. Ahora el fallback por descriptor se salta cuando hay un `scraper_uid` (si el ID no está en DB es un movimiento nuevo, aunque coincida en descripción).
  - **Bug C** (`scraper_scheduler.py`): `_apply_saldo_delta` usaba `result.movimientos` (todos los detectados por el scraper) en lugar de los efectivamente insertados en DB. Ahora `insert_movimientos_raw` acepta `_out_inserted` para devolver qué dicts se insertaron, y el scheduler usa esa lista para el delta.

## 0.5.21

- **Fix: settlement report detectaba 4 movimientos como nuevos en cada run**: `_get_existing_payment_ids` filtraba por `fecha >= hoy - dias`, por lo que entradas del settlement CSV con fecha fuera de esa ventana (ej. 30/04 cuando `dias=30` y hoy es 30/05) nunca aparecían en el set de IDs conocidos y se insertaban como nuevas cada vez. Se eliminó el filtro de fecha: ahora se cargan todos los `payment_id` de `fuente='mercadopago'` sin límite temporal.

## 0.5.20

- **Log de ajuste de saldo visible en el panel**: el delta de saldo por movimientos nuevos ahora aparece en el log del scraper (antes se aplicaba silenciosamente DESPUÉS de guardar el log). La línea muestra saldo anterior, cantidad y suma de movimientos nuevos, delta aplicado y saldo nuevo, ej: `Delta saldo mercadopago (ARS): saldo_anterior=$5.000.000,00 | 4 mov. nuevos suma_montos=+$1.250.000,00 delta=-$1.250.000,00 saldo_nuevo=$3.750.000,00`. Además se agrega `get_cuenta_saldo()` a `db.py` para leer el saldo actual antes de modificarlo.

## 0.5.19

- **Settlement report: retiros a CVU/CBU con monto en la descripción**: el CSV de PAYOUTS no incluye datos del destinatario (sin CBU, sin nombre). Para que el motor de reglas pueda distinguirlos, la descripción ahora incluye el monto: "Retiro a CVU/CBU $1.250.000". Así se pueden crear reglas específicas por importe ("$1.250.000 → Transferencia Magdalena").

## 0.5.18

- **Settlement report: parser completo según glosario oficial MP**: lee todas las columnas documentadas (`DESCRIPTION`, `PAYER_NAME`, `PAYER_ID_TYPE/NUMBER`, `POI_BANK_NAME`, `POI_WALLET_NAME`, `STORE_NAME/ID`, `POS_NAME/ID`, `FRANCHISE`, `LAST_FOUR_DIGITS`, `BUSINESS_UNIT`, `SUB_UNIT`, `TAXES_AMOUNT`, etc.). Descripción prioriza `DESCRIPTION` → `PAYER_NAME` → store/pos → fallback genérico. Manejo correcto de todos los `TRANSACTION_TYPE` del glosario: `REFUND`/`CHARGEBACK` → ingreso "Devolución/Contracargo", `WITHDRAWAL_CANCEL` → ingreso "Retiro cancelado". Pre-agrega filas con mismo `SOURCE_ID` (rendimientos de Mercado Crédito que MP divide en múltiples filas).

## 0.5.17

- **Settlement report: lectura de todas las columnas del CSV**: el parser ahora lee y almacena en `raw_data` todas las columnas disponibles (`PAYMENT_METHOD`, `PAYMENT_METHOD_TYPE`, `FEE_AMOUNT`, `REAL_AMOUNT`, `ORDER_ID`, `PACK_ID`, `SHIPPING_ID`, `INSTALLMENTS`, `COUPON_AMOUNT`, `MKP_FEE_AMOUNT`, `METADATA`). El log `[rpt]` en modo debug muestra todas las columnas no vacías por fila para facilitar el análisis de nuevos `TRANSACTION_TYPE`. Las claves con valor `None` se omiten del JSON para no inflar el almacenamiento.

## 0.5.16

- **Settlement report: correcciones de clasificación**: agrega `PAYOUTS` (plural, el tipo real en producción) explícitamente al set de retiros bancarios; descripción de retiros cambia a "Retiro a CVU/CBU". SOURCE_IDs de 13+ dígitos (IDs internos de MP, ej. intereses de Mercado Crédito) se clasifican como "Intereses/Rendimientos" en vez de "Liquidación SETTLEMENT". El campo `METADATA` del CSV ahora se loguea en debug `[rpt]` y se guarda en `raw_data` para análisis posterior.

## 0.5.15

- **Settlement report: estrategia list-first para evitar timeout**: antes de solicitar un reporte nuevo, consulta `GET /list` y descarga el más reciente si ya existe (0 s de espera). Solo si la lista está vacía hace `POST` + polling. La ventana del reporte nuevo es siempre los últimos 10 días (fija, independiente de `dias`); el dedup por `existing_ids` maneja cualquier solapamiento con imports anteriores.

## 0.5.14

- **Fix: settlement report — 3 correcciones según la documentación oficial de MP**: (1) endpoint corregido de `release_report` a `settlement_report`; (2) el polling ahora detecta que el reporte está listo por su presencia en la lista con `file_name` (no hay campo `status` en el listado); (3) parser CSV corregido: separador `;`, columnas `TRANSACTION_DATE`, `TRANSACTION_AMOUNT`, `TRANSACTION_CURRENCY`, `TRANSACTION_TYPE` — las columnas `NET_DEBIT_AMOUNT`/`NET_CREDIT_AMOUNT`/`RECORD_TYPE` no existen en el formato real.

## 0.5.13

- **Fix: release report timeout** (polling nunca matcheaba): el `POST` devuelve solo el ID numérico, no el `file_name`. El polling ahora matchea por `id` en la lista; una vez que el reporte está `processed` extrae el `file_name` real para la descarga. Timeout extendido a ~90 seg (30 × 3 s).

## 0.5.12

- **Fix: crash en release report** (`'int' object has no attribute 'strip'`): la API de MP devuelve el ID del reporte como entero. Se agrega `str()` antes de `.strip()` al extraer `file_name`/`id` de la respuesta.

## 0.5.11

- **MercadoPago: Release Report para transferencias a CVU/CBU externo**: implementa el flujo oficial de MP Reports API (`POST /v1/account/release_report` → polling → descarga CSV) para capturar transferencias salientes que no aparecen en `/v1/payments/search` (ej. retiros a cuenta bancaria de otra persona). El reporte se procesa de forma asincrónica con hasta ~60 s de espera; si el token no tiene permisos (403) o el reporte no está listo, se loguea y continúa sin error. La deduplicación cruza el `SOURCE_ID` del CSV contra los `payment_id` ya en la DB para evitar duplicar lo importado vía payments. El modo debug muestra cada fila del CSV con tag `[rpt]`.

## 0.5.10

- **MercadoPago: drops silenciosos ahora visibles**: `_payment_to_movimiento` devuelve el motivo del descarte (`sin_fecha`, `monto=0`, `sin_descripcion`, `excepcion: …`). Cuando un pago no puede convertirse, se loguea siempre con `[!] SIN-DATOS id=… motivo=…`, independientemente del modo debug.

## 0.5.9

- **MercadoPago: fix retiros a CBU externa (two-pass)**: la API no devuelve `collector_id` en la query de payer, por lo que el fix anterior era inefectivo. Ahora la query de **collector se corre primero** y se recolectan los IDs de `account_fund` que aparecen ahí (= depósitos propios, `payer==collector==user`). La query de payer luego difiere solo esos IDs; cualquier `account_fund` que no esté en ese set se captura como "Retiro a CBU". El tag de debug cambió de `DEFER-IN` a `RETIRO-CBU` para los retiros externos.

## 0.5.8

## 0.5.7

- **MercadoPago: fix retiros a CBU externa no se importaban**: el filtro DEFER-IN descartaba todos los `account_fund` en la query de payer, incluyendo transferencias salientes a un CBU de otro banco. Ahora sólo se difieren los `account_fund` cuyo collector es el mismo usuario (depósito propio); si el collector es externo, se captura como egreso con descripción "Retiro a CBU".
- **MercadoPago: revertido endpoint `/mercadopago_account/movements/search`**: ese endpoint no está en la documentación oficial y devolvía 403. Se eliminó la consulta; los retiros a CBU ahora se capturan correctamente vía el filtro corregido en `/v1/payments/search`.

## 0.5.6

- **Fix: chips de categorías en chart presupuesto vs real no respondían al click**: el onclick se generaba como atributo HTML con `JSON.stringify(cat)` (comillas dobles), lo que rompía el atributo. Se reemplazó por `createElement` + `chip.onclick = () => toggleBudCat(c)`, igual que los chips de la tab Gastos.
- **MercadoPago: retiros a CBU vía `/mercadopago_account/movements/search`**: los retiros de billetera a cuenta bancaria (CBU) no aparecen en `/v1/payments/search`. Se agrega consulta al endpoint de movimientos bancarios; los movimientos cuyo `reference_id` ya existe en la DB se descartan para evitar duplicados. En modo debug se loguean todos los movimientos con `[mvt]` para inspección.
- **MercadoPago: fecha en líneas de debug**: las líneas `[dbg]` de pagos ahora incluyen la fecha (`date_created[:10]`) para facilitar la identificación de transacciones.

## 0.5.5

- **Chart presupuesto vs real movido a tab Gráficos**: el card ahora aparece al inicio de la solapa Gráficos (arriba de los filtros y charts personalizados) en lugar de en la página de inicio. Se dispara al abrir la tab y al cambiar el mes.

## 0.5.4

- **Fix: chart presupuesto vs real rompía la página**: las constantes `_BUD_MODE_LABELS/CYCLE/TITLES` estaban declaradas como `const` al final del archivo pero se accedían en `applyUiPrefs()` que corre en línea 80 (temporal dead zone). Se movieron al inicio del archivo junto a las constantes del gráfico mensual.

## 0.5.3

- **Chart presupuesto vs real en el inicio**: nueva tarjeta en la página principal (antes de los tabs) con un gráfico de barras agrupadas por categoría. Barra izquierda = presupuesto (verde); barra derecha = gasto real (amarillo si dentro del presupuesto, rojo si lo supera). Muestra por defecto el último mes cerrado. Incluye selector de mes persistente y chips de categorías filtrables (ambos se guardan en `localStorage` entre sesiones). El card tiene el mismo toggle normal/compacto/oculto que el gráfico mensual superior.

## 0.5.1

- **Fix: saldo MercadoPago siempre daba 404**: el endpoint `/v1/account/balance` no está disponible para tokens personales. Se reemplazó por `/users/{user_id}/mercadopago_account/balance`, que sí responde con `available_balance` y `currency_id`. El `user_id` ya estaba disponible del paso `/users/me`.

## 0.5.2

- **Fix: widget de saldos no se actualizaba tras ejecutar scraper**: `runCuentaInstance` llamaba `loadCuentas()` pero no `loadSaldos()` en el `finally`. El widget superior ahora refleja el saldo nuevo inmediatamente.
- **Encriptación de credenciales habilitada**: se agrega `scraper_encryption_key` a la config del add-on (str? en `config.yaml`). Ponerle cualquier string largo activa Fernet (AES-128-CBC + HMAC-SHA256) para las credenciales de scrapers. Requiere la dependencia `cryptography`, ahora incluida en `requirements.txt`.
- **MercadoPago: saldo por delta de movimientos**: como la API devuelve 403 para el endpoint de saldo con tokens personales, el scheduler ahora aplica el delta neto de cada run a `cuentas.saldo` (sólo si `auto_saldo=1`). El usuario setea el saldo correcto una vez; cada import lo mantiene actualizado automáticamente. La lógica es genérica: aplica a cualquier scraper que no devuelva saldo de API.
- **Tab Scrapers eliminada**: las credenciales, estado, "Importar pendientes", "Borrar sesión" y TOTP de cada scraper ya estaban disponibles en el panel inline de cada cuenta (tab Cuentas). La tab duplicaba la funcionalidad. Se agregan los botones faltantes ("Importar pendientes", "Borrar sesión", TOTP) al panel inline para que quede paridad completa.
- **Tab Importar eliminada**: el "último import" de cada parser ahora se muestra en el panel PDF parser inline de cada cuenta (en tab Cuentas). La opción RG 5617 se movió a Config → Interfaz.

## 0.4.9

- **IOL: usar `/api/v2/estadocuenta` como fuente de saldos**: en vez de sumar manualmente los `valorizado` del portafolio, ahora se consulta el endpoint `/api/v2/estadocuenta` que devuelve `cuentas[].total` (cash + títulos valorizados) separado por moneda (`peso_Argentino` / `dolar_Estadounidense`). Es la fuente autorizada de IOL y evita desincronías entre la valorización del portafolio y el saldo real de la cuenta.
- **IOL: portafolio solo para log**: `/api/v2/portafolio/argentina` ya no computa saldos; muestra cada tenencia con símbolo, valorización, variación diaria y tipo de instrumento para visibilidad en el log del run.
- **IOL: `_process_estadocuenta()`**: nuevo método que parsea las cuentas del estado de cuenta, loguea cash + títulos por cuenta y devuelve el total ARS y USD acumulado.
- **IOL: `_log_holdings()`**: rebautizado desde `_process_portfolio()`; ahora es puro logging sin side-effects sobre saldos.

## 0.4.8

- **IOL: fix campos anidados en `titulo{}`**: los campos `simbolo`, `descripcion` y `tipo` no están directamente en el activo sino dentro del sub-objeto `titulo`. Ahora se leen con fallback (`titulo.X` o `a.X`). Como consecuencia el símbolo mostraba `?` y el tipo quedaba vacío.
- **IOL: fix variación diaria**: la API devuelve `variacionDiaria` en vez de `variacion`; se usa el primero disponible con fallback.
- **IOL: `_tipo_label()` con matching flexible**: reemplaza el dict exacto por una función que hace substring lowercase, cubriendo "FondoComun", "fondos_comunes_de_inversion" y cualquier variante futura.
- **IOL: log de diagnóstico mejorado**: muestra las claves del root y el primer activo completo (600 chars) en vez de los 400 chars del response entero (que se cortaba antes de ver `titulo`).
- **UI: botón "⎘ Copiar" en el log de instancias**: el panel de cuenta (tab Cuentas) ahora tiene el mismo botón de copiar que la tab Scrapers, con IDs `copy-log-btn-inst-{id}` y `scraper-log-pre-inst-{id}`.

## 0.4.7

- **IOL: fix moneda ARS/USD**: la API puede devolver `moneda` como entero (0=ARS, 1=USD) o string ("peso_argentino"/"dolar_estadounidense"). Reemplazado el dict-lookup por la función `_to_moneda()` que cubre ambos formatos. También fix en `estado_cuenta.saldos`: antes siempre sumaba a ARS; ahora cada ítem de saldo respeta su propia moneda.
- **IOL: estructura de respuesta defensiva**: `_process_portfolio()` ahora acepta tanto `{"activos":[...], "estado_cuenta":{...}}` (snake_case) como `{"activos":[...], "estadoCuenta":{...}}` (camelCase) o un array directo de activos. Agrega log de diagnóstico con los primeros 400 caracteres del raw para identificar la estructura real.
- **Log visible en panel de cuenta**: el scheduler no pasaba `last_log` a `update_instance_status`, por lo que `scraper_instances.last_log` nunca se actualizaba y el panel mostraba vacío. Ahora se pasa en todos los paths (ok, error, error_msg).

## 0.4.6

- **Nuevo scraper: InvertirOnline (IOL)**: consulta el portafolio vía API REST (sin Selenium). Autentica con usuario/contraseña usando OAuth2 `grant_type=password`, almacena el token y lo refresca automáticamente con `refresh_token` antes de que expire (TTL 1 hora con margen de 5 min). En cada run obtiene `/api/v2/portafolio/argentina`, suma el `valorizado` por moneda y actualiza `saldo_ars` (posiciones ARS + efectivo en cuenta) y `saldo_usd` (posiciones USD) en la cuenta "InvertirOnline". Opcionalmente importa operaciones terminadas (compras/ventas/cobros) como movimientos si el checkbox "Importar operaciones" está activo. Para configurarlo: Cuentas → crear cuenta tipo Scraper → selector → InvertirOnline.
- **Fix scheduler: saldo hardcodeado a "bbva_cuenta"**: `_run_instance_job` y `run_instance_now` leían el saldo del resultado con `result.saldos.get("bbva_cuenta", {})`, lo que devolvía `None` para MP, IOL y cualquier otro banco que no sea BBVA. Ahora usa el primer valor disponible de `result.saldos` de forma genérica.
- **Nueva cuenta default "InvertirOnline"** (`fuente="invertironline"`, `moneda="MULTI"`, `activa=1`, `auto_saldo=1`) en `init_db()`.

## 0.4.5

- **Fix HTTP 500 al cambiar el scraper / borrar cuenta / crear cuenta**: las rutas `PUT /api/cuentas/{fuente}/scraper`, `DELETE /api/cuentas/{fuente}` y `POST /api/cuentas` eran sync (`def`) y llamaban a `reload_scheduler()`. FastAPI ejecuta los `def` en un threadpool sin event loop, y `_scheduler.start()` (APScheduler AsyncIO) hace `asyncio.get_running_loop()` → `RuntimeError: no running event loop`. Fix: las tres rutas pasaron a `async def`.
- **Defensa adicional en `reload_scheduler`**: si en el futuro algo todavía la llama desde un thread sin event loop, en lugar de explotar ahora loguea un warning y devuelve. Los cambios se aplican en el próximo restart del add-on (o llamando `POST /api/scrapers/scheduler/reload` desde un endpoint async).

## 0.4.4

Tres cambios grandes en la tab Cuentas: cuentas colapsables, parser por cuenta, y delete de cuentas auto.

- **Cada cuenta es colapsable con botón +/−**: por default todas arrancan cerradas (sólo se ve header con nombre + badge + moneda + saldo). Click en cualquier parte del header (o en el +/−) expande/colapsa el body con detalles, acciones, parser y scraper. El estado expandido se persiste en `localStorage` (`cuenta-expanded-<fuente>`) por cuenta. Adiós scroll infinito.
- **PDF parser inline por cuenta** (sección "📄 PDF parser"):
  - Nueva columna `parser_type` en tabla `cuentas` (migración `cuentas_parser_type_v1`).  Las cuentas pre-existentes la heredan de su fuente (bbva_cuenta → parser bbva_cuenta, amex → parser amex, etc.).
  - Combo para asignar/cambiar el parser de cada cuenta auto (lista viene del nuevo endpoint `GET /api/parsers`).
  - Botón `⬆ Subir PDF/XLSX` que abre el file picker filtrado por el accept del parser (.pdf o .xls,.xlsx).
  - Backend: `PUT /api/cuentas/{fuente}/parser` actualiza, `POST /api/cuentas/{fuente}/upload` recibe el archivo. Internamente delega a `/api/upload` con el nuevo flag `target_fuente`: el archivo se parsea con el parser de la cuenta, pero los gastos se guardan con la **fuente real de la cuenta** (no la del parser). Eso permite que cuentas con slug custom (ej. `bbva_pesos_personal`) reusen un parser estándar.
  - La tab Importar vieja sigue viva — se va a migrar progresivamente. Por ahora, ambos coexisten.
- **Eliminar cualquier cuenta** (no sólo manuales):
  - Nuevo endpoint `GET /api/cuentas/{fuente}/gastos-count` para que el front muestre cuántos gastos van a desaparecer antes de confirmar.
  - `DELETE /api/cuentas/{fuente}` ahora acepta cuentas auto también (antes sólo manuales). Borra: cuenta + gastos + filas en `movimientos_raw`. Si la cuenta estaba linkeada a una `scraper_instance`, la instancia **no se borra** (otras cuentas podrían usarla).
  - UI: botón `🗑 Eliminar cuenta` ahora aparece en TODAS las cuentas. El confirm muestra cantidad exacta de gastos a borrar.

## 0.4.3

- **Botón "+ Crear cuenta" arriba a la derecha del tab**: lo movemos del final del listado al header del sub-tab Cuentas (flex `space-between` con el hint a la izquierda). En mobile el botón pasa abajo del hint a ancho completo.
- **Tercera opción "PDF parser" en el modal de creación**: el radio de tipo ahora tiene 3 opciones:
  - **Manual** → movimientos cargados a mano (sin cambios respecto a v0.4.2).
  - **PDF parser** → cuenta auto sin scraper, alimentada solo por PDFs importados (esquema histórico de AMEX/BBVA MC/Visa/Galicia MC). Backend: `tipo=auto` sin `scraper_instance_id`.
  - **Scraper** → cuenta auto con instancia de scraper asignada. Backend: `tipo=auto` con `scraper_instance_id` + `product_key`.
- **Hint actualizado** en el header del tab explica los 3 tipos de un vistazo.
- El combo de scraper solo aparece cuando elegís "Scraper" (antes aparecía con cualquier "Automática").

## 0.4.2

- **Reubicación del botón "Crear cuenta"**: el botón estaba arriba del listado de cuentas en una `rules-header` (lo que parecía un banner superior). Lo movemos al final del listado como una "card" punteada `+ Crear cuenta` (más cerca de las cuentas existentes, menos visualmente intrusivo).
- **Modal unificado con tipo + scraper**: el flujo previo era una secuencia de prompts (nombre → moneda) y solo permitía crear cuentas manuales. Ahora click → un solo modal con:
  - **Nombre**
  - **Tipo**: Manual (movimientos a mano) o Automática (scraper / PDFs)
  - **Moneda** (ARS / USD)
  - **Scraper** (solo si tipo=Automática): combo con instancias existentes + opción `+ Nueva instancia BBVA/AMEX/...`
- **Backend extendido**: `POST /api/cuentas` acepta `tipo: "manual"|"auto"` + `scraper_instance_id` + `scraper_product_key`. Nueva función `create_cuenta_auto` en `db.py` que crea la cuenta con slug derivado del nombre + linkea opcionalmente a una instancia. Para BBVA se valida que `product_key` sea `ARS`/`USD`/`EUR` (default ARS si viene cualquier otra cosa).
- **Flujo "crear con nueva instancia"**: si en el modal elegís "+ Nueva instancia BBVA", el JS primero crea la instancia (deshabilitada, sin credenciales), después crea la cuenta linkeada — luego abrís el panel inline de la cuenta y completás las credenciales. Cancelar el prompt del nombre de la instancia aborta toda la creación.

## 0.4.1

**Fase 2 de multi-instancia — UI en la tab Cuentas.**

Cada cuenta `tipo=auto` ahora tiene un panel inline "🤖 Scraper" con todo el flujo de gestión del scraper que la alimenta. La tab Scrapers (vieja) se mantiene viva en v0.4.1 — la limpiamos en v0.4.2.

- **Nuevos endpoints backend** (`routes/scraper_instances_routes.py`):
  - `GET /api/scraper-types` — lista de tipos de scraper disponibles (BBVA/AMEX/Galicia/MP) con sus definiciones de campos. Usado por el combo "Nueva instancia".
  - `GET /api/scraper-instances` — lista de instancias del usuario (secretos enmascarados).
  - `GET /api/scraper-instances/{id}` — detalle de una instancia + cuentas que alimenta.
  - `POST /api/scraper-instances` — crear nueva instancia (opcionalmente linkea a una cuenta con `cuenta_fuente` + `product_key`).
  - `PUT /api/scraper-instances/{id}` — actualizar nombre/config/schedule/enabled (mergea config preservando passwords vacíos).
  - `DELETE /api/scraper-instances/{id}` — eliminar instancia (las cuentas que la usaban quedan sin scraper, no se borran gastos).
  - `POST /api/scraper-instances/{id}/run` — trigger manual de la instancia.
  - `PUT /api/cuentas/{fuente}/scraper` — asignar/desasignar instancia a cuenta (con `product_key`).
- **UI en tab Cuentas — panel inline por cuenta auto**:
  - Combo "Scraper que la alimenta" con instancias existentes + opciones "+ Nueva instancia BBVA/AMEX/Galicia/MercadoPago".
  - Si la cuenta tiene una instancia asignada: panel inline con form de credenciales (campos vienen de `scraper-types`), nombre, hora diaria, toggle Activa, badge de estado, botones [Guardar] / [▶ Ejecutar ahora] / [🗑 Eliminar instancia].
  - Sección "📋 Detalle del último run" colapsable con el `last_log`.
  - Sección "📦 Registros ingresados" reusando el componente actual (delete con ✕ funciona igual — hard delete de v0.3.68).
  - Status info: último intento, último OK, próximo run (del scheduler).
  - Para banco BBVA, `product_key` se asigna automáticamente según la moneda de la cuenta (ARS/USD/EUR).
- **Crear "+ Nueva instancia" desde combo**:
  - Prompt para el nombre (sugerencia: "{Banco} {nombre_cuenta}").
  - Crea la instancia deshabilitada (para que completes credenciales antes de activarla).
  - La linkea automáticamente a la cuenta + setea el `product_key`.
  - El combo se actualiza, el panel inline aparece para que entres password/usuario.
- **Compatibilidad**: tab Scrapers (vieja) sigue funcionando — actúa sobre la instancia default de cada banco. Los endpoints `/api/scrapers/*` legacy siguen vivos.

## 0.4.0

**Fase 1 de multi-instancia de scrapers (backend, sin cambios visibles en UI).**

Refactor preparatorio para que un usuario pueda tener varias instancias del
mismo banco (ej. BBVA Personal + BBVA Empresa), cada una con sus propias
credenciales y su propio mapeo a cuentas. v0.4.1 agrega la UI desde la tab
Cuentas; v0.4.2 limpia el código legacy.

- **Nueva tabla `scraper_instances`** (por usuario): cada instancia tiene
  `banco`, `nombre`, `config` (JSON con credenciales, dias, monedas, etc.),
  `schedule`, `enabled`, y todos los campos de status (`ultimo_run`, `estado`,
  `saldos`, `error_msg`, `last_log`). Reemplaza a `scraper_credentials.json` y
  a la tabla `scraper_status` como source-of-truth. Ambos quedan en disco/DB
  por back-compat durante v0.4.x.
- **Nuevas columnas en `cuentas`**: `scraper_instance_id` (FK opcional a
  `scraper_instances.id`) y `scraper_product_key` (TEXT: "ARS"/"USD"/"EUR"/
  "main" — qué "producto" de la instancia alimenta esta cuenta). Decision 1=B:
  una cuenta es alimentada por UNA instancia; dos cuentas BBVA = dos
  instancias = dos logins independientes (con sus propias credenciales,
  aunque sean idénticas).
- **Migración automática `scraper_instances_v1`**: al arrancar v0.4.0, lee
  `scraper_credentials.json` + `scraper_status` y crea una instancia
  "{Banco} default" por cada banco existente. Linkea las cuentas auto
  pre-existentes (`bbva_cuenta` → BBVA default con product_key=ARS, `amex` →
  AMEX default con product_key=main, etc.). No se renombra ninguna fuente
  existente — gastos históricos quedan intactos.
- **Encryption-ready (opcional)**: nuevo módulo `scraper_crypto.py` con
  fallback graceful. Si `SCRAPER_ENCRYPTION_KEY` está seteada Y `cryptography`
  está instalado → encripta config con Fernet; si falta alguno → plaintext
  (default actual). Cada fila de `scraper_instances` tiene un flag
  `config_encrypted` para coexistencia. Para habilitar: agregar `cryptography`
  a requirements + setear la env var en la config del add-on de HA.
- **Scheduler refactor**: ahora itera `scraper_instances` (filtrado por user
  data_dir), no más `find_all_enabled_configs` de credentials. Cada job
  carga la instancia, descifra config, agrega `__cuentas__` con la lista de
  cuentas mapeadas (fuente + product_key) y se lo pasa al scraper. Status se
  actualiza vía `update_instance_status` (mirror a `scraper_status` legacy
  para que la UI siga funcionando sin tocarse).
- **BBVA scraper — modo multi-instancia**: si recibe `__cuentas__` en config,
  mapea `product_key=ARS/USD/EUR` → cuenta destino y emite movimientos con la
  `fuente` correspondiente. Si NO recibe `__cuentas__` (standalone/testing),
  cae al modo legacy (filtra por config `monedas` y emite todo a
  `bbva_cuenta`).
- **AMEX/Galicia/MP** (single-product): el scheduler hace remap post-scrape:
  si la instancia tiene una cuenta mapeada con fuente custom (ej. `amex_personal`),
  re-construye los `MovimientoRaw` con esa fuente. Los scrapers no necesitan
  cambios.
- **`fuentes_for_banco` ahora resuelve por query a DB** en lugar del mapping
  hardcoded `_BANCO_FUENTES`. Cuando un usuario crea cuentas con slugs
  custom en v0.4.1+, esta función las captura automáticamente. Fallback al
  hardcoded sólo si las tablas multi-instancia no existen (primer arranque
  pre-migración).
- **Mirror back-compat**: `set_bank_config` (escritura de credenciales desde
  la UI viejos) también actualiza la instancia default del banco; si no
  existe, la crea + linkea la cuenta default. `update_instance_status` también
  refresca `scraper_status` (legacy) para la instancia default de cada banco.
- **Sin cambios visibles**: la tab Scrapers actual sigue funcionando igual —
  por debajo opera sobre la instancia default. Los endpoints `/api/scrapers/...`
  no se rompieron. La migración garantiza que un usuario que actualice de
  v0.3.x a v0.4.0 no note ninguna diferencia funcional.

## 0.3.71

- **Scraper MP — fix signo `account_fund`**: los depósitos bancarios (`op=account_fund`, tipo `bank_transfer`) aparecían en ambas queries igual que `partition_transfer`. Se agregan al defer de la query de payer (sign=+1) para capturarlos solo en la de collector (sign=−1), evitando que $8M/$4.5M/etc. queden importados como egresos.
- **Scraper MP — descripción `account_fund`**: nueva Regla 2 que retorna `"Depósito bancario"` para cualquier pago con `op=account_fund`, en lugar de caer al fallback genérico.
- **Scraper MP — descripción `money_transfer` ingreso**: para transferencias recibidas (sign=−1), la descripción ahora incluye el nombre/email del pagador: `"fausto@sbsoft.com.ar — Transferencia: Varios"`. Los egresos mantienen `"Transferencia: Varios"`.
- **Scraper MP — raw_data `payer_email`**: se guarda el email del pagador en `raw_data` para movimientos ingresados como ingresos (sign=−1).

## 0.3.70

- **Scraper MP — debug log enriquecido**: cuando "Log de debug" está tildado, cada pago muestra líneas adicionales con `payer_email`, `payer_ident` (tipo:número DNI/CUIL), `ext_ref` (external_reference, útil para CVU), `td_ref` (transaction_details.payment_method_reference_id, el CVU/CBU concreto) y `td_bank` (financial_institution). Solo aparecen las líneas con valor no vacío. Permite ver qué campos trae la API para transferencias y decidir qué enriquecer en la descripción.

## 0.3.69

- **BBVA — filtro de monedas a importar** (`monedas` en credentials): nuevo campo text en el config del scraper BBVA donde se ingresan los códigos de moneda a procesar, separados por coma (`ARS`, `USD`, `EUR`).  Si está vacío o sin setear, el default es **solo `ARS`** (conservador — no importa dólares ni euros sin pedirlo explícitamente, antes los importaba todos a `bbva_cuenta`).  La detección de moneda por cuenta usa la lógica que ya estaba en `_detect_moneda` (prefiere `codigoMoneda`/`moneda` de la API, fallback al alias "Pesos"/"Dolares"/"Euros").  El log muestra `monedas_filtro=['ARS']` al inicio y `Saltando cuenta: Dolares (moneda=USD no está en ['ARS'])` por cada cuenta filtrada, así queda claro qué se procesa y qué no.  El saldo de las cuentas filtradas se sigue registrando (informativo) pero sin importar movimientos.  Esto es la fase 1 hacia multi-instancia/multi-cuenta — eventualmente la idea es permitir mapeo per-cuenta (cuenta USD → otra fuente/usuario distintos).

## 0.3.68

- **Botón ✕ en "📦 Registros ingresados" — hard delete único (eliminamos el soft delete)**: ya no se usa el estado `ignored` como sentinel anti-reimport.  Un solo clic en ✕ borra definitivamente la fila de `movimientos_raw` y, si tenía un gasto vinculado, también borra el gasto.  Comportamiento idéntico en todos los scrapers (MP, AMEX, BBVA, Galicia, etc.).
- **Trade-off conocido**: como la fila desaparece de la DB, el dedup de `insert_movimientos_raw` no la detecta en el siguiente run, así que el scraper SÍ puede re-importar la transacción si todavía cae dentro del rango temporal configurado (`dias`).  El diálogo de confirmación lo aclara explícitamente con un ⚠.  Para bloquear definitivamente: bajar `dias` (que la transacción quede fuera del rango) o usar una regla de categorización que la filtre por descripción.
- **Filas viejas con estado `ignored`** (del esquema previo): siguen existiendo pero ya nada las crea.  Si querés limpiarlas, hacé clic en su ✕ (ahora con el hard delete, las elimina del todo).

## 0.3.67

- **Fix BBVA paginación — `fechaDesde`/`fechaHasta` ahora se envían en TODAS las páginas, no solo la primera**: bug reportado: configurando `dias=35` el scraper importaba movimientos hasta diciembre del año anterior (~150 días). Causa: la primera llamada de paginación incluía `fechaDesde`/`fechaHasta` (más todos los filtros vacíos requeridos), pero las páginas siguientes solo enviaban `idProducto + ultimoMovimientoMostrado`, lo que hacía que BBVA paginara por TODA la historia de la cuenta ignorando el filtro temporal. Fix: incluir el payload completo (incluyendo `fechaDesde`/`fechaHasta` y los demás filtros vacíos) en cada iteración del while.
- **Safety extra — filtro client-side por fecha**: como defensa adicional por si BBVA en algún momento ignora el filtro server-side, ahora descartamos movimientos cuya `fecha` sea anterior a `fechaDesde` antes de procesarlos. El batch viene newest-first, así que cuando aparece el primero fuera de rango cortamos la página y dejamos de paginar (todos los siguientes son aún más viejos). Si esto se activa, queda registrado en el log: `[filter] descartados N movimientos anteriores a DD/MM/YYYY`.

## 0.3.66

- **Default user para los gastos importados por el scraper BBVA + detección de moneda por cuenta**: agrega un nuevo campo opcional `usuario_default` en la config del scraper BBVA ("Usuario para los gastos importados", ej. "Sebastián"). Cuando el scraper importa movimientos, ese nombre se escribe en `raw_data["usuario"]` y `importar_a_gastos` lo aplica como el usuario del gasto creado. Si el campo está vacío, fallback al `fuente_usuario["bbva_cuenta"]` de `user_config` (que ya tenía default "Titular"). El nuevo fallback en `importar_a_gastos` aplica a TODOS los scrapers — antes los gastos importados quedaban con `usuario=NULL` si el scraper no lo seteaba explícitamente.
- **Detección automática de moneda en BBVA**: la cuenta de Pesos se importaba siempre con `moneda="ARS"` hardcodeada, lo que fallaría cuando el usuario quiera empezar a importar la cuenta de Dolares/Euros también. Nueva función `_detect_moneda(cuenta, alias)`: prefiere los campos `codigoMoneda`/`moneda`/`currency` de la API si están (acepta `ARS/032`, `USD/840`, `EUR/978` y nombres en español), si no deduce por el alias de la cuenta ("Pesos"→ARS, "Dolares"/"Dólares"→USD, "Euros"→EUR). Se propaga a `_fetch_movimientos` y `_parse_batch` para que cada movimiento se importe con la moneda correcta. `saldos` también separa `saldo_ars`/`saldo_usd`/`saldo_eur` según corresponda.
- **Groundwork para Fase 2 (multi-instancia / multi-cuenta)**: dejar la base lista para escenarios como "BBVA personal + BBVA empresa" o "Pesos→usuario A, Dólares→usuario B". El refactor del scheduler para soportar múltiples configs por banco vendrá más adelante.

## 0.3.65

- **Unificación del botón ✕ en "📦 Registros ingresados" — mismo comportamiento para todos los scrapers**: antes MercadoPago borraba definitivamente con un solo clic (porque tenía dedup propio vía `payment_id`) mientras que AMEX/BBVA/Galicia hacían soft delete (marcaban como `ignored`). Eso confundía: el diálogo y la consecuencia eran distintos según el banco. Ahora con el dedup unificado de `insert_movimientos_raw` (v0.3.61) que mira todos los estados incluido `ignored`, el sentinel funciona para cualquier scraper. **Nueva regla única**:
  - **1er ✕** sobre un registro (cualquier estado salvo `ignored`): soft delete → se borra el gasto vinculado si lo había, el raw queda como `ignored`. El scraper no lo va a reimportar.
  - **2do ✕** sobre el mismo registro (ya en `ignored`): hard delete → la fila se borra de la DB. El scraper puede volver a importar esa transacción en el próximo run.
  - **Entrada manual de /quick**: siempre hard delete (no tiene "reimport" posible).
  - Tooltips y diálogos de confirmación actualizados para reflejar esto consistentemente en MP, AMEX, BBVA, Galicia, etc.
- **Limpieza de archivos dev de BBVA**: eliminados `inject_bbva_session.py` y `test_bbva_login.py` (eran helpers de la etapa "API directa" / debugging local, ya no aplican con el login natural del browser de v0.3.55+). `.gitignore` actualizado para excluir `*_test.yaml`, `inject_*.py` y `test_*.py` y evitar que vuelvan a entrar al repo con credenciales reales.

## 0.3.64

- **Fix signo BBVA cuenta — el `importe` viene firmado por la API**: el log diagnóstico de v0.3.63 reveló dos cosas: (1) BBVA NO devuelve `saldo` por movimiento en `/cliente/productos/cuentas/movimientos` (siempre `saldo=0,00`), por lo que la comparación de saldos es inútil; (2) BBVA SÍ devuelve `importe` firmado — negativo para egresos, positivo para ingresos. Antes mi código trataba "importe positivo" como ambiguo (caía al default `+1 egreso`), por lo que los ingresos del usuario se importaban con signo invertido. Fix: `_detect_sign` ahora confía en el signo del `importe` como fuente de verdad (segunda prioridad después de la `naturaleza` explícita que no existe en este endpoint). La comparación de saldos queda como tercer fallback defensivo.
- **Diagnóstico mejorado**: el log ahora muestra el `importe` con signo (`importe=+10096673.65` o `importe=-8000000.00`) en lugar del valor absoluto, y la etiqueta `ingreso`/`egreso` en lugar de `sign=±1` para que sea más legible de un vistazo.
- **Limpieza de gastos viejos con signo erróneo**: los gastos importados antes de v0.3.64 con signo invertido siguen en la tabla. Como el ✕ del UI marca el raw como `ignored` (sentinel anti-reimport), eso solo no alcanza para re-importar con el signo correcto. Dos opciones para limpiar:
  - **Manual**: editar el monto del gasto en la UI principal cambiándole el signo (negativo si es ingreso).
  - **Reset completo del scraper BBVA cuenta** vía SQL (perdés la categorización manual): `DELETE FROM gastos WHERE fuente='bbva_cuenta'; DELETE FROM movimientos_raw WHERE fuente='bbva_cuenta';` — luego correr el scraper de vuelta y se importan limpios con signo correcto.

## 0.3.63

- **Fix detección de signo en movimientos BBVA — usar campos explícitos antes que diferencia de saldos**: la lógica anterior comparaba `saldo[i]` con `saldo[i+1]` para deducir si era ingreso/egreso, pero como el batch viene newest-first, el movimiento **más viejo** del batch no tiene `saldo[i+1]` para comparar — entonces siempre defaulteaba a egreso, incluso si era un ingreso. Síntoma: cuenta con 2 movimientos donde el más viejo era ingreso aparecía con signo invertido. **Nueva estrategia en `_detect_sign`** (en orden de confiabilidad):
  1. Campo explícito en la API: `naturalezaMovimiento`, `naturaleza`, `signo`, `tipoSigno`, `codigoSigno`, `tipoNaturaleza`, `indicadorMovimiento` con valores tipo `C/D`, `+/-`, `1/0`, `I/E`, `CREDITO/DEBITO`, etc.
  2. Comparación de saldos (la lógica anterior — sigue siendo correcta cuando hay `mov_older`).
  3. Si `importe` viene firmado por BBVA (`importe < 0` → egreso), usar ese signo.
  4. Default egreso (último recurso).
- **Diagnóstico**: el log del scraper ahora imprime los keys del primer movimiento de cada batch (`[debug] keys del primer mov: [...]`) para confirmar qué campos trae BBVA, y por cada movimiento muestra `sign={+1/-1} ({reason})` con el motivo de la decisión (`naturaleza=C`, `saldo↑`, `importe<0`, `default`). Esto permite afinar la detección si BBVA usa campos distintos a los probados. Se guarda también `sign_reason` en `raw_data` para auditoría posterior.

## 0.3.62

- **Fix UI "Sin registros guardados" — `list_movimientos_raw` expande banco→fuentes**: la sección "📦 Registros ingresados" en cada tab de banco mostraba "Sin registros guardados" aún cuando había filas en `movimientos_raw`. La UI llamaba `/api/scrapers/movimientos-raw?fuente=bbva` con el banco como filtro, pero las filas tenían `fuente='bbva_cuenta'`. Mismo bug que arreglamos en el scheduler en v0.3.57, ahora también en el query del backend. Nuevo helper `fuentes_for_banco(banco)` con el mapping `{"bbva": ["bbva","bbva_cuenta","bbva_visa","bbva_mc"], "amex": ["amex"], "galicia": ["galicia","galicia_mc"], "mercadopago": ["mercadopago"]}` — si el filtro `fuente` recibido es una banco-key conocida, se expande; si es una fuente específica devuelve `[fuente]` (compatibilidad). Usado en:
  - `list_movimientos_raw(fuente=...)` → SQL `fuente IN (?, ?, ...)` con todas las fuentes del banco.
  - `/api/scrapers/status` → suma `pendientes` de todas las fuentes del banco para el badge.
  - Como efecto colateral, `auto_import_unmatched("bbva")` y `run_conciliation(fuente="bbva")` también funcionan ahora (defensa adicional sobre el fix de v0.3.57).

## 0.3.61

- **Fix duplicados al scrapear — dedup en `insert_movimientos_raw` + migración para limpiar los existentes**: bug en la transición v0.3.55→0.3.57 dejó filas atascadas en `movimientos_raw` con estado='new' (porque la conciliación buscaba `fuente="bbva"` pero los datos tenían `fuente="bbva_cuenta"`). Cuando v0.3.57 arregló el scheduler, en el próximo run se reimportaron los 2 movimientos nuevos JUNTO con los 2 que estaban atascados → 4 gastos donde debería haber 2. **Fix doble**:
  - `insert_movimientos_raw` ahora dedupea: si ya existe una fila con misma `(fuente, fecha, monto, descripcion, moneda)` — en cualquier estado, incluyendo `imported` e `ignored` — se skipea sin insertar. Si el scraper guarda un identificador único en `raw_data` (`numero_operacion`, `payment_id`, `operation_id`, `transaction_id`), se usa eso como llave de dedup en lugar del descriptor (más preciso).
  - Migración `dedup_scraper_gastos_v1` (corre una sola vez al arrancar): encuentra gastos con `archivo_origen='scraper'` duplicados — misma `(fuente, fecha, monto, descripcion, moneda)` — mantiene el de menor `id` y borra los demás, removiendo también las filas vinculadas en `movimientos_raw`. Los duplicados del run anterior se limpian automáticamente al arrancar v0.3.61.
- **Tip UI**: si querés ver/borrar manualmente registros importados, expandí la sección "Movimientos guardados" en la tab del banco — muestra todos los estados (`new`, `unmatched`, `matched`, `imported`, `ignored`) con un botón ✕ que borra el raw y el gasto vinculado.

## 0.3.60

- **Session TTL — descartar sesión guardada si supera N segundos (BBVA: 240s)**: BBVA cierra la sesión por inactividad a los 5 minutos.  Como el scraper típicamente corre una vez al día, la sesión guardada del run anterior está siempre vencida y reusarla genera más problemas que beneficios (caía en `desconexion.html` por cookies stale).  Nuevo atributo de clase opcional `session_ttl_seconds` en `BaseScraper`: si la sesión guardada en disco es más vieja que ese TTL, `_has_session()` devuelve False sin intentar restaurarla, y el flujo va directo a `do_login`.  `BbvaScraper.session_ttl_seconds = 240` (4 min, 1 min de margen).  Otros scrapers (Amex/Galicia/etc.) siguen sin TTL — comportamiento previo intacto.  Beneficio adicional: sesiones reusadas correctamente cuando un run ocurre dentro de los 4 min (ej. al testear localmente).

## 0.3.59

- **Fix BBVA login — limpiar cookies stale antes del login**: cuando hay una sesión guardada en disco que ya venció, el flujo es: `_restore_session` (cookies cargadas al browser) → `check_session` (falla porque caducaron) → `do_login`. Pero las cookies stale siguen vivas en el browser al iniciar el login. Al cargar `/login/index.html` con esas cookies, BBVA detecta la sesión vencida y redirige a `https://www.bbva.com.ar/desconexion.html` (página de "sesión cerrada") en vez de mostrar el formulario de login. Síntoma: tras submit, URL inesperada `desconexion.html?` y login falla. Solución: al inicio de `do_login`, navegamos al dominio BBVA y llamamos `driver.delete_all_cookies()` antes de cargar el formulario, garantizando un estado limpio. Además, se reconoce la URL `desconexion`/`logout` post-submit con un mensaje de error explícito (sugiriendo reintentar en unos minutos si vuelve a pasar por sospecha de Akamai).

## 0.3.58

- **Fix BBVA login — esperar `/fnetcore/` específicamente, no sólo "no /login/"**: la condición de espera tras el submit (`"/login/" not in url`) salía prematuramente cuando el browser llegaba a `https://online.bbva.com.ar/fnetcore/loginClementeApp2.html` — esa URL no contiene `/login/` (con slashes) pero es un paso intermedio, no el destino final. Síntoma: `datosperfil HTTP 0 ... fetch error: TypeError: Failed to fetch` porque la página intermedia se atascaba y el browser no podía ejecutar fetch desde ese contexto. Solución: nueva condición `_is_logged_in` que requiere `/fnetcore/` Y `loginClementeApp2` NO presentes. Tope subido de 30 s a 45 s para dar tiempo al JS de BBVA a completar la cadena postlogin→redirect. Si tras el timeout seguimos atascados en `loginClementeApp2.html`, navegamos manualmente a `/fnetcore/` (las cookies de sesión ya están establecidas si postlogin corrió) y proseguimos con `datosperfil`. Si seguimos en `/login/` tras timeout → credenciales inválidas (error explícito).

## 0.3.57

- **Fix scheduler — conciliar y auto-importar por la `fuente` real de cada movimiento, no por el `banco`**: el scraper de BBVA se identifica como `banco="bbva"` pero los movimientos que emite tienen `fuente="bbva_cuenta"` (porque van a la cuenta corriente, no a una tarjeta). El scheduler ejecutaba `run_conciliation(fuente="bbva")` y `auto_import_unmatched("bbva")` — esos filtros no encontraban las filas en `movimientos_raw` (que tienen `fuente="bbva_cuenta"`), así que se quedaban indefinidamente con `estado="new"` sin moverse a la tabla `gastos`. Síntoma reportado: login OK, scraper devuelve N movimientos, pero la tabla de gastos no se actualiza. Solución: tras `insert_movimientos_raw`, extraemos el set de `fuentes` distintas presentes en los dicts insertados y corremos conciliación + auto-importación por cada una. Esto generaliza también a futuros scrapers de BBVA Visa / BBVA Mastercard (mismo `banco="bbva"`, distintas `fuente`). Se aplica al path scheduled (`_run_one`) y al manual (`run_scraper_now`). Las filas previamente "atascadas" en `movimientos_raw` con estado='new' se procesarán en el próximo run.

## 0.3.56

- **Log del addon con fecha y hora**: uvicorn ahora usa `log_config.json` con formato `YYYY-MM-DD HH:MM:SS` en cada línea del log del addon de HA. Antes no había timestamp y era imposible saber a qué hora había ocurrido cada evento.
- **UI Scrapers: mostrar último intento, último OK y próximo run del scheduler**: la card de cada scraper ahora muestra "▶ Último intento" (cuándo arrancó el último run, exitoso o no), "✓ Último OK" (cuándo terminó bien por última vez) y "⏱ Próximo run" (cuándo lo tiene programado el scheduler). Si el banco no está en el scheduler se muestra "⚠ No programado". Esto permite diagnosticar sin tener que ir a los logs del addon.

## 0.3.55

- **Rewrite BBVA login — interacción natural con el formulario en lugar de API directa**: las versiones 0.3.40-0.3.53 intentaron hacer el login bypassando Akamai con llamadas API directas vía `fetch()` desde el browser (prelogin → loginClementeApp2.html → postlogin → obtenerTsec). Eso requería: generar sessionIdLN client-side, navegar a URLs con tokens de 350+ chars que crasheaban el renderer, manejar XSRF tokens diferentes pre/post auth, esquivar el statusCode:500 que devolvía BBVA cuando el contexto Akamai no estaba "fresco", y todo eso falla intermitentemente porque Akamai detecta el patrón. **Solución simplificada**: dejamos que el browser real haga TODO el flujo. (1) Cargamos `login/index.html`, (2) esperamos cookies Akamai+Adobe, (3) llenamos los 3 inputs (`input[type='number']` DNI, `input[name='username']` alias, `input[name='password']` clave) con `_type_input()` (ActionChains, soporta web components Lit/Spherica), (4) clickeamos submit con `_click_element()`, (5) `WebDriverWait` hasta que la URL deje de tener `/login/` (hasta 30s — el browser hace toda la cadena prelogin → loginClementeApp2 → postlogin → /fnetcore/ por sí solo), (6) verificamos con `datosperfil` que la sesión esté establecida. Se elimina código muerto: `_fetch_url`, `_make_session_id_ln`, parámetro `with_xsrf` ya no se usan en login (sólo `_api_request` con XSRF auto-incluído desde cookie sigue siendo necesario para los endpoints REST post-login que sí lo requieren). El `do_login` pasa de ~190 líneas a ~80.

## 0.3.54

- **Fix navbar sticky + alineación del toast**: la navbar superior no era `sticky`, así que al hacer scroll se iba con la página. El toast (`position: fixed; top: 52px`) asumía que la navbar seguía en su lugar, por lo que aparecía colgando 52px debajo del tope del viewport con un hueco vacío arriba. Se fija la navbar con `position: sticky; top: 0; z-index: 400` para que siempre esté visible, y en mobile el toast pasa a `top: 46px` para alinearse con la navbar de 46px de alto.

## 0.3.53

- **Fix ícono del addon en la lista de addons de HA**: HA usa `icon.png` (128×128) para la lista y `logo.png` para la página de detalles. El addon solo tenía `logo.png`; se agrega `icon.png` generado a partir de `icono-sb.png`.
- **Fix BBVA login — navegación a loginClementeApp2.html con URL completa vía `window.location.href`**: en 0.3.50/0.3.51 navegábamos a la URL base sin el token de authentication, pero el servidor BBVA puede necesitar ver ese token para registrar internamente la sesión antes de aceptar el postlogin. Se cambia a usar `driver.execute_script("window.location.href = ...", url_completa)` que evita el crash del renderer que causaba `driver.get()` con URLs largas. Fallback a URL base si la navegación JS falla. Se genera `sessionIdLN` antes de construir la URL (para embeber el mismo ID en la URL y en el payload de postlogin).

## 0.3.52

- **UI: toggle de tamaño del gráfico mensual en la página principal**: botón ▾/▸/▴ en el título del gráfico "Movimientos ARS — mes a mes" que cicla entre normal, compacto (mitad de altura) y oculto. El estado se persiste en `localStorage` (clave `chart_home_mode` dentro de `ui_prefs`) y se restaura al recargar la página. También disponible como selector en la tab Interfaz → Preferencias para mayor comodidad.

## 0.3.51

- **Fix BBVA login — navegación a loginClementeApp2.html con URL completa vía JS**: en 0.3.50 navegábamos a la URL base (sin el token de authentication) para refrescar Akamai. Pero el servidor BBVA puede requerir el token de authentication en la URL para registrar la sesión server-side antes de aceptar el postlogin. Se cambia la navegación a usar `window.location.href = url_completa` (JS, no `driver.get`) con el token de authentication completo + sessionIdLN embebidos. `window.location.href` puede manejar URLs largas con `==SLASH==` más robustamente que el comando WebDriver `get`. Fallback: si la navegación JS falla, navega a la URL base. Se genera `sessionIdLN` antes de construir la URL (para poder ponerlo en la URL y usarlo en postlogin).

## 0.3.50

- **Fix BBVA postlogin statusCode:500 — navegar a loginClementeApp2.html (sin query string) para refrescar Akamai**: postlogin devolvía HTTP 200 con `statusCode:500 "Esta transacción no puede ser realizada"` porque era llamado desde el contexto de `login/index.html` — el mismo contexto de prelogin. El servidor BBVA (o Akamai) espera que postlogin venga de `loginClementeApp2.html` (que es la página a la que navega el browser real entre prelogin y postlogin). Dos efectos de esa navegación: (1) el `_abck` de Akamai se actualiza con los datos del sensor de esa nueva página; (2) el header `Referer` del fetch de postlogin apunta a `loginClementeApp2.html`. Solución: antes de generar el sessionIdLN y llamar postlogin, navegamos a `https://online.bbva.com.ar/fnetcore/loginClementeApp2.html` **sin** query string (URL corta, sin el token de authentication de 350+ chars que crasheaba el renderer headless). Esperamos hasta 12 s a que `_abck` sea actualizado (largo > 100 chars), luego llamamos postlogin desde ese contexto.

## 0.3.49

- **Fix Akamai fingerprint detection — parches CDP para ocultar automatización**: Akamai BotManager verifica múltiples propiedades del browser que difieren entre headless y un browser real. Se agregan overrides inyectados via `Page.addScriptToEvaluateOnNewDocument` (CDP) antes de que cargue cualquier página: (1) `navigator.webdriver → undefined` (refuerzo adicional al flag `--disable-blink-features`); (2) `window.chrome` mockeado con `runtime`, `loadTimes`, `csi`, `app` (ausente en headless); (3) `navigator.plugins` con 3 plugins falsos (headless tiene 0); (4) `Notification.permission → 'default'` (headless devuelve 'denied'); (5) `navigator.languages → ['es-AR','es','en-US','en']`; (6) `navigator.platform → 'Win32'`. Se cambia el User-Agent de `X11; Linux aarch64` a `Windows NT 10.0; Win64; x64` (más plausible para un usuario de homebanking argentino). Los parches se aplican en `BaseScraper._create_driver()` (add-on) y en `test_bbva_login.py` (local). Se agrega log del largo del `_abck` cookie para diagnóstico.

## 0.3.48

- **Fix BBVA login — X-XSRF-TOKEN no debe enviarse en prelogin ni postlogin**: en 0.3.47 el helper `_api_request` fue actualizado para incluir automáticamente la cookie `XSRF-TOKEN` como header `X-XSRF-TOKEN` en todas las requests (replicando el comportamiento de Angular `$http`). Esto rompía el `postlogin`: BBVA devolvía HTTP 200 con `statusCode:500 "Esta transacción no puede ser realizada"`. La causa: el `XSRF-TOKEN` del browser antes de autenticarse es el token de la sesión anónima (pre-login), no de la sesión autenticada; enviarlo en `postlogin` invalida el request. Solución: nuevo parámetro `with_xsrf=False` en `_api_request` para `prelogin` y `postlogin`; todas las demás calls (post-auth) siguen enviando el header. Se agrega también validación del `statusCode` en el body de la response de `postlogin` (BBVA usa HTTP 200 incluso cuando falla a nivel aplicación). Se mejora la espera de Akamai: en lugar de `time.sleep(6)` fijo, se espera hasta 15 s en pasos de 1 s verificando que las cookies `_abck` y `s_visit` (Adobe Analytics) estén presentes, lo que indica que los scripts de fingerprinting terminaron.

## 0.3.47

- **Fix BBVA login — postlogin directo sin navegar a loginClementeApp2.html**: en 0.3.46 navegábamos Selenium a `loginClementeApp2.html?{authentication}=...` para que el JS de BBVA generara el `sessionIdLN` y llamara a `postlogin`. Esa URL larga (~350 chars con el token `authentication` que contiene `==SLASH==`, `+` y `=`) crashea el tab del renderer de Chromium headless en Alpine. Solución: generamos `sessionIdLN` directamente en Python con `secrets.choice` sobre `[a-z0-9]` (128 caracteres, idéntico al patrón observado en el HAR), y llamamos `POST /login/postlogin` vía `_api_request` (fetch en el browser) con `{ documento, usuario:"", claveDigital:"", numeroClienteAltamira, sessionIdLN }`. Se elimina la navegación a `loginClementeApp2.html` por completo. Resultado: login en dos pasos API puros sin ninguna navegación de página tras la carga inicial de `login/index.html`.

## 0.3.46

- **Fix BBVA login — postlogin delegado al browser via navigation**: la response real de `prelogin` (confirmada con el nuevo HAR y log de producción) trae `{loginOk, authentication, numeroClienteAltamira, codigoTipoIngreso, marcaTipoUsuario}` — NO trae `sessionIdLN`. Ese token (~128 chars lowercase) lo genera el JS del frontend al navegar a `loginClementeApp2.html`, antes de hacer `postlogin`. En lugar de tratar de reconstruir esa lógica client-side, ahora navegamos Selenium directamente a `https://online.bbva.com.ar/fnetcore/loginClementeApp2.html?{authentication}=/std/{numeroCliente}/0/{dni}/` y dejamos que el JS de BBVA arme el sessionIdLN y haga el POST a `/login/postlogin` por nosotros. Esperamos 10 s y verificamos con `datosperfil`. Se valida también que `prelogin` devuelva `loginOk:true` antes de continuar (caso credenciales inválidas).

## 0.3.45

- **Fix BBVA — todas las requests API ahora se hacen desde el browser real (fetch + execute_async_script)**: en 0.3.44 las llamadas a `/login/prelogin` se hacían con httpx, lo que daba HTTP 403 con HTML de Akamai porque Akamai Bot Manager hace fingerprinting del cliente HTTP (TLS handshake, ciphersuites, JA3, orden de headers) y rechaza cualquier cosa que no sea el mismo Chrome que generó las cookies anti-bot. Solución: nuevo helper `_api_request(driver, path, method, json_body)` que ejecuta `fetch()` adentro de Chrome vía `driver.execute_async_script()` y devuelve `{status, body, json}`. Como el fetch corre en el browser real con sus cookies y fingerprint válidos, Akamai lo deja pasar. Refactor completo: `check_session`, `do_login` (prelogin + postlogin + datosperfil), `scrape` (cuentas) y `_fetch_movimientos` (paginación) todos usan `_api_request`. Se eliminan `_HEADERS`, `_make_client` y la dependencia de `httpx` en este scraper.

## 0.3.44

- **Rewrite BBVA login — API directa en lugar de interacción con formulario HTML**: análisis completo del HAR reveló que el login real de BBVA es una secuencia de dos llamadas API: `POST /login/prelogin` (con DNI, usuario, claveDigital y tipoDocumento estructurado) → parse del redirect URL con `sessionIdLN` y `numeroClienteAltamira` → `POST /login/postlogin` (con esos tokens) → cookies de sesión definitivas. El formulario HTML con web components Lit/Spherica es solo UI; la acción real ocurre en la API. Selenium ahora solo sirve para que Akamai Bot Manager inicialice sus cookies anti-bot (indispensables para que la API acepte requests). `_dump_page_state`, `_type_input`, `_click_element` se conservan pero ya no se usan en el flujo de login. Se agrega `_extract_version_front()` que busca `versionFront` en el HTML de la página y cae al valor conocido del HAR (`20260325.1526`) si no lo encuentra. Todo el flujo prelogin → postlogin → datosperfil ahora va por httpx con logging detallado de cada paso (HTTP status + body) visible en el log del add-on.

## 0.3.43

- **Fix BBVA login — múltiples correcciones post-interacción**: (1) `_type_input()` estrategia 1 ahora usa `ActionChains.click(el).send_keys(val).perform()` en cadena en lugar de `element.send_keys()` separado — para Lit/Shadow DOM la diferencia es crítica: ActionChains manda keystrokes al elemento ENFOCADO en el browser, no al WebElement directamente, lo que evita que el componente ignore los valores. (2) `Origin`/`Referer` en `_HEADERS` corregidos de `www.bbva.com.ar` a `online.bbva.com.ar` (dominio real del homebanking) — el servidor podría rechazar llamadas API con origen incorrecto. (3) Se elimina `button[type='submit']` del selector de `btn_cont` para evitar que se dispare el submit final antes de llenar usuario y contraseña. (4) Diagnósticos post-submit mejorados: la URL actual, la lista de nombres de cookies y el HTTP status de `datosperfil` ahora aparecen en el log del panel (no solo en el log del sistema); si seguimos en la página de login tras el submit se lanza error descriptivo inmediatamente.

## 0.3.42

- **Fix BBVA login — botón Submit no interactuable en web components**: el mismo problema de `ElementNotInteractableException` que afectaba a los campos de texto ahora se presentaba en el botón submit (y en el botón "Continuar"). Se agrega el helper `_click_element()` con dos estrategias: (1) ActionChains con scroll + move + click; (2) `element.click()` vía JS como fallback. Los dos botones del flujo de login (`btn_cont` y `submit_el`) ahora usan `_click_element()` en lugar de `.click()` directo.

## 0.3.41

- **Fix BBVA login — "element not interactable" en web components**: los `<input>` del formulario de BBVA están dentro de web components Lit/Spherica (`@bbva/webcomponents`); en modo headless Chromium el `send_keys()` directo falla con `ElementNotInteractableException`. Se agrega el helper `_type_input()` con tres estrategias progresivas: (1) `ActionChains` con scroll + move + click antes del `send_keys`; (2) setter nativo de `HTMLInputElement.prototype.value` vía JS + dispatch de eventos `input`/`change`/`blur` con `bubbles:true` para que el framework detecte el cambio; (3) asignación directa de `element.value` como último recurso. Los tres campos del formulario (DNI, usuario, contraseña) usan `_type_input()` y ya no llaman a `.clear()` previamente (que también fallaba por el mismo motivo).

## 0.3.40

- **Fix BBVA login — URL correcta del formulario**: el scraper navegaba a `www.bbva.com.ar/personas/home.html` (página pública) pero el formulario de homebanking está en `https://online.bbva.com.ar/fnetcore/login/index.html`. Causa raíz confirmada por análisis del HAR del login completo. Se corrige `_LOGIN_URL` y `login_origin` al dominio `online.bbva.com.ar`. Los selectores `input#documentNumberInput`, `input#username` e `input[type='password']` quedan confirmados por la telemetría del HAR. El POST de login va a `/fnetcore/servicios/login/prelogin` con `claveDigital`; Akamai Bot Manager corre en background vía JS y Selenium lo maneja transparentemente.

## 0.3.39

- **Fix BBVA login — detección de iframe y diagnóstico**: `input#documentNumberInput` no se encontraba porque el formulario de login de BBVA está dentro de un iframe (patrón habitual en SPAs). Se agrega `_find_across_frames()` que prueba el frame principal y luego cada iframe del DOM, dejando el contexto enfocado en el iframe correcto para las interacciones siguientes. Se agregan logs de diagnóstico (`[bbva-diag]`) que emiten título, URL, todos los inputs (id/type/name/placeholder) e iframes encontrados — visibles en Supervisión → Add-ons → Gastos → Log. El wait inicial se extiende a 6 s para dar tiempo al lazy-loading de React. Se agregan listas de selectores con fallbacks para DNI, usuario y contraseña.

## 0.3.38

- **Scraper BBVA — implementación inicial de cuenta corriente/ahorro**: reemplaza el stub anterior con un scraper funcional usando un enfoque híbrido Selenium + httpx. Selenium realiza el login en la SPA (micro-frontend React); httpx hace todas las llamadas a la API REST (`https://online.bbva.com.ar/fnetcore/servicios/`) usando las cookies de sesión generadas por el login. Los movimientos se obtienen paginados de `/cliente/productos/cuentas/movimientos` (10 por página) dentro del rango de fechas configurado. El signo de cada movimiento (ingreso/egreso) se deduce comparando el saldo consecutivo en el array newest-first que devuelve la API.
- **Config BBVA — campos corregidos y ampliados**: `usuario` ahora está etiquetado como "Número de DNI", `tercer_dato` como "Usuario BBVA" (antes decía incorrectamente "dato estático de seguridad / apellido materno"), y se agrega campo opcional `dias` (días hacia atrás a consultar, default 60) igual que MercadoPago.

## 0.3.37

- **Fix scraper MP — pagos recientes no aparecían**: el filtro `status=approved` en la API excluía pagos con tarjeta prepaga que aún están en estado `in_process` o `pending` (el ciclo de aprobación puede tardar minutos/horas después de la transacción). Ahora se consulta sin filtro de status y se descartan en código solo los que definitivamente no ocurrieron: `rejected`, `cancelled`, `charged_back`, `refunded`. El log del run muestra cuántos se omitieron por cada motivo.
- **Debug MP — status en cada línea**: el log de debug ahora incluye `status=` para cada pago, lo que permite identificar fácilmente pagos en tránsito vs aprobados.
- **raw_data MP — campo `status`**: se guarda el status del pago (`approved`, `in_process`, etc.) en `raw_data` para referencia futura.

## 0.3.36

- **Fix scraper MP — fecha incorrecta para pagos con tarjeta prepaga**: el scraper usaba `date_approved` (fecha de liquidación) como fecha del movimiento. Para tarjetas prepaga (y otras con ciclo T+1), la liquidación ocurre al día siguiente de la transacción, desplazando la fecha un día. Ahora se usa `date_created` (momento de la transacción, igual a lo que muestra la app de MP), con `date_approved` como fallback si `date_created` no estuviera disponible.

## 0.3.35

- **Scraper MP — reglas de descripción explícitas**: `_build_description_base` ahora aplica reglas fijas antes de la lógica genérica: (1) `partition_transfer` → "Transferencia desde Reserva" (ingreso) o "Transferencia hacia Reserva" (egreso); (2) `account_money + money_transfer` → "Transferencia: {reason}" (ej. "Transferencia: Varios"); (3) `account_money + regular_payment` → `reason` directo (ej. "Merpago*grupolarg", "Express av dorrego 851"). El resto sigue con la lógica genérica (poi_name → merchant → reason → stmt_desc → op_label).

## 0.3.34

- **Fix scraper MP — `partition_transfer` signo incorrecto**: MP devuelve este tipo de pago en ambas queries (`payer.id` Y `collector.id`) con el mismo `user_id` en ambos lados. La query de `payer.id` lo capturaba primero como egreso (+), y la de `collector.id` lo saltaba por deduplicación. Ahora se salta en la query de payer (sign=+1) y se captura únicamente en la de collector (sign=−1), resultando en ingreso correcto. Confirmado con el caso "Dinero retirado de Guita" ($101.887,54).
- **Debug MP — payer_id y collector_id en log**: el log de debug ahora muestra `payer=` y `coll=` en cada línea para facilitar diagnóstico futuro de pagos con signo ambiguo. Nuevo tag `DEFER-PT` para partition_transfers diferidos.

## 0.3.33

- **Fix debug log MP — salida real en el run log**: `logger.debug()` no aparece en el log del add-on de HA porque el handler raíz filtra en INFO. Se corrigió para usar `log_fn()` cuando `debug=True`, así los mensajes `[dbg] NUEVO/YA-EXISTE/OMITIDO-CC/SIN-DATOS` aparecen en el log del run (visible en el panel de scraper y en Supervisión → Add-ons → Gastos → Log). Se elimina el `logger.setLevel(DEBUG)` que no tenía efecto.

## 0.3.32

- **Config scraper — soporte de campos checkbox**: el formulario de configuración de scrapers ahora renderiza campos de tipo `checkbox` (tilde). El valor se guarda como booleano y se envía correctamente al backend.
- **Config MP — tilde "Log de debug"**: nuevo campo opcional en la config de MercadoPago. Si está tildado, activa el nivel `DEBUG` del logger del módulo durante ese run. Los mensajes por pago (`NUEVO`, `YA-EXISTE`, `OMITIDO-CC`, `SIN-DATOS`) aparecen en Supervisión → Add-ons → Gastos → Log. Se puede tildar puntualmente para diagnosticar y destildar después.

## 0.3.31

- **Scraper MP — rango de fechas en zona Argentina**: el período consultado ahora se calcula en UTC-3 fijo (sin DST). `dias=1` trae solo el día de hoy desde las 00:00 ART; `dias=2` agrega ayer; y así sucesivamente. Antes se usaba UTC, lo que podía dejar fuera transacciones de las últimas horas del día local.
- **Scraper MP — descripciones más ricas**: `_build_description_base` recibe el signo de la transacción. Para ingresos (`sign=-1`) se antepone el nombre del pagador (`payer.first_name + last_name`). Se agrega `statement_descriptor` como fallback antes de "MercadoPago". Los títulos de ítems que son códigos técnicos (`_TECHNICAL_CODES`) se filtran para no aparecer como nombre de comercio.
- **Scraper MP — nuevas etiquetas de operación**: `money_outflows` → "Transferencia saliente", `money_release` → "Liberación de fondos", `partition_transfer` → "Transferencia interna". Se agrega `payer_name` y `statement_descriptor` a `raw_data`.
- **Scraper MP — debug logging por pago**: se registra a nivel `DEBUG` cada pago procesado con su `id`, `payment_type_id`, `operation_type`, `amount` y `reason` (30 chars), junto al resultado: `NUEVO`, `YA-EXISTE`, `OMITIDO-CC` o `SIN-DATOS`. Activar debug en HA (`logger.default: debug`) permite auditar exactamente qué trae la API.
- **UI subtítulos**: se agregan traducciones para `money_outflows`, `money_release` y `partition_transfer` en los subtítulos del panel de scraper.
- **Config MP — hint de `dias`**: se clarifica el significado (`1 = solo hoy, 2 = hoy y ayer, N = últimos N días`).

## 0.3.30

- **`delete_movimiento_raw` — hard delete para MP en un solo click**: las entradas de MercadoPago se borran completamente con un solo ✕ (el gasto vinculado también se elimina si existe). No se crea sentinel `ignored` porque MP ya deduplica vía `payment_id` en `_get_existing_payment_ids`. Esto rompe el ciclo confuso de "✕ → ignored → ✕ de nuevo" que se necesitaba antes. El scraper reimporta en el próximo run; AMEX/BBVA/Galicia siguen con soft-delete para mantener su sentinel.
- **Panel scraper — subtitle con tipo de pago**: bajo la descripción de cada fila se muestra una línea pequeña con `payment_type_id` traducido (Billetera, Débito, etc.), `operation_type` traducido y `payment_id`. Permite ver de qué tipo es cada movimiento sin abrir la DB.
- **Tooltips del ✕ diferenciados**: el tooltip del botón ✕ indica explícitamente si el borrado permitirá o impedirá la reimportación (comportamiento diferente para MP vs otros scrapers).

## 0.3.29

- **Panel scraper — mostrar entradas `ignored`**: los registros con estado `ignored` (sentinels anti-reimport) ahora se muestran en el panel, con opacidad reducida y descripción tachada para distinguirlos de los activos.
- **Panel scraper — hard delete de `ignored`**: al presionar ✕ sobre un registro `ignored`, se borra completamente de la DB (ya no queda sentinel). El confirm advierte que el scraper podrá volver a importarlo. Permite limpiar manualmente entradas viejas o incorrectas.
- **`delete_movimiento_raw`: hard delete si ya es `ignored`**: si el estado actual es `ignored`, la función borra la fila directamente (el usuario está eliminando el sentinel a propósito).

## 0.3.28

- **Scraper MP — excluir pagos con tarjeta de crédito**: los pagos con `payment_type_id == "credit_card"` se omiten completamente. Esos cargos ya figuran en el resumen de la tarjeta (AMEX, BBVA, etc.) y se importan vía PDF; traerlos también desde MP generaría duplicados. El log del run muestra cuántos se omitieron por este motivo. Se elimina el código de split de cuotas agregado en 0.3.26 (ya no es necesario).

## 0.3.27

- **Scraper MP — descripción `checkout_on`**: el campo `reason` de la API de MP devuelve códigos técnicos sin espacios (ej. `checkout_on`, `regular_payment`) que se filtraban por la lógica de prioridad y aparecían como nombre de la transacción. Ahora si `reason` no contiene espacios se descarta como código técnico y se usa `op_label` en su lugar. Se agrega `"checkout_on"` al dict de etiquetas → muestra `"Compra online"`.
- **Panel de scraper — sort por `scraped_at DESC`**: la lista de registros ahora se ordena por cuándo fueron escaneados (más reciente primero) en lugar de por fecha de transacción. Así las entradas del último run siempre aparecen al tope, incluyendo cuotas con fechas futuras.
- **Panel de scraper — indicador "Nuevo" y timestamp**: cada fila ahora muestra un punto azul `●` si es del último run del scraper, y la fecha de escaneo como sublínea bajo la fecha de transacción (ej. `5min`, `10:30`, `26/05`).

## 0.3.26

- **Scraper MP — Q2: campo "Usuario"**: se agrega el campo opcional `usuario` a la configuración del scraper MercadoPago. El nombre configurado se guarda en `raw_data["usuario"]` de cada movimiento; al importar a `gastos` vía "Importar pendientes", `importar_a_gastos` lo extrae y lo inserta en la columna `gastos.usuario`. Permite distinguir de quién son los pagos de MP cuando hay más de un titular en el sistema.
- **Scraper MP — Q3: descripción más rica**: `_build_description_base` ahora prioriza `point_of_interaction.business_info.sub_unit` / `.unit` (nombre del comercio en pagos QR/POS) por sobre `additional_info.items[0].title`. También se guardan más campos en `raw_data`: `payment_type_id`, `collector_id`, `poi_type` y `poi_name` (nombre del comercio QR cuando está disponible).
- **Scraper MP — Q4: cuotas de tarjeta divididas en N entradas**: cuando `payment_type_id == "credit_card"` e `installments > 1`, el pago se divide en N `MovimientoRaw` individuales (una por cuota mensual). Cada cuota tiene `monto = total/N`, `fecha` desplazada un mes por cuota, y descripción `"COMERCIO i/N"` (ej. `"Frávega 2/6"`). Esto permite que la conciliación cruce cada cuota contra la línea correspondiente del resumen de tarjeta. La deduplicación usa sub-IDs `"{payment_id}_c{i}"` para detectar cuotas ya importadas en runs anteriores.

## 0.3.25

- **Borrado de /quick: hard delete, no sentinel**: al borrar un gasto ingresado con el formulario rápido (`raw_data.manual_quick = true`), tanto el raw como el gasto se eliminan completamente de la DB. No tiene sentido guardar un sentinel para algo que el usuario ingresó a mano. Si el scraper encuentra la misma transacción real en la API, la importa normalmente (comportamiento correcto). Solo los raws del scraper (no manuales) conservan el comportamiento de soft delete (`'ignored'`).

## 0.3.24

- **Fix — ✕ en card de scraper ahora previene reimport**: `delete_movimiento_raw` ya no borra la fila; la marca como `'ignored'` (y sí borra el gasto vinculado si estaba importado). El sentinel `'ignored'` es detectado por la conciliación y por `_get_existing_payment_ids` → el scraper no vuelve a importar esa transacción.
- **UI: raws `'ignored'` no se muestran en el panel de registros**: se filtran en el frontend antes de renderizar. Para el usuario son "borrados"; en la DB persisten como sentinel.
- **Confirm dialog actualizado**: el mensaje ahora dice "Ignorar este registro" y aclara que el scraper no lo volverá a importar.

## 0.3.23

- **Fix — gastos borrados no vuelven en el próximo run del scraper**: al borrar un gasto desde la UI, `delete_movimiento_manual` ahora marca el `movimiento_raw` vinculado como `'ignored'`. Esto aplica a todos los scrapers (AMEX, MP, etc.).
- **Conciliación: fallback para entradas /quick borradas (sin payment_id)**: si un nuevo raw no tiene candidatos en `gastos`, `_conciliar_uno` busca un raw `'ignored'` con mismas características (fuente+moneda+monto±0.02+fecha±5d). Si lo encuentra, el nuevo raw también se marca `'ignored'`. Evita que transacciones cargadas con /quick, borradas, y luego traídas por el scraper API vuelvan a aparecer.
- **Scraper MP: `_get_existing_payment_ids` incluye raws `'ignored'`**: los payment_ids de entradas ignoradas también se consideran "ya vistos" para no reinsertar por esa vía.

## 0.3.22

- **Scraper MercadoPago reescrito: Selenium → API REST**: ya no requiere usuario/contraseña ni browser. Usa el Access Token personal de la cuenta (`mercadopago.com.ar/developers/panel → Credenciales de producción`). Consulta `/v1/payments/search` como payer (egresos) y como collector (ingresos) con paginación, y `/v1/account/balance` para el saldo. Deduplicación por `payment_id` en `raw_data` para evitar reinsertar pagos ya conocidos en runs consecutivos.
- **Credenciales MP**: se reemplazan los campos `usuario`/`password` por `access_token` (tipo password, enmascarado en UI) y `dias` opcional (default 60).
- **Descripción de pagos MP**: prioriza nombre del comercio de `additional_info.items`, luego `reason`/`description`, luego etiqueta del `operation_type`. Si la compra fue en cuotas, agrega `(N cuotas)` al final.

## 0.3.21

- **Conciliación: `_normalize()` ya no elimina el número de cuota (N/M)**: ahora que el tie-breaker en `_score()` hace imposible el match entre cuotas distintas, eliminar `3/12` de la descripción antes de comparar sólo restaba precisión. Con el N/M preservado, `TIENDA 3/12` vs `TIENDA 3/12` obtiene mayor similitud que `TIENDA 3/12` vs `TIENDA` (PDF sin cuota explícita).

## 0.3.20

- **Cuotas: guardar N/M en raw_data (AMEX scraper)**: `_parse_row` detecta el patrón `N/M` (ej. `3/12`) en la descripción y lo guarda en `raw_data["cuota"]`. Disponible para la UI y para futuras reglas.
- **Cuotas: tie-breaker en conciliación**: `_score()` en `conciliacion.py` ahora retorna `0.0` si raw y candidato tienen distinto número de cuota — evita que `TIENDA 3/12` matchee con `TIENDA 1/12` (mismo monto, misma desc base, pero distinta cuota).
- **Cuotas: tie-breaker en dedup PDF upload**: `consolidate_scraper_duplicates()` aplica el mismo chequeo antes del SequenceMatcher.

## 0.3.19

- **Deduplicación scraper → PDF (AMEX / BBVA)**: cuando se sube un PDF de una fuente que también tiene scraper activo (`amex`, `bbva_mc`, `bbva_visa`), el upload detecta y elimina automáticamente los gastos duplicados que el scraper había auto-importado del mismo período. El PDF es la fuente de verdad: el gasto del scraper se borra, el `movimiento_raw` pasa a `matched` apuntando al gasto del PDF. Matching por fuente+moneda, monto±0.02, fecha±5 días y descripción >60% similar. Si se eliminaron duplicados, la respuesta incluye `scraper_duplicados_eliminados`.
- **Nota Galicia**: documentado en código que `_scrape_mastercard` debe usar `fuente="galicia_mc"` (no `"galicia"`) para que la conciliación matchee contra PDFs de Galicia cuando se implemente.

## 0.3.18

- **Bump de versión**: 0.3.17 ya estaba tomado por otra sesión concurrente; se sube a 0.3.18 para evitar conflicto de instalación en HA.

## 0.3.17

- **Categorías especiales ocultas en formulario rápido**: los chiclets de categoría ya no muestran las categorías marcadas como especiales (Transferencia, Transferencia Intercuentas, y las marcadas con `especial: true` en rules.yaml). Se consulta `/api/categorias/especiales` en paralelo y se filtra antes de renderizar.
- **Fix — 500 "type 'coroutine' is not supported" al ejecutar scraper**: `categorize()` es `async def` (llama LLMs vía httpx) y se llamaba sin `await` en tres lugares síncronos, pasando un objeto coroutine a SQLite como parámetro. Corregido reemplazando todas las llamadas por `categorize_by_rules()` (sync) en `scrapers_db.auto_import_unmatched`, `routes/scrapers.importar_pendiente` y `routes/scrapers.crear_movimiento_rapido`.

## 0.3.16

- **Botón guardar integrado al campo monto**: el botón "Guardar gasto" se reemplazó por un botón cuadrado con tilde (✓) a la derecha del campo de monto. Elimina la necesidad de scrollear para guardar; mientras procesa muestra "…" y se deshabilita.

## 0.3.15

- **Selector de categoría tipo chiclets en formulario rápido**: reemplaza el `<select>` por una grilla de 2 columnas con botones tipo píldora. Tocar un chip lo selecciona (fondo oscuro); tocarlo de nuevo lo deselecciona. Si no se elige ninguno, el autocategorizador aplica reglas según la descripción ingresada.
- **Fix — "Importar pendientes" daba "string did not match pattern"**: la función `_auto_import_unmatched` vivía en `scraper_scheduler.py` y al importarla desde el route handler causaba un error de validación de ruta. Se movió a `scrapers_db.py` como `auto_import_unmatched` (función pública) y se renombró el endpoint de `/import-unmatched` a `/importar-pendientes` para evitar ambigüedades con el path parser de Starlette.

## 0.3.14

- **Auto-import de scraper a Gastos**: tras cada run (diario o manual), los movimientos que no matchean con ningún PDF (`unmatched`) se importan automáticamente a la tabla `gastos`. El toast del "Ejecutar ahora" muestra cuántos fueron scrapeados y cuántos importados.
- **Nuevo botón "⬆ Importar pendientes"** en la card de scraper: importa de una sola vez todos los `unmatched` existentes (útil para lotes anteriores al auto-import).
- **Nuevo endpoint `POST /api/scrapers/{banco}/import-unmatched`**: llama a `_auto_import_unmatched` con categorización automática.
- **`_auto_import_unmatched(banco)`**: función reutilizada por el scheduler diario, el trigger manual y el botón de la UI.

## 0.3.13

- **Fix — botón borrar en gastos del formulario rápido (2do intento)**: `COALESCE(c.tipo, CASE...)` retornaba `'auto'` cuando la fuente (ej. `mercadopago`) ya tenía fila en `cuentas` con `tipo='auto'` no-NULL, sin evaluar el CASE de `archivo_origen`. Corregido invirtiendo el orden: `CASE WHEN archivo_origen='manual' THEN 'manual' ELSE COALESCE(c.tipo,'auto') END` — el check de `archivo_origen` ahora tiene prioridad absoluta.

## 0.3.12

- **Migración automática `quick_form_archivo_origen_v1`**: los gastos cargados con el formulario rápido antes del fix (que quedaron con `archivo_origen='scraper'`) se corrigen automáticamente al iniciar. Se identifican via `movimientos_raw.raw_data LIKE '%manual_quick%'` y se actualiza a `archivo_origen='manual'` para que el botón de borrar aparezca en la UI.
- **Formulario rápido autocontenido**: se eliminaron el link "← Inicio" del header y el botón "Volver a inicio" de la pantalla de éxito. La página queda sin navegación externa, pensada para usarse como ícono standalone desde el home screen.
- **Registros ingresados en la card de scraper**: cada card tiene un panel colapsable "📦 Registros ingresados" con los últimos 100 `movimientos_raw` del banco (fecha, descripción, monto, badge de estado). Carga lazy al abrir, botón ↻ para refrescar.
- **Borrar movimiento_raw desde la UI**: botón ✕ por fila; si el movimiento estaba `imported` también borra el gasto asociado.
- **Botón "Copiar log"**: el panel "Detalle del último run" tiene un botón ⎘ Copiar al portapapeles.
- **Nuevo endpoint `DELETE /api/scrapers/movimientos-raw/{id}`** + **`scrapers_db.delete_movimiento_raw`**: borrado en cascada (raw + gasto si aplica).

## 0.3.11

- **Íconos SVG por banco en el formulario rápido**: cada `/quick?fuente=X` ahora muestra un ícono generado dinámicamente con los colores y siglas del banco (AMEX azul, MercadoPago celeste, BBVA marino, Galicia rojo). El endpoint `/quick-icon/{fuente}.svg` genera el SVG en el servidor; el `/manifest-quick.json` lo referencia para que el ícono correcto aparezca al agregar al inicio de iOS/Android. Fuentes sin ícono dedicado usan el color de acento con los primeros 4 caracteres de la fuente.

## 0.3.10

- **Fix — gastos del formulario rápido ahora se pueden borrar**: los gastos cargados desde `/quick` quedaban con `archivo_origen='scraper'` y `tipo='auto'`, ocultando el botón de borrar. Ahora se insertan con `archivo_origen='manual'`; `list_gastos` los trata como `tipo='manual'` y `delete_gasto_manual` los acepta.
- **Fix — ícono de iOS dice el nombre correcto**: al agregar `/quick?fuente=mercadopago&label=MercadoPago` al inicio de iOS, el ícono ahora dice "MercadoPago" en vez de "Gastos". La página sirve su propio manifest (`/manifest-quick.json`) con `name` y `short_name` iguales al label de la cuenta, en lugar de heredar el manifest principal.
- **Fix AMEX — "Últimos Movimientos" (período abierto) devolvía 0 registros**: el portal redirige a una vista sin `div[id^='txnsCard']`; se agrega fallback que busca `tr.tableStandardText.pagebreak` directamente bajo `div#txnsSection`.
- **Fix AMEX — saldo negativo (`-$132,70`) se parseaba como 0**: la condición `startswith("$")` fallaba con el prefijo `-$`. Se invierte el orden de chequeo (USD primero) y se usa `"$" in line` para ARS.

## 0.3.9

- **Diagnóstico de scrapers en la UI**: cada card de scraper ahora muestra un panel colapsable "Detalle del último run" con las líneas de diagnóstico del scraper. Incluye URL navegada, si se encontraron los elementos esperados, cuántas secciones txnsCard y filas se encontraron y cuántas se parsearon correctamente — facilita detectar por qué un run devuelve 0 movimientos.
- **Logs detallados en AMEX**: `check_session`, `do_login` y `_scrape_producto` ahora emiten logs granulares (URL actual post-navegación, si el portal legacy cargó, si el campo usuario/contraseña fue encontrado, cantidad de secciones y filas por cardholder, errores de parse individuales).
- **`ScraperResult.log_lines`**: nuevo campo en el dataclass que acumula líneas de diagnóstico del scraper; se propaga de `_scrape_producto` → `scrape` → `_run_sync` → `scraper_status.last_log`.
- **`scraper_status.last_log`**: nueva columna en la tabla (con migración automática si la BD ya existe) que persiste el log del último run para mostrarlo en la UI.

## 0.3.8

- **Fix — guardar credenciales de scraper crasheaba con "no running event loop"**: `PUT /api/scrapers/credentials/{banco}` y `POST /api/scrapers/scheduler/reload` eran endpoints `def` síncronos, por lo que FastAPI los ejecutaba en un thread pool sin event loop. `AsyncIOScheduler.start()` llama internamente a `asyncio.get_running_loop()` y fallaba con `RuntimeError`. Fix: ambos endpoints ahora son `async def`.

## 0.3.7

- **Guía de instalación iOS en la UI**: la sección "Accesos rápidos" (Config → Interfaz) ahora muestra un panel "Instalar en iOS" con un link por cada acceso configurado. El usuario abre el link en Safari y usa Compartir → Agregar al inicio; el ícono queda con el nombre correcto de la cuenta.
- **Título dinámico en `/quick`**: el servidor inyecta el nombre de la cuenta en `<title>` y `apple-mobile-web-app-title` según el parámetro `label` de la URL, para que el diálogo "Agregar al inicio" en iOS sugiera el nombre correcto (ej. "AMEX", "BBVA Cuenta").
- **Aclaración de plataformas**: el texto de la sección explica que los shortcuts del manifest funcionan en Android + Chrome, y la vía iOS es agregar íconos individuales al inicio.
- **URLs de manifest con label**: los shortcuts del `manifest.json` ahora incluyen `?label=…` en la URL para que el título sea correcto también al abrirlos desde Android.

## 0.3.6.1

- **Fix 422 en guardar shortcuts**: `PUT /api/config/pwa-shortcuts` fallaba con 422 porque FastAPI no infiere JSON body para parámetros `list`; corregido con `Body(...)`.
- **Shortcuts al tope del tab Interfaz**: la sección "Shortcuts de la PWA" ahora aparece al principio del sub-tab, sin necesidad de scrollear.
- **Moneda automática en formulario rápido**: `/quick` llama a `/api/cuentas` y si la cuenta tiene moneda fija (ARS o USD) oculta el selector; para fuentes de scraper o cuentas MULTI lo mantiene visible.

## 0.3.6

- **PWA Shortcuts — formulario rápido de gastos**: desde iOS/Android, al mantener presionado el ícono de la app instalada aparecen shortcuts configurables por el usuario. Cada shortcut abre `/quick?fuente=<fuente>`, una página standalone ultra-simple con campo de monto numérico (teclado decimal en iOS), fecha pre-completada con hoy, selector de categoría, descripción opcional y tipo egreso/ingreso.
- **Carga rápida con conciliación automática**: al guardar, el movimiento se inserta en `movimientos_raw` con `estado='new'` y se corre la conciliación. Si matchea con un PDF ya importado queda vinculado; si es nuevo (unmatched) se importa automáticamente a `gastos` con la categoría elegida.
- **Nuevo helper `scrapers_db.insert_movimiento_raw_single`**: inserta un único movimiento y devuelve su ID — necesario para el follow-up post-conciliación del formulario rápido.
- **Nuevo endpoint `POST /api/movimientos-rapidos`**: recibe `{fuente, fecha, descripcion, monto, moneda, categoria, tipo}`, ejecuta el flujo completo inserción → conciliación → auto-importación si corresponde.
- **Manifest dinámico**: `/manifest.json` ahora se genera server-side. Si el usuario está logueado incluye sus shortcuts en el campo `shortcuts` del manifest; si no, devuelve el manifest base sin shortcuts.
- **Configuración de shortcuts en la UI**: nueva sección "Shortcuts de la PWA" al final de Config → Interfaz. Permite agregar, renombrar y eliminar shortcuts; las fuentes disponibles incluyen bancos conocidos y cuentas manuales del usuario. Guardado en `user_config.json` del usuario.
- **Nueva clave `pwa_shortcuts` en `user_config.json`**: lista de `{fuente, label}` que define los shortcuts del manifest. Retrocompatible — si no existe se asume lista vacía.

## 0.3.5

- **Credenciales de scrapers en la UI**: nuevo sub-tab "Scrapers" en Config. Cada banco (AMEX, BBVA, Galicia, MercadoPago) tiene su propia card con toggle habilitado/deshabilitado, campos de credenciales, hora de ejecución diaria y botones de acción (Guardar, Ejecutar ahora, Borrar sesión). Para Galicia muestra además el área de código TOTP.
- **Almacenamiento por usuario**: las credenciales se guardan en `{data_dir}/scraper_credentials.json` (en el directorio de cada usuario autenticado). No se necesita más crear `/data/scrapers.yaml` a mano.
- **Seguridad de contraseñas en la API**: el endpoint GET `/api/scrapers/credentials` nunca devuelve contraseñas; indica si hay una guardada con `has_password: true`. Al hacer PUT, un campo vacío conserva la contraseña existente.
- **Nuevo módulo `scraper_credentials.py`**: define los campos de cada banco, operaciones de lectura/escritura por usuario, y `find_all_enabled_configs()` que escanea todos los directorios de usuario para el scheduler.
- **Scheduler actualizado**: lee desde `scraper_credentials.py` (no más `scrapers_config.py`), setea el ContextVar de `userctx` antes de cada job para que las operaciones de DB usen el directorio correcto.
- **`scrapers_db._find_db_path()`**: simplificado — usa el ContextVar de `userctx` directamente (seteado por el scheduler o por la request HTTP activa).
- **Endpoints TOTP generalizados**: `/api/scrapers/{banco}/session-setup` y `/api/scrapers/{banco}/totp` reemplazan los hardcodeados de Galicia; cualquier banco con `totp: True` puede usarlos.

## 0.3.4

- **Scraper AMEX — implementación real**: reemplaza el stub anterior con lógica completa calibrada contra los HTML reales del portal (`samples/Amex Table.html`). Implementa `check_session` (navega al portal legacy y verifica `div#middleContentHeader`), `do_login` (maneja el flow React con soporte para pantallas de usuario/contraseña separadas), y `scrape` (parsea las dos tarjetas por sorted_index 0/1 y las secciones `txnsCard{N}` por cardholder).
- **Scraper AMEX — parser de tabla**: extrae fecha desde texto DD-MM-YYYY o desde el timestamp en ms del atributo `id` de la celda; detecta filas ARS vs USD por la clase `dollarText` en el `<tr>`; mapea las 6 columnas de la tabla (ARS pagos/cargos + USD pagos/cargos) a `monto` positivo (egreso) o negativo (crédito); nuevo helper `_parse_usd_amount` para el formato argentino `U$S 1.234,56`.
- **Scraper AMEX — saldo**: lee `td#colOSBalance` para extraer saldo ARS y USD del período actual.

## 0.3.3

- **Fix build definitivo — reemplazo Playwright → Selenium**: la causa raíz era que Playwright solo publica wheels `manylinux_2_17_aarch64` (glibc), incompatibles con Alpine Linux (musl libc). No existe wheel de Playwright para musllinux. Selenium es `py3-none-any` (pure Python) y usa el ChromeDriver del sistema (`apk add chromium-chromedriver`), sin dependencias de plataforma.
- **Dockerfile**: agrega `chromium-chromedriver` al paso apk; elimina el step separado de pip y las variables de entorno de Playwright; setea `CHROMIUM_BIN` y `CHROMEDRIVER_BIN`.
- **requirements.txt**: reemplaza `playwright` por `selenium==4.44.0` y `apscheduler==3.11.2` (ambos pure Python, sin problemas en musl/Alpine).
- **scrapers/base.py**: reescrito para Selenium WebDriver síncrono; `run()` mantiene la interfaz async envolviendo el código en `run_in_executor`; gestión de sesión via cookies + localStorage en JSON (reemplaza `storage_state` de Playwright).
- **scrapers/galicia.py**: flujo TOTP reescrito con `threading.Event` (en lugar de `asyncio.Queue`) ya que Selenium corre en un thread.

## 0.3.2

- **Fix build**: `PIP_CONFIG_FILE=/dev/null` para ignorar el pip.conf del sistema en el paso de instalación de playwright/apscheduler. El índice de HA devuelve una respuesta vacía para playwright que confunde a pip con "from versions: none" incluso cuando PyPI está accesible.

## 0.3.1

- **Fix build**: bump de versión para forzar rebuild limpio de la imagen Docker tras el fix de playwright/apscheduler.

## 0.3.0

- **Scrapers web — infraestructura completa**: nuevo sistema de scraping diario de movimientos bancarios vía Playwright. Incluye scheduler (APScheduler), tabla de staging `movimientos_raw`, tabla de estado `scraper_status` y motor de conciliación automática contra los PDF ya importados.
- **Scrapers — AMEX, BBVA, Galicia, MercadoPago**: cuatro scrapers estructurados con selectores a calibrar contra los portales reales. Cada banco tiene su clase (BaseScraper) con check_session/do_login/scrape. Stubs listos para completar con selectores definitivos.
- **Conciliación automática**: algoritmo de matching raw→gastos por fuente + monto exacto + ventana de ±5 días + similitud de descripción (difflib). Umbral 0.80 para auto-match; por debajo queda como "unmatched" para revisión manual.
- **Flujo TOTP interactivo para Galicia**: setup de sesión vía endpoint `/api/scrapers/galicia/session-setup` + `/api/scrapers/galicia/totp`. El browser headless pausa en la pantalla de TOTP y espera el código ingresado por el usuario en la UI (queue asyncio, timeout 5 min).
- **API de scrapers**: nuevos endpoints en `/api/scrapers/` — estado, trigger manual, movimientos pendientes, importar/ignorar, gestión de sesiones.
- **Dockerfile — Playwright en Alpine arm64**: agrega chromium + dependencias gráficas vía apk; usa el Chromium del sistema (`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`) en lugar de descargar uno propio, ahorrando ~400 MB de imagen.
- **scrapers.yaml**: credenciales en `/data/scrapers.yaml` (mismo patrón que rules.yaml); no se tocan las options de config.yaml. Incluye `owner_email` para que el background job ubique la DB del usuario correcto.

## 0.2.83

- **Fix — dropdown flotante de categoría en formulario "Nuevo movimiento"**: el campo Categoría del panel "+ Movimiento" tenía el mismo problema de truncado que la tabla de gastos (usaba `<datalist>` nativo). Ahora también usa el dropdown flotante con nombres completos. Escape limpia el campo y cierra el dropdown.

## 0.2.82

- **Gastos — autocomplete de categoría con dropdown flotante**: reemplaza el `<datalist>` nativo del campo categoría en la tabla de gastos por un dropdown personalizado que flota encima del contenido. El ancho mínimo es 220 px (o el ancho del input si es mayor), por lo que nombres largos como "Impuestos Especiales" se muestran completos sin truncarse. El filtro es por substring (no solo prefijo). Las flechas ↑↓ navegan la lista; Enter selecciona y guarda; clic en un ítem selecciona.
- **Gastos — Escape cancela la edición de categoría**: al presionar Escape el campo vuelve al valor original, desaparece el indicador de cambio pendiente y el input pierde el foco. El dropdown se cierra en el mismo gesto. Los otros campos que usan `cat-datalist` (formulario nuevo movimiento, modal de chart) no se ven afectados.

## 0.2.81

- **Fix Interfaz — botones y preview fuera del sub-tab**: un `</div>` sobrante cerraba prematuramente el panel `cfg-tab-ui`, dejando los botones "Guardar/Restablecer" y la vista previa de colores visibles en todo el tab Config en lugar de solo dentro del sub-tab Interfaz.

## 0.2.80

- **Interfaz — color de acento personalizable**: nuevo picker "Color de acento" cubre navbar, botones primarios, chips activos y botón de scroll. Implementado como CSS custom property `--color-accent`; todos los usos previos de `#16213e` en el CSS ahora referencian la variable.
- **Interfaz — tamaño de texto**: slider de 12 a 17 px que se aplica al instante como vista previa; se guarda al hacer "Guardar".
- **Interfaz — período y moneda por defecto en Gráficos**: dos selectores que determinan los valores iniciales de los filtros al abrir la tab Gráficos (antes siempre arrancaban en 6 meses / ARS).
- **Interfaz — umbrales de urgencia en widget de vencimientos**: dos inputs numéricos para definir cuántos días se consideran "urgente" (rojo, default 3) y "pronto" (ámbar, default 7).
- **Interfaz — visibilidad de secciones del widget de vencimientos**: tres checkboxes para mostrar u ocultar la línea RG 5617, la referencia PDF y la fila de próximo cierre/vencimiento. Los cambios se aplican al hacer "Guardar" y el widget se recarga automáticamente.
- **Refactor**: `saveUiColors` + `resetUiColors` renombradas a `saveUiSettings` / `resetUiSettings`; preferencias no-color se guardan en `localStorage("ui_prefs")`; las de color siguen en `localStorage("ui_colors")`.

## 0.2.79

- **Config — sub-tabs en lugar de acordeones**: la pestaña ⚙ Config ahora usa una barra de sub-tabs horizontales (Importar · Reglas · Personas · Cuentas · Interfaz · ⚠ Borrar) con el mismo estilo visual que las tabs principales. Dentro de los sub-tabs que tienen varias secciones (Reglas, Personas) se conservan los acordeones expandibles (+/−). Se eliminó el botón "Cerrar todo".
- **Config — nueva sub-tab Interfaz (colores personalizables)**: permite elegir el color de los montos ARS, montos USD, línea RG 5617 y el tono del toggle "sin RG". Los colores se aplican mediante CSS custom properties (`--color-ars`, `--color-usd`, `--color-rg5617`, `--color-toggle-rg`) y se guardan en `localStorage`. Incluye una vista previa en tiempo real y un botón "Restablecer" para volver a los valores predeterminados.
- **Verde ARS más oscuro por defecto**: el color predeterminado de montos ARS pasa de `#16a34a` (green-600) a `#15803d` (green-700), ligeramente más oscuro y con mejor contraste.
- **Colores en widgets vía CSS vars**: todos los colores de montos en widgets (saldo-cards y vencimientos) ahora usan las custom properties en lugar de valores fijos, por lo que responden inmediatamente al cambiar los colores en la tab Interfaz.

## 0.2.78

- **Widget saldos y vencimientos — color en el monto, no en el nombre**: el color verde/azul por moneda se aplica ahora sobre el importe (`saldo-monto` con clase `ars-val` o `usd-val`), no sobre el nombre de la cuenta. El nombre de la cuenta (`saldo-nombre`) vuelve siempre al gris neutro `#888`, igual que antes de v0.2.74. En el widget de vencimientos, `venc-fuente` también queda en gris; solo los montos ARS (`venc-ars`) y USD (`venc-usd`) conservan el color. El criterio positivo/negativo anterior (verde = positivo, rojo = negativo) se reemplaza por verde = ARS, azul = USD en los saldo-cards.

## 0.2.77

- **Widget saldos (fila superior) — nombre en verde/azul según moneda**: el label de cada cuenta (`saldo-nombre`) ahora usa verde (`#16a34a`) para cuentas ARS y azul (`#2563eb`) para cuentas USD, igual que los montos en el widget de vencimientos. Las cuentas MULTI (ARS + USD) mantienen el gris neutro.
- **Widget vencimientos — fecha en gris**: `venc-fecha` cambia de `#1a1a2e` (casi negro) a `#64748b` (slate-500) para igualar el tono visual apagado de los saldo-cards de la fila superior.

## 0.2.76

- **Fix widget vencimientos — pantalla en blanco**: `const rg5617` se declaraba en la línea 1867 pero se usaba en `hasRg` (línea 1846), violando la zona muerta temporal de `const` y lanzando un `ReferenceError` que impedía renderizar todas las cards. Se movió la declaración al inicio del bloque, antes de su primer uso, y se eliminó la declaración duplicada.

## 0.2.75

- **Widget vencimientos — doble clic para ver monto sin RG 5617**: cuando una card tiene percepción RG 5617 del período, hacer doble clic sobre el total ARS muestra el importe neto sin el cargo (`net_ars − rg5617_ars`) en color ámbar con etiqueta `−RG` en superíndice. Un segundo doble clic vuelve al total original en verde. El cursor cambia a `pointer` y hay un `title` como ayuda. El estado se resetea automáticamente cuando el widget se recarga.

## 0.2.74

- **Widget vencimientos — próximo cierre y próximo vencimiento**: cada card muestra debajo del consumo una línea `Próx. cierre DD/MM · venc. DD/MM` con las fechas del siguiente ciclo. AMEX expone solo el próximo vencimiento (fecha que sigue al `- + = <total>` en el encabezado); BBVA expone ambas (fila `PRÓXIMO CIERRE PRÓXIMO VENCIMIENTO` en el header). Las fechas se guardan en las columnas `proximo_cierre` y `proximo_venc` de `importaciones` (migración automática `ALTER TABLE`).
- **Widget vencimientos — colores por moneda**: el nombre de la cuenta (`venc-fuente`) aparece en verde si el resumen tiene saldo ARS, en azul si es solo USD. Los montos ARS en la fila de consumo son verdes (`venc-ars`) y los USD azules (`venc-usd`). La línea RG 5617 mantiene el gris claro (`#94a3b8`). La línea de próximas fechas tiene un separador sutil y tipografía más pequeña.

## 0.2.73

- **Devoluciones RG 5617 importadas por defecto**: el checkbox "Incluir devoluciones RG 5617" ahora viene marcado de fábrica. Importar el crédito `DEV PERCEPCION / CR.RG` junto al cargo del período hace que la lista de gastos refleje el gasto real (percepción neta) en lugar de mostrar solo el cargo sin su compensación.
- **Widget vencimientos — total a pagar excluye créditos RG 5617**: el campo `net_ars` que el widget usa como "total a pagar" ahora descarta las filas negativas (créditos/devoluciones) cuya descripción contenga "5617". Esto asegura que el total coincida con el TOTAL A PAGAR del PDF independientemente de si las devoluciones fueron importadas o no. El cargo RG 5617 del período sigue siendo parte del total; solo el crédito del período anterior se ignora en el cálculo del widget.
- **Fix cálculo de fila sintética "Créditos del resumen" con créditos 5617 importados**: el delta `stmt_ars − net_importado` también excluye las devoluciones RG 5617 para que la fila sintética se genere correctamente (delta negativo pequeño) aunque los créditos estén en la base de datos. Sin este ajuste, importar el DEV PERCEPCION convertía el delta en positivo (+779 k para AMEX Mar26) y eliminaba la fila sintética que cubre el carry-over de período anterior.

## 0.2.72

- **Fix AMEX — "Transacciones financieras" no importadas**: intereses punitorios, intereses financieros e IVA 21% que AMEX agrupa en la sección "Transacciones financieras aplicables a la Cuenta Básica" no se importaban. Esta sección aparece en el PDF entre el cierre de la última sub-sección de pesos y el inicio de "Nuevos Cargos en DÓLARES", justo cuando `current_moneda` es `None`. Solución: al detectar el encabezado "Transacciones financieras" se reactiva el modo ARS con `current_usuario = None` (cargos a nivel cuenta → Titular); el cierre se produce con "Total de transacciones". Las filas tienen prefijo "DD de MES" y sus importes se parseaban correctamente; el único obstáculo era no estar dentro del bloque ARS.
- **Fix AMEX — "Intereses" en `_SKIP_DESC` bloqueaba cargos legítimos**: el patrón `Intereses` impedía importar filas cuya descripción comenzara con "Intereses punitorios" o "Intereses financieros". Esas filas solo llegan al filtro si ya pasaron la comprobación de fecha (`DD de MES`), es decir, son transacciones reales; las líneas informativas "Información sobre Intereses" son filtradas antes por no tener prefijo numérico. Se eliminó `Intereses` del patrón `_SKIP_DESC`. Efecto neto en el resumen Amex Mar26: delta ARS pasa de +154.531 (sin fila sintética) a -2.429 (pequeña fila "Créditos del resumen").

## 0.2.71

- **Filtro créditos RG 5617 al importar**: los registros de devolución de percepción RG 5617 (`DEV PERCEPCION RG 5617` en AMEX, `CR.RG 5617` en BBVA) ya no se importan por defecto. El endpoint `/upload` acepta el parámetro `include_rg5617_credits` (default `false`); si es falso, se descartan las filas cuya descripción contiene "5617" y cuyo monto es negativo (créditos). En el formulario de importación se agregó un checkbox "Incluir devoluciones RG 5617" que por defecto queda desmarcado. Fundamento: quienes pagan el saldo en USD con USD recuperan la percepción del período anterior automáticamente; importarla genera ingresos fantasma.
- **Fix widget vencimientos no se actualiza al borrar**: faltaba llamar `loadVencimientos()` en el callback de éxito del botón de borrado; ahora se llama junto a `loadGastos()`, `loadMonthlyChart()`, `loadCategorias()` e `loadImportaciones()`.
- **Fix borrado — selección peligrosa por defecto**: la opción "Todas las fuentes" estaba seleccionada por defecto en el `<select>` del diálogo de borrado, permitiendo borrar todo con un solo clic sin intención. Ahora el `<select>` inicia con un placeholder `disabled` ("Seleccioná fuente o importación…") y la opción destructiva pasó a ser `⚠ Todas las fuentes` como entrada separada. El handler muestra un toast de error si no hay selección válida.

## 0.2.70

- **Fix AMEX — PERCEPCION RG 5617 con monto grande no importada**: el umbral de columna de importes (`_AMOUNT_X`) bajó de 500 pt a 490 pt. AMEX alinea los importes a la derecha en una columna de ~542 pt; números de 12+ dígitos como "2.362.741,92" comienzan en x0 ≈ 495.8 (< 500 anterior) y quedaban fuera de la banda → no se parseaban. Los números de referencia de descripción quedan por debajo de x0 ≈ 240, por lo que el nuevo límite no genera falsos positivos.
- **Fix AMEX — Cuota Anual no importada**: el patrón `Cuota` en `_SKIP_DESC` descartaba la cuota anual de membresía (p.ej. "Cuota Anual 04/26 - 03/27 $735.000"). Las sub-filas de plan de cuotas como "Cuota 01 de 03" ya son filtradas antes por la detección de fecha, por lo que el patrón era redundante e incorrecto.
- **Fix BBVA — fechas de cuotas (installments) no reasignadas**: `_detect_statement_date()` usa patrones DD/MM/AA pero BBVA imprime las fechas en DD-Mmm-AA; siempre retornaba `None` → `stmt_date = None` → `_installment_date()` nunca se ejecutaba → las cuotas mantenían la fecha original de compra en lugar de la del período del resumen. Solución: `_detect_vencimiento_bbva()` ya parseaba DD-Mmm-AA y ahora también retorna la fecha de cierre (`dates[0]`) que se usa como `stmt_date`.
- **Fix widget RG 5617 — mostrar solo el cargo del período actual**: la columna `rg5617_ars` en `list_vencimientos()` ahora suma solo transacciones positivas (percepción cobrada en el período), excluyendo los créditos `DEV PERCEPCION` / `CR.RG` que corresponden a devoluciones del período anterior.

## 0.2.69

- **Widget de vencimientos — línea RG 5617**: cada card muestra una línea secundaria con el neto de percepciones RG 5617 del resumen (`LIKE '%5617%'` sobre `descripcion`). Valor positivo = percepción neta cobrada (crédito fiscal ante AFIP deducible); valor negativo = más DEV que cargos en ese período. La línea no aparece si el valor es cero o menor a $0,50. Implementado como nueva columna `rg5617_ars` en `list_vencimientos()` y elemento `.venc-rg5617` en el widget.

## 0.2.68

- **Fix fila sintética "Créditos del resumen" con delta positivo (BBVA / AMEX)**: con el cálculo neto introducido en 0.2.67, el delta para BBVA y AMEX resultaba positivo (saldo de período anterior no representado como transacción del ciclo actual), lo que generaba filas de egreso erróneas. Ahora la fila sintética solo se inserta cuando `delta < -0,50` (genuine credit/overpayment); un delta positivo se ignora silenciosamente.
- **Fix AMEX — crédito CR en sub-fila**: el marcador `CR` que imprime AMEX a veces queda en una línea separada (gap y > 2 pt) no agrupada por `group_by_y`. El parser ahora hace look-ahead al siguiente row: si contiene solo tokens `CR` en la banda de importes y no comienza con dígito (no es nueva transacción), absorbe el CR como ingreso. Corrige `DEV PERCEPCION RG 5617` que seguía importándose como egreso pese al fix de 0.2.66.

## 0.2.67

- **Fix "Créditos del resumen" duplicado en Galicia (y AMEX)**: el delta para la fila sintética ahora se calcula contra el **neto** de todas las transacciones ARS del import (`stmt_total_ars − net_ars_imported`) en lugar del bruto de egresos. Créditos que el parser ya importó como ingresos (BONIF.COM.MEN.MANT.C, devoluciones MercadoLibre, CR.RG de AFIP…) quedan en el net y cierran el gap por sí solos; el delta resulta ~0 y no se inserta ninguna fila sintética. El residuo que genera la fila sintética es exclusivamente lo que cae fuera de las transacciones del período (ej. saldo anterior de BBVA − pago → overpayment de ciclo previo).
- **Widget de vencimientos — monto neto**: el widget ahora muestra `net_ars` (egresos − créditos ya importados) como valor principal en lugar del bruto de egresos. El número coincide con el `TOTAL A PAGAR` / `SALDO ACTUAL` del PDF cuando el import está completo.
- **Nota**: reimportar los resúmenes afectados (Galicia / AMEX con créditos) para corregir la fila sintética duplicada en imports anteriores a esta versión.

## 0.2.66

- **Fix AMEX — créditos con marcador CR**: transacciones como `DEV PERCEPCION RG 5617` no se importaban por dos bugs simultáneos: (1) el token `CR` que AMEX imprime junto al monto se concatenaba (`"1.234,56CR"`) haciendo fallar el parseo del número; (2) el filtro `description.startswith("DEV ")` descartaba explícitamente estas filas. Ahora se detecta y separa `CR` de las palabras numéricas, se niega el monto resultante (crédito → ingreso, monto negativo), y el filtro DEV se reemplaza por uno que solo salta `"Gracias por su pago"`.

## 0.2.65

- **Fix widget de vencimientos — línea PDF solo aparece en inconsistencia real**: la comparación para mostrar la línea amber `PDF: $X` ahora usa el net de las transacciones del import (egresos − créditos, incluyendo la fila sintética "Créditos del resumen") en lugar del bruto de egresos. Cuando el crédito sintético fue insertado correctamente, `net_ars == total_ars` y no aparece línea secundaria. La línea amber solo se muestra si el net difiere del PDF, indicando un error real del parser o transacciones faltantes. `list_vencimientos()` agrega `net_ars`/`net_usd` al resultado.

## 0.2.64

- **Widget de vencimientos — suma de egresos siempre visible**: `list_vencimientos()` ahora hace JOIN con `gastos` y calcula `sum_ars`/`sum_usd` (suma de egresos del import) además del total extraído del PDF (`total_ars`/`total_usd`). El widget muestra `sum_ars` como valor principal — siempre disponible aunque el parser no haya detectado el total del PDF. Si `total_ars` existe y difiere de `sum_ars` en más de $0,50, aparece una línea secundaria en amarillo `PDF: $X` para detectar inconsistencias del parser.

## 0.2.63

- **Fila sintética "Créditos del resumen"**: al importar un resumen de tarjeta, si el parser detectó el `SALDO ACTUAL` / `TOTAL A PAGAR` del PDF, se inserta automáticamente una fila de ajuste con `monto = stmt_total_ars − suma_egresos_ARS`. El delta es típicamente negativo (crédito/sobrepago aplicado por el banco) y aparece como ingreso en la lista de gastos, haciendo visible el overpayment. Para BBVA, donde se puede reclamar el saldo a favor, esto es crítico. La respuesta del upload incluye `ajuste_resumen_ars` con el valor del ajuste cuando aplica.

## 0.2.62

- **Fecha de vencimiento en parsers**: AMEX, BBVA (MC y Visa) y Galicia MC ahora extraen la `fecha_vencimiento` directamente del PDF.
- **Totales del resumen**: los parsers también extraen el `SALDO ACTUAL` (BBVA) o `TOTAL A PAGAR` (Galicia) / saldo a pagar (AMEX) en ARS y USD.
- **Columnas en `importaciones`**: se agregan `fecha_venc TEXT`, `total_ars REAL`, `total_usd REAL` con migración automática.
- **Endpoint `/api/stats/vencimientos`**: retorna los imports más recientes por fuente que tienen `fecha_venc`.
- **Widget de vencimientos**: cards encima del contenido principal con fecha de vencimiento, días restantes y total a pagar por tarjeta. Colores: rojo (≤3 días / vencido), amarillo (≤7 días), verde (>7 días).
- **Fix BBVA — transacción USD faltante**: texto de marca de agua (`ocnaB` = "Banco" rotado 180°) se concatenaba con el monto en la columna USD. Corregido con filtro `_AMOUNT_WORD_RE` que descarta tokens no numéricos en las columnas de monto.

## 0.2.61

- **Fix colores inconsistentes en charts personalizados**: `_drawCustomChart` usaba `PALETTE.slice()` en lugar de `_catColor()`, por lo que las barras de charts custom mostraban colores distintos al donut de categorías. Ahora todos los charts usan `_catColor(label, index)` para mantener coherencia visual.

## 0.2.60

- **Fix cache de estáticos**: el servidor ahora añade `?v=0.2.60` a las URLs de `app.js` y `style.css` al servir la página. El browser trata la URL como nueva en cada release y descarga los archivos frescos, eliminando el problema de que el código viejo se seguía ejecutando aunque se actualizara el add-on.

## 0.2.59

- **Colores consistentes entre charts**: el donut "por categoría" ahora construye un mapa global `categoría → color` al renderizar, y el stacked bar "mes a mes" lo usa para asignar el mismo color a cada categoría. "Supermercado" siempre es el mismo color en ambos charts.

## 0.2.58

- **Versión en el navbar**: muestra `v0.2.58` en gris pequeño al lado del título "Gastos". Se inyecta desde el servidor (`window.APP_VERSION`) así siempre queda en sincronía con la versión del add-on.

## 0.2.57

- **Fix cross-filter donut**: al clickear una categoría, el donut ahora sigue mostrando todas las categorías (las no seleccionadas en gris) en lugar de colapsar a un solo slice. El problema era que el filtro `categoria=X` se enviaba también al endpoint que alimenta el donut, devolviendo solo una categoría. Ahora se hace un segundo fetch sin ese filtro exclusivamente para el donut.

## 0.2.56

- **Fix cross-filter donut**: las categorías no seleccionadas ahora se muestran en gris claro (`#d1d5db`) en lugar del semitransparente confuso que tenían antes.

## 0.2.55

- **Fix charts custom — total en el título**: los charts personalizados ahora muestran el total en el encabezado igual que los charts fijos. El span `.chart-total` se crea siempre en `_buildChartBox`, con o sin `id`.

## 0.2.54

- **Fix**: `user_config.json` (personas, mapeo fuente→persona, reglas de asignación) ahora también se almacena en el directorio por usuario `/data/{email}/` en lugar del directorio raíz.

## 0.2.53

- **Aislamiento de datos por usuario**: cada usuario tiene su propio directorio de datos en `/data/{email}/` con su `gastos.db`, `rules.yaml` y `match_rules.yaml` independientes. Un middleware establece el contexto de datos por cada request usando `contextvars` de Python, sin necesidad de cambiar las firmas de las funciones existentes.
- **Migración automática**: en el primer acceso de cada usuario, si existen archivos en `/data/` (instalación anterior con un solo usuario), se copian automáticamente a su directorio personal, preservando todos los datos existentes.
- Nuevo módulo `userctx.py` con `get_db_path()`, `get_rules_file()`, `get_match_rules_file()` y `set_user_context()`.

## 0.2.52

- **Fix charts desaparecen al recargar la página**: `loadChartLayout()` no tenía manejo de errores — cualquier excepción en el fetch, el JSON o `rebuildChartsGrid()` dejaba `_layoutReady` en `false` para siempre y `loadCharts()` nunca se ejecutaba. Se agregaron try/catch/finally en ambas rutas de inicialización (`loadChartLayout` y `loadMonthlyChart`) garantizando que los flags `_layoutReady` y `_filtersReadyForCharts` siempre se setean aunque algo falle.
- **Fix crash en cascade**: `_destroyAndCreate()` y todas las funciones `_draw*` hacían `getElementById(...)` sin null-check; si el canvas o el span de total no existían en el DOM, la excepción cortaba el render del resto de los charts. Ahora todos son defensivos.

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
