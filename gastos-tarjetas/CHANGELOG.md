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
