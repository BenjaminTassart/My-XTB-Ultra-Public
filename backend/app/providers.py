"""Appels aux API de donnees (Financial Modeling Prep + Alpha Vantage en secours pour le prix)."""
import re

import requests

from . import config, quota
from .errors import ProviderError

TIMEOUT = 15
FMP_BASE = "https://financialmodelingprep.com/stable"
AV_BASE = "https://www.alphavantage.co/query"

# Suffixe Yahoo/FMP -> suffixe Alpha Vantage (teste : .PA -> .PAR ; les autres sont a confirmer)
AV_SUFFIX = {".PA": ".PAR", ".L": ".LON", ".DE": ".DEX", ".TO": ".TRT"}
# Bourses hors Etats-Unis (non couvertes par l'offre gratuite FMP d'apres le test de l'etape 0)
FOREIGN_SUFFIX = set(AV_SUFFIX) | {".T", ".HK", ".AS", ".MI", ".MC", ".SW", ".ST", ".OL", ".CO",
                                   ".HE", ".VI", ".BR", ".LS", ".AX", ".KS", ".SS", ".SZ",
                                   ".NS", ".BO", ".SA", ".MX", ".TW"}


# Devise de cotation deduite du suffixe (pour les bourses ou seul le prix est disponible)
CURRENCY_BY_SUFFIX = {".PA": "EUR", ".DE": "EUR", ".AS": "EUR", ".MI": "EUR", ".MC": "EUR", ".BR": "EUR",
                      ".LS": "EUR", ".HE": "EUR", ".VI": "EUR", ".TO": "CAD", ".SW": "CHF", ".ST": "SEK",
                      ".CO": "DKK", ".OL": "NOK", ".T": "JPY", ".HK": "HKD", ".AX": "AUD"}
# (.L absent expres : la Bourse de Londres cote en pence, la devise serait trompeuse)
FX_URL = "https://api.frankfurter.dev/v1/latest"  # taux de la BCE, gratuit, sans cle


def suffix(symbol):
    m = re.search(r"\.[A-Z]+$", symbol)
    return m.group(0) if m else ""


def guess_currency(symbol):
    return CURRENCY_BY_SUFFIX.get(suffix(symbol))


def is_foreign(symbol):
    return suffix(symbol) in FOREIGN_SUFFIX and not config.FMP_COVERS_WORLD


def _norm(k):
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _flat(*dicts):
    out = {}
    for d in dicts:
        if isinstance(d, dict):
            for k, v in d.items():
                if v is not None:
                    out.setdefault(_norm(k), v)
    return out


def _pick(flat, *names):
    for n in names:
        v = flat.get(_norm(n))
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
    return None


def _text(flat, *names):
    for n in names:
        v = flat.get(_norm(n))
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


