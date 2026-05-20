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
