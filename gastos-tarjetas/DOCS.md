# SnapBudget — Documentación

Add-on para Home Assistant que parsea extractos bancarios argentinos (PDF/XLSX),
categoriza automáticamente los movimientos y lleva el saldo de tus cuentas.

---

## Configuración

| Opción | Tipo | Requerido | Descripción |
|--------|------|-----------|-------------|
| `allowed_domain` | string | ✅ | Dominio de correo permitido para registrarse (ej: `miempresa.com`). Solo se aceptan cuentas `@ese-dominio`. |
| `registration_enabled` | bool | ✅ | `true` habilita el registro de nuevos usuarios desde la pantalla de login. Por defecto `false`. Se puede cambiar en tiempo real desde el panel Admin. |
| `admin_password` | string | — | Contraseña para el usuario administrador. Si se deja vacío, el acceso admin queda deshabilitado. |
| `titular2_name` | string | — | Nombre (o fragmento) del titular adicional tal como aparece en los PDFs de AMEX o BBVA (ej: `"Maria"`). Los movimientos de sus secciones quedan asignados a `Adicional`; el resto a `Titular`. Si se deja vacío, todos los movimientos van a `Titular`. |
| `claude_api_key` | string | — | API key de Anthropic Claude para categorización automática con IA. |
| `groq_api_key` | string | — | API key de Groq (Llama 3, gratis ~14.000 req/día) para categorización IA. |
| `gemini_api_key` | string | — | API key de Google Gemini 2.0 Flash (gratis ~1.500 req/día) para categorización IA. |

### Orden de categorización automática

1. Reglas propias (keywords configurables en el tab Reglas)
2. Groq (si hay clave)
3. Gemini (si hay clave)
4. Claude (si hay clave)

Si ningún proveedor está configurado, los movimientos quedan sin categoría para asignar manualmente.

---

## Usuario administrador

El usuario admin se construye automáticamente como **`admin@<allowed_domain>`**.

Ejemplo: si `allowed_domain: miempresa.com`, el admin es `admin@miempresa.com` con
la contraseña configurada en `admin_password`.

Desde el panel Admin (`⚙ Admin` en el navbar, solo visible al loguearse como admin) podés:

- Habilitar / deshabilitar el registro de nuevos usuarios en tiempo real
- Ver todos los usuarios registrados
- Eliminar usuarios
- Resetear contraseñas

---

## Fuentes soportadas

| Fuente | Formato | Moneda |
|--------|---------|--------|
| AMEX Argentina | PDF | ARS + USD (MULTI) |
| BBVA Mastercard | PDF | ARS + USD (MULTI) |
| BBVA Visa | PDF | ARS + USD (MULTI) |
| Galicia Mastercard | PDF | ARS + USD (MULTI) |
| BBVA Cuenta | PDF | ARS |
| MercadoPago | XLSX (exportación) | ARS |

---

## Cuentas

### Automáticas
Se crean al importar el primer PDF de cada fuente. El saldo se actualiza
automáticamente en cada importación (cuando el parser lo detecta) o se puede
editar manualmente con el botón ✏.

Las tarjetas de crédito son de tipo **MULTI** y muestran saldo ARS + USD por separado.

### Manuales
Se crean desde el tab Cuentas con un nombre libre y moneda (ARS o USD).
Los movimientos se agregan manualmente (fecha, descripción, monto, tipo Egreso/Ingreso,
categoría) y el saldo se recalcula automáticamente.

Los movimientos de cuentas manuales aparecen también en el tab Gastos con un botón ✕
para eliminarlos directamente desde ahí.

### Widget de saldos
El widget fijo encima de los tabs muestra las cuentas con **Widget ✓** activo.
Se puede editar el saldo directamente desde ahí con el botón ✏.

---

## Usuarios (Titular / Adicional)

El campo Usuario en cada movimiento indica a quién pertenece el gasto.
Por defecto todos los movimientos importados se asignan a **Titular**.

Si configurás `titular2_name` con el nombre del titular adicional tal como
aparece en el PDF (basta con el primer nombre), los movimientos de sus secciones
se asignan a **Adicional** automáticamente al importar.

El usuario se puede cambiar manualmente en cualquier momento desde el dropdown
en la tabla de Gastos.

---

## Reglas de categorización

Las reglas asocian palabras clave a categorías. Si la descripción de un movimiento
contiene alguna de las palabras (sin distinguir mayúsculas), se asigna esa categoría.

**Auto-aprendizaje:** al categorizar manualmente un movimiento, su descripción se
agrega automáticamente como keyword a la regla de esa categoría (se crea la regla
si no existía). Los próximos imports con la misma descripción quedan categorizados solos.

---

## Presupuesto

Definí un monto mensual por categoría en el tab Presupuesto. Al seleccionar un mes
se muestra una tabla con lo presupuestado vs lo gastado y una barra de progreso
(verde → amarillo → rojo según el porcentaje consumido).

---

## Preguntas frecuentes

**¿Cómo habilito el registro de usuarios?**
Loguéate como admin y activá el toggle en el panel Admin. También podés poner
`registration_enabled: true` en la configuración del add-on y reiniciarlo.

**¿Los datos quedan en Home Assistant?**
Sí. La base de datos SQLite y todos los archivos se guardan en `/data` (volumen
persistente de HA). No se envía nada a servidores externos salvo las descripciones
a la IA de categorización si tenés configurada alguna API key.

**¿Puedo usar el add-on sin API key de IA?**
Sí. La categorización por reglas funciona sin ninguna clave. La IA es opcional.

**¿Qué pasa si cambio `allowed_domain`?**
Los usuarios ya registrados siguen funcionando. Solo afecta a los nuevos registros.
El usuario admin cambia junto con el dominio.
