"""Actualites via les flux RSS de Google Actualites (gratuit, sans cle, non officiel)."""
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

from .cache import cached
from .errors import ProviderError

TTL_NEWS = 30 * 60
URL = "https://news.google.com/rss/search?q={q}&hl=fr&gl=FR&ceid=FR:fr"


def _fetch(query):
    try:
        r = requests.get(URL.format(q=quote_plus(query)), timeout=10,
                         headers={"User-Agent": "Mozilla/5.0 (my-xtb-ultra)"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError) as e:
        raise ProviderError("reseau", "news", "Actualités indisponibles pour le moment.") from e
    items = []
    for it in root.iter("item"):
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).timestamp()
        except (TypeError, ValueError):
            ts = 0
        src = it.find("source")
        items.append({"title": (it.findtext("title") or "").strip(),
                      "link": (it.findtext("link") or "").strip(),
                      "source": src.text.strip() if src is not None and src.text else "",
                      "ts": ts})
    return items[:8]


def latest(symbols):
    queries = [f"{s} action bourse when:7d" for s in symbols[:5]] or ["CAC 40 Wall Street bourse when:2d"]
    merged, seen = [], set()
    for q in queries:
        try:
            items, _ = cached(f"news:{q}", TTL_NEWS, lambda q=q: _fetch(q))
        except ProviderError:
            continue
        for i in items:
            if i["link"] and i["link"] not in seen:
                seen.add(i["link"])
                merged.append(i)
    merged.sort(key=lambda i: i["ts"], reverse=True)
    return merged[:20]
