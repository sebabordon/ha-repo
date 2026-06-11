# Finance Me — App iOS (Capacitor)

Contenedor nativo **iOS** que envuelve la PWA de Finance Me (el add-on de Home
Assistant que está en [`../finance-me`](../finance-me)) en un `WKWebView`, para
poder distribuirla por la **App Store**.

> **Arquitectura.** Finance Me es una app *server-driven*: el backend FastAPI
> sirve la UI, la auth y la API. Por eso este contenedor carga la PWA **remota**
> definida en `server.url` de [`capacitor.config.json`](capacitor.config.json),
> en vez de empaquetar el frontend. Ventaja: la app móvil nunca queda
> desincronizada del backend. Contrapartida: requiere que el backend sea
> **accesible públicamente por HTTPS** y que Apple no la considere un "mero
> sitio web envuelto" (ver §6).

---

## 0. Requisitos

| Requisito | Detalle |
|-----------|---------|
| **Mac** | Xcode solo corre en macOS. Imprescindible. |
| **Xcode** | 15+, desde la App Store. Incluye el simulador de iOS. |
| **CocoaPods** | `sudo gem install cocoapods` (Capacitor lo usa para las deps nativas). |
| **Node 18+** | Para el CLI de Capacitor. |
| **Cuenta Apple Developer** | US$ 99/año. Necesaria para subir a la App Store (no para probar en el simulador). |
| **Backend HTTPS público** | La PWA debe ser accesible por `https://` desde el celular (no `homeassistant.local`). Ya tenés el proxy con Nginx Proxy Manager. |

---

## 1. Configurar la URL del backend

Editá [`capacitor.config.json`](capacitor.config.json) y reemplazá el dominio:

```json
"server": { "url": "https://finance-me.tudominio.com", "cleartext": false }
```

- **Producción:** tu dominio público con HTTPS válido. App Transport Security
  (ATS) de iOS **exige HTTPS con certificado válido** — el de Let's Encrypt del
  Proxy Manager sirve.
- **Desarrollo local** contra el add-on en la LAN: podés usar
  `"url": "http://192.168.x.x:8000"` con `"cleartext": true`. **Nunca** dejes
  `cleartext: true` en la build que subís a la App Store.

---

## 2. Generar el proyecto iOS

```bash
cd finance-me-mobile
npm install
npx cap add ios       # crea la carpeta ios/ con el proyecto Xcode (solo la 1ª vez)
npx cap sync ios      # copia config + plugins (correr tras cada cambio de config)
```

## 3. Íconos y splash

Capacitor genera los assets desde una imagen fuente con
[`@capacitor/assets`](https://github.com/ionic-team/capacitor-assets):

```bash
npx @capacitor/assets generate --ios   # busca assets/icon.png (1024×1024) y assets/splash.png (2732×2732)
```

Podés partir del ícono existente del add-on:
[`../finance-me/icon.png`](../finance-me/icon.png).

## 4. Abrir y correr en Xcode

```bash
npx cap open ios
```

En Xcode:
1. Seleccioná el target **App** → pestaña **Signing & Capabilities**.
2. Elegí tu **Team** (tu cuenta de Apple Developer). Xcode genera el
   *provisioning profile* automáticamente.
3. Cambiá el **Bundle Identifier** si querés (default `ar.com.sbsoft.financeme`,
   también en `capacitor.config.json` → `appId`; deben coincidir).
4. Elegí un simulador (p. ej. *iPhone 15*) y dale ▶ para probar.
5. Para probar en tu iPhone físico: conectalo, seleccionalo como destino y ▶.

---

## 5. Publicar en la App Store — paso a paso

1. **App Store Connect** → [appstoreconnect.apple.com](https://appstoreconnect.apple.com)
   → *Mis Apps* → **+** → *Nueva App*. Cargá nombre ("Finance Me"), idioma,
   bundle id y SKU.
2. **Versión y build** en Xcode: subí `Version` (1.0.0) y `Build` (1) en el
   target *App* → *General*.
3. **Archive:** en Xcode, destino *Any iOS Device (arm64)* →
   menú **Product → Archive**. Cuando termina se abre el *Organizer*.
4. **Distribuir:** en el Organizer → **Distribute App** → *App Store Connect* →
   *Upload*. Xcode firma, sube y procesa la build (tarda unos minutos en
   aparecer en App Store Connect).
5. **TestFlight (recomendado antes de producción):** en App Store Connect →
   pestaña *TestFlight*, instalás la build en tu iPhone vía la app TestFlight y
   la probás como usuario real.
6. **Ficha de la App Store:** capturas de pantalla (por cada tamaño de pantalla
   requerido), descripción, categoría, **política de privacidad** (obligatoria,
   ver §6), y el cuestionario *App Privacy* (qué datos recolecta — Finance Me
   maneja datos financieros, declaralo).
7. **Enviar a revisión:** seleccionás la build procesada → *Add for Review* →
   *Submit*. La revisión de Apple suele tardar 24–48 h.

---

## 6. Riesgos de aprobación (leer antes de invertir tiempo)

Apple es estricta con apps que son "un sitio web envuelto". Para no caer en el
rechazo por **Guideline 4.2 (Minimum Functionality)**:

- **Sumá valor nativo** que un navegador no da: Face ID / Touch ID para abrir la
  app (plugin `@capacitor-community/biometric-auth`), notificaciones push,
  widget, o lectura de archivos local. Con solo 1–2 de estas, deja de ser "una
  web".
- **Cuenta y datos financieros:** vas a necesitar **política de privacidad
  publicada** (una URL) y completar *App Privacy*. Si hay login, Apple a veces
  pide una **cuenta de demo** en las notas de revisión.
- **Guideline 3.1.1 (pagos):** si en algún momento cobrás suscripción *dentro*
  de la app, debe ir por compras in-app de Apple (comisión 15–30 %). Mientras
  sea gratis / uso personal, no aplica.
- **Backend siempre arriba:** si el revisor abre la app y el backend no responde,
  la rechazan. Asegurate de que el dominio HTTPS esté estable durante la revisión.

### ¿Alternativa sin App Store?
Como Finance Me **ya es una PWA instalable**, en iOS podés "Agregar a inicio"
desde Safari y queda como app standalone, sin cuenta de Apple ni revisión. Es la
vía más rápida; la App Store solo aporta descubribilidad y features nativas.

---

## Estructura

```
finance-me-mobile/
├── capacitor.config.json   # appId, appName, server.url (← editá el dominio)
├── package.json            # deps de Capacitor
├── www/                    # fallback offline (la PWA real se carga de server.url)
│   └── index.html
└── ios/                    # ← generado por `npx cap add ios` (no se commitea entero)
```
