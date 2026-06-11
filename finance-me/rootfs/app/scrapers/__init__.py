"""
Scrapers de bancos argentinos via Playwright.

Cada scraper es una subclase de BaseScraper que implementa:
  - check_session(page)  → bool
  - do_login(page, cfg)  → None
  - scrape(page, cfg)    → ScraperResult

El scheduler (scraper_scheduler.py) instancia cada scraper y llama a .run(cfg).
"""

from .base import BaseScraper, ScraperResult, MovimientoRaw  # noqa: F401
