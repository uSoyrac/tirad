"""
Web scraper — CoinTelegraph, CoinDesk, BTCHaber, KriptoPara, CryptoPanic API.
Hem statik (requests+BS4) hem dinamik (playwright) sayfa desteği.
"""
import logging
import time
import random
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,tr;q=0.8",
}


def _get(url: str, timeout: int = 15) -> Optional[BeautifulSoup]:
    try:
        time.sleep(random.uniform(1, 2.5))  # Politeness delay
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        logger.warning(f"Scrape hatası {url}: {e}")
        return None


def scrape_cointelegraph(limit: int = 10) -> list[dict]:
    """CoinTelegraph son haberler."""
    soup = _get("https://cointelegraph.com")
    if not soup:
        return []

    articles = []
    for a in soup.select("article a[href*='/news/']")[:limit]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if title and len(title) > 20:
            articles.append({
                "source": "cointelegraph",
                "language": "en",
                "title": title,
                "url": f"https://cointelegraph.com{href}" if href.startswith("/") else href,
            })

    logger.info(f"CoinTelegraph: {len(articles)} haber")
    return articles


def scrape_coindesk(limit: int = 10) -> list[dict]:
    """CoinDesk son haberler."""
    soup = _get("https://www.coindesk.com/markets")
    if not soup:
        return []

    articles = []
    for el in soup.select("a[href*='/markets/']")[:limit * 2]:
        title = el.get_text(strip=True)
        href = el.get("href", "")
        if title and len(title) > 20:
            articles.append({
                "source": "coindesk",
                "language": "en",
                "title": title,
                "url": f"https://www.coindesk.com{href}" if href.startswith("/") else href,
            })
        if len(articles) >= limit:
            break

    logger.info(f"CoinDesk: {len(articles)} haber")
    return articles


def scrape_btchaber(limit: int = 10) -> list[dict]:
    """BTCHaber — Türkçe."""
    soup = _get("https://btchaber.com")
    if not soup:
        return []

    articles = []
    for a in soup.select("h2 a, h3 a, .entry-title a")[:limit]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if title and len(title) > 10:
            articles.append({
                "source": "btchaber",
                "language": "tr",
                "title": title,
                "url": href,
            })

    logger.info(f"BTCHaber: {len(articles)} haber")
    return articles


def scrape_kriptopara(limit: int = 10) -> list[dict]:
    """KriptoPara — Türkçe."""
    soup = _get("https://kriptopara.com")
    if not soup:
        return []

    articles = []
    for a in soup.select("h2 a, h3 a, .title a")[:limit]:
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if title and len(title) > 10:
            articles.append({
                "source": "kriptopara",
                "language": "tr",
                "title": title,
                "url": href,
            })

    logger.info(f"KriptoPara: {len(articles)} haber")
    return articles


def fetch_cryptopanic(limit: int = 30) -> list[dict]:
    """CryptoPanic public API — ücretsiz, key gerekmez."""
    url = "https://cryptopanic.com/api/v1/posts/?auth_token=public&kind=news&filter=hot"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        articles = []
        for post in data.get("results", [])[:limit]:
            articles.append({
                "source": "cryptopanic",
                "language": "en",
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "currencies": [c["code"] for c in post.get("currencies", [])],
            })
        logger.info(f"CryptoPanic: {len(articles)} haber")
        return articles
    except Exception as e:
        logger.warning(f"CryptoPanic API hatası: {e}")
        return []


def collect_all_news(config: dict = None) -> list[dict]:
    """Tüm kaynaklardan haberleri toplar."""
    if config is None:
        config = {}

    all_articles = []
    all_articles.extend(fetch_cryptopanic(30))
    all_articles.extend(scrape_cointelegraph(8))
    all_articles.extend(scrape_coindesk(8))
    all_articles.extend(scrape_btchaber(8))
    all_articles.extend(scrape_kriptopara(8))

    logger.info(f"Toplam haber: {len(all_articles)}")
    return all_articles
