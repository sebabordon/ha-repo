"""
Script de prueba local para el scraper BBVA.

Uso:
    python test_bbva_login.py [--yaml bbva_test.yaml]

bbva_test.yaml debe tener:
    usuario: "25965231"      # DNI
    tercer_dato: "sebasb"    # usuario BBVA (alias homebanking)
    password: "xxxxxxxx"     # clave digital
"""
import argparse
import logging
import os
import sys
import time
import traceback
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

try:
    from webdriver_manager.chrome import ChromeDriverManager
    _USE_WDM = True
except ImportError:
    _USE_WDM = False

# DATA_DIR en /data no existe en macOS — usar un directorio temporal local
_data_dir = Path(__file__).parent / ".test_data"
_data_dir.mkdir(exist_ok=True)
os.environ.setdefault("DATA_DIR", str(_data_dir))

# Permite correr desde el raíz del repo
sys.path.insert(0, str(Path(__file__).parent / "rootfs" / "app"))

from scrapers.bbva import BbvaScraper  # noqa: E402


def make_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if _USE_WDM:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
    else:
        driver = webdriver.Chrome(options=opts)
    # CDP fingerprint overrides (mismo que base.py _create_driver)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
                if (!window.chrome) { window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} }; }
                Object.defineProperty(navigator, 'plugins', { get: () => { var p=[{name:'Chrome PDF Plugin',filename:'internal-pdf-viewer',description:'Portable Document Format'},{name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',description:''},{name:'Native Client',filename:'internal-nacl-plugin',description:''}]; p.__proto__=PluginArray.prototype; return p; } });
                try { Object.defineProperty(Notification,'permission',{get:()=>'default'}); } catch(e) {}
                Object.defineProperty(navigator,'languages',{get:()=>['es-AR','es','en-US','en']});
                Object.defineProperty(navigator,'platform',{get:()=>'Win32'});
            """
        })
    except Exception:
        pass
    return driver


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yaml", default="bbva_test.yaml")
    args = ap.parse_args()

    creds_path = Path(args.yaml)
    if not creds_path.exists():
        print(f"ERROR: no se encuentra {creds_path}")
        sys.exit(1)

    config = yaml.safe_load(creds_path.read_text())
    print(f"[test] credenciales cargadas: usuario={config.get('usuario')}  tercer_dato={config.get('tercer_dato')}")

    driver = make_driver()
    scraper = BbvaScraper()
    try:
        print("[test] do_login…")
        t0 = time.time()
        scraper.do_login(driver, config)
        print(f"[test] login OK en {time.time()-t0:.1f}s")

        print("[test] check_session…")
        ok = scraper.check_session(driver)
        print(f"[test] check_session → {ok}")

        print("[test] scrape…")
        result = scraper.scrape(driver, config)
        print(f"[test] scrape OK — movimientos: {len(result.movimientos)}")
        for m in result.movimientos[:5]:
            print(f"  {m.fecha}  {m.descripcion[:40]:40s}  {m.monto:>10.2f}  {m.moneda}")
        if len(result.movimientos) > 5:
            print(f"  … y {len(result.movimientos)-5} más")
    except Exception:
        traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
