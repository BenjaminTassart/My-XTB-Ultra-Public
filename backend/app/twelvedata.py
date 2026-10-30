"""Secours de cours américains, un crédit par symbole, sans données inventées."""
import json
import math
import threading
import time
from datetime import date, datetime, timezone

import requests

from . import config, db, quota
from .errors import ProviderError

_lock = threading.Lock()


def _get(path, symbol, **params):
    provider = 'twelvedata'
    if not config.TWELVEDATA_API_KEY:
        raise ProviderError('config', provider, 'Clé Twelve Data absente du serveur.')
    # Fenêtre glissante persistante ; verrou adapté au serveur à un processus.
    with _lock:
        quota.check(provider)
        now = time.time()
        row = db.cache_get('twelvedata:recent-calls')
        recent = [t for t in json.loads(row[0]) if t > now - 60] if row else []
        if len(recent) >= 8:
            raise ProviderError('quota', provider,
                                'Twelve Data : limite locale de 8 appels par minute. Réessaie dans une minute.')
        quota.hit(provider)
        db.cache_set('twelvedata:recent-calls', json.dumps(recent + [now]))
    try:
        response = requests.get('https://api.twelvedata.com/' + path, params={
            **params,
            'symbol': symbol, 'country': 'United States', 'apikey': config.TWELVEDATA_API_KEY,
        }, timeout=15)
    except requests.RequestException as e:
        raise ProviderError('reseau', provider, 'Twelve Data ne répond pas.') from e
    try:
        data = response.json()
    except ValueError:
        data = {}
    code = response.status_code
    if isinstance(data, dict) and data.get('status') == 'error' and code < 400:
        try:
            code = int(data.get('code', 500))
        except (TypeError, ValueError):
            code = 500
    if code == 429:
        # Ne jamais exposer le message brut : il peut contenir la clé.
        msg = str(data.get('message', '')).lower() if isinstance(data, dict) else ''
        daily = any(word in msg for word in ('daily', 'per day', 'a day'))
        quota.exhaust(provider, 'Twelve Data signale une limite quotidienne.' if daily
                      else 'Twelve Data signale une limite temporaire.', retry_seconds=None if daily else 60)
        raise ProviderError('quota', provider, quota.message(provider))
    if code == 401:
        raise ProviderError('config', provider, 'Clé Twelve Data refusée par le fournisseur.')
    if code in (402, 403):
        raise ProviderError('payant', provider, 'Twelve Data : ce cours n’est pas inclus dans ton offre.')
    if code == 404:
        raise ProviderError('inconnu', provider, 'Titre introuvable chez Twelve Data.')
    if code >= 400 or not isinstance(data, dict):
        raise ProviderError('reseau', provider, 'Réponse de Twelve Data indisponible ou illisible.')

    return data


def num(value):
    try:
        result = float(value) if not isinstance(value, bool) else math.nan
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def quote(symbol):
    provider = 'twelvedata'
    data = _get('quote', symbol)

    price = num(data.get('close'))
    if data.get('symbol') != symbol or data.get('currency') != 'USD' or price is None or price <= 0:
        raise ProviderError('reseau', provider, 'Twelve Data n’a pas fourni de cours américain valide pour ce symbole.')
    year = data.get('fifty_two_week') or {}
    if not isinstance(year, dict):
        year = {}
    return {'source': provider, 'currency': 'USD', 'price': price,
            'name': data.get('name'), 'exchange': data.get('exchange'),
            'change': num(data.get('change')), 'changePercent': num(data.get('percent_change')),
            'dayLow': num(data.get('low')), 'dayHigh': num(data.get('high')),
            'yearLow': num(year.get('low')), 'yearHigh': num(year.get('high')),
            'volume': num(data.get('volume')), 'marketCap': None}


def history(symbol):
    today = datetime.now(timezone.utc).date()
    start = today.replace(year=today.year - 5, day=28 if today.month == 2 and today.day == 29 else today.day)
    data = _get('time_series', symbol, interval='1day', outputsize=1500,
                start_date=start.isoformat(), end_date=today.isoformat(), adjust='splits')
    meta = data.get('meta')
    values = data.get('values')
    if (not isinstance(meta, dict) or meta.get('symbol') != symbol or meta.get('currency') != 'USD'
            or meta.get('interval') != '1day' or not isinstance(values, list)):
        raise ProviderError('reseau', 'twelvedata', 'Historique Twelve Data invalide pour ce symbole.')
    points = {}
    for row in values:
        if not isinstance(row, dict):
            continue
        try:
            day = date.fromisoformat(row.get('datetime', ''))
        except (ValueError, TypeError):
            continue
        if not start <= day <= today:
            continue
        o, h, l, c = [num(row.get(k)) for k in ('open', 'high', 'low', 'close')]
        if any(v is None or v <= 0 for v in (o, h, l, c)) or not l <= min(o, c) <= max(o, c) <= h:
            continue
        volume = num(row.get('volume'))
        points[day.isoformat()] = [day.isoformat(), o, h, l, c,
                                  volume if volume is not None and volume >= 0 else None]
    if not points:
        raise ProviderError('reseau', 'twelvedata', 'Aucun point historique valide fourni par Twelve Data.')
    return [points[day] for day in sorted(points)]
