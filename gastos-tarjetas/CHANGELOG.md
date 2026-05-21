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

- Parser AMEX: detecta automáticamente los cargos de Magdalena Sabina Saenz (secciones "Nuevos Cargos en PESOS/DOLARES para MAGDALENA SABINA SAENZ") y los asigna a usuario="Mada".
- Parser BBVA Visa: detecta la sección "Consumos Magdalena Saenz" y asigna usuario="Mada" a sus movimientos; cierra la sección en "TOTAL CONSUMOS DE MAGDALENA SAENZ".
- Los movimientos de titulares no identificados (Seba) siguen asignándose por el default de fuente en upload.py.

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
- Nueva columna "Usuario" en gastos (Seba / Mada), auto-asignado por fuente (BBVA y MercadoPago → Seba)
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
- Autenticación local con usuarios `@sbsoft.com.ar`
- Interfaz web con tabs: Gastos / Importar / Reglas
- Compatibilidad aarch64 (Raspberry Pi 5) y amd64