# ------------------------------------------------------------------ appel HTTP commun
def _get(provider, url, params):
    key = config.FMP_API_KEY if provider == "fmp" else config.ALPHAVANTAGE_API_KEY
    if not key:
        raise ProviderError("config", provider,
                            f"Clé d'API « {provider} » absente : ajoute-la dans les variables d'environnement.")
    quota.check(provider)
    quota.hit(provider)
    try:
        r = requests.get(url, params={**params, "apikey": key}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ProviderError("reseau", provider, "Le fournisseur de données ne répond pas.") from e

    if r.status_code == 429:
        quota.exhaust(provider, 'HTTP 429 : limite de requêtes, durée non précisée.', retry_seconds=300)
        raise ProviderError("quota", provider, quota.message(provider))
    if r.status_code == 401:
        raise ProviderError("config", provider, "Clé d'API refusée par le fournisseur.")
    if r.status_code in (402, 403):
        raise ProviderError("payant", provider,
                            "Cette donnée n'est pas incluse dans l'offre gratuite pour ce titre.")
    if r.status_code == 404:
        raise ProviderError("inconnu", provider, "Titre introuvable.")
    if r.status_code >= 400:
        raise ProviderError("reseau", provider, f"Erreur du fournisseur (HTTP {r.status_code}).")
    try:
        data = r.json()
    except ValueError as e:
        raise ProviderError("reseau", provider, "Réponse illisible du fournisseur.") from e

    if isinstance(data, dict):
        msg = data.get("Error Message") or data.get("Information") or data.get("Note")
        if isinstance(msg, str):
            safe = msg
            for secret in (config.FMP_API_KEY, config.ALPHAVANTAGE_API_KEY):
                if secret:
                    safe = safe.replace(secret, '[clé masquée]')
            safe = re.sub(r'https?://\S+', '[lien masqué]', safe)
            safe = safe[:1000]
            low = msg.lower()
            if any(w in low for w in ("rate limit", "per day", "per minute", "credits", "too many", "per second", "request per second", "requests per second")):
                short_limit = any(w in low for w in ('per minute', 'per second', 'frequency'))
                quota.exhaust(provider, safe, retry_seconds=300 if short_limit else None)
                raise ProviderError("quota", provider, quota.message(provider))
            if any(w in low for w in ("premium", "subscription", "upgrade", "plan")):
                raise ProviderError("payant", provider,
                                    "Cette donnée n'est pas incluse dans l'offre gratuite pour ce titre.")
            if "invalid" in low:
                raise ProviderError("inconnu", provider, "Titre introuvable.")
            raise ProviderError("reseau", provider, "Le fournisseur a renvoyé une erreur.")
    return data


def _first(data, provider="fmp"):
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    raise ProviderError("inconnu", provider, "Titre introuvable.")


def _fmp(path, **params):
    return _get("fmp", FMP_BASE + path, params)


# ------------------------------------------------------------------ FMP
def fmp_quote(symbol):
    f = _flat(_first(_fmp("/quote", symbol=symbol)))
    price = _pick(f, "price")
    if price is None:
        raise ProviderError("inconnu", "fmp", "Titre introuvable.")
    return {
        "source": "fmp", "price": price,
        "change": _pick(f, "change"),
        "changePercent": _pick(f, "changePercentage", "changesPercentage"),
        "dayLow": _pick(f, "dayLow"), "dayHigh": _pick(f, "dayHigh"),
        "yearLow": _pick(f, "yearLow"), "yearHigh": _pick(f, "yearHigh"),
        "volume": _pick(f, "volume"), "marketCap": _pick(f, "marketCap"),
        "name": _text(f, "name"), "exchange": _text(f, "exchange"),
    }


def fmp_profile(symbol):
    f = _flat(_first(_fmp("/profile", symbol=symbol)))
    return {
        "name": _text(f, "companyName"), "logo": _text(f, "image"),
        "sector": _text(f, "sector"), "industry": _text(f, "industry"),
        "country": _text(f, "country"), "currency": _text(f, "currency"),
        "exchange": _text(f, "exchangeFullName", "exchange"),
        "website": _text(f, "website"), "description": _text(f, "description"),
    }


# Indicateurs affiches sur la fiche : (cle, libelle, type d'affichage, noms possibles chez FMP)
INDICATORS = [
    ("per", "PER", "ratio", ["priceToEarningsRatioTTM", "peRatioTTM", "priceEarningsRatioTTM"]),
    ("peg", "PEG", "ratio", ["priceToEarningsGrowthRatioTTM", "priceEarningsToGrowthRatioTTM",
                             "pegRatioTTM", "forwardPriceToEarningsGrowthRatioTTM"]),
    ("pb", "P/B", "ratio", ["priceToBookRatioTTM", "pbRatioTTM", "priceBookValueRatioTTM"]),
    ("dividendYield", "Dividende", "percent", ["dividendYieldTTM", "dividendYieldPercentageTTM"]),
    ("netMargin", "Marge nette", "percent", ["netProfitMarginTTM", "netIncomeMarginTTM"]),
    ("debtToEbitda", "Dette nette / EBITDA", "ratio", ["netDebtToEBITDATTM", "debtToEbitdaTTM"]),
    ("roe", "ROE", "percent", ["returnOnEquityTTM", "roeTTM"]),
]


def fmp_metrics(symbol):
    available, errors = [], []
    for path in ('/key-metrics-ttm', '/ratios-ttm'):
        try:
            available.append(_first(_fmp(path, symbol=symbol)))
        except ProviderError as e:
            errors.append(e)
    if not available:
        raise errors[0]
    f = _flat(*available)
    return [{"key": k, "label": label, "kind": kind, "value": _pick(f, *names)}
            for k, label, kind, names in INDICATORS]


# ------------------------------------------------------------------ Alpha Vantage (prix seulement)
def av_quote(symbol):
    sfx = suffix(symbol)
    av_symbol = symbol[: -len(sfx)] + AV_SUFFIX[sfx] if sfx in AV_SUFFIX else symbol
    data = _get("alphavantage", AV_BASE, {"function": "GLOBAL_QUOTE", "symbol": av_symbol})
    g = data.get("Global Quote") if isinstance(data, dict) else None
    if not g or not g.get("05. price"):
        raise ProviderError("inconnu", "alphavantage", "Titre introuvable.")

    def num(k):
        try:
            return float(str(g.get(k)).replace("%", ""))
        except (TypeError, ValueError):
            return None

    return {
        "source": "alphavantage", "price": num("05. price"), "change": num("09. change"),
        "changePercent": num("10. change percent"), "dayLow": num("04. low"),
        "dayHigh": num("03. high"), "yearLow": None, "yearHigh": None,
        "volume": num("06. volume"), "marketCap": None, "name": None, "exchange": None,
    }


# ------------------------------------------------------------------ historique des prix (FMP)
def fmp_history(symbol):
    """Bougies journalieres, ordre croissant : [date, ouverture, haut, bas, cloture, volume]."""
    data = _fmp("/historical-price-eod/full", symbol=symbol)
    rows = data if isinstance(data, list) else (data.get("historical") if isinstance(data, dict) else None)
    if not rows:
        raise ProviderError("inconnu", "fmp", "Historique introuvable pour ce titre.")
    pts = []
    for r in rows:
        try:
            pts.append([r["date"], float(r["open"]), float(r["high"]), float(r["low"]),
                        float(r["close"]), float(r.get("volume") or 0)])
        except (KeyError, TypeError, ValueError):
            continue
    if not pts:
        raise ProviderError("inconnu", "fmp", "Historique introuvable pour ce titre.")
    pts.sort(key=lambda p: p[0])
    return pts[-1300:]  # environ 5 ans


# ------------------------------------------------------------------ taux de change (Frankfurter / BCE)
def fx_rate(frm, to):
    try:
        r = requests.get(FX_URL, params={"base": frm, "symbols": to}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ProviderError("reseau", "fx", "Taux de change indisponible pour le moment.") from e
    if r.status_code in (404, 422):
        raise ProviderError("inconnu", "fx", "Devise non prise en charge.")
    if r.status_code >= 400:
        raise ProviderError("reseau", "fx", "Taux de change indisponible pour le moment.")
    try:
        d = r.json()
        return {"from": frm, "to": to, "rate": float(d["rates"][to]), "date": d.get("date")}
    except (ValueError, KeyError, TypeError) as e:
        raise ProviderError("inconnu", "fx", "Devise non prise en charge.") from e
