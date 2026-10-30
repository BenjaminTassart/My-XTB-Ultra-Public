"""Recherche locale uniquement ; enrichissement FMP borné et séparé de la consultation."""
import json
import math
import secrets
import threading
import time
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select, update, insert
from . import config, db, quota, service
from .errors import ProviderError
from .universe import SECTORS, SYMBOLS

_lock = threading.Lock()
DAILY_BUDGET = 40
RESERVE = 50
TTL = 24 * 3600


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def matches(data, preset):
    values = {i['key']: i.get('value') for i in data.get('indicators', [])}
    def between(key, low, high):
        v = values.get(key)
        return finite(v) and low < v <= high
    if preset == 'value':
        return between('per', 0, 20) and between('pb', 0, 3)
    if preset == 'growth':
        return between('peg', 0, 2) and between('roe', 0.15, 10)
    if preset == 'dividend':
        v = values.get('dividendYield')
        return finite(v) and v >= 0.02
    return True


def listing(sector, region, preset, offset):
    # L’univers est volontairement petit : le filtrage reste intégralement local.
    stored = [r for r in db.records(db.screener) if r['symbol'] in SYMBOLS]
    items = []
    loaded = 0
    for row in stored:
        if not row['payload']:
            continue
        loaded += 1
        d = json.loads(row['payload'])
        if sector and row['sector'] != sector:
            continue
        if region == 'US' and row['country'] != 'US':
            continue
        if region == 'other' and (not row['country'] or row['country'] == 'US'):
            continue
        if not matches(d, preset):
            continue
        items.append({**d, 'updated_at': row['updated_at'],
            'outdated': time.time() - row['updated_at'] >= TTL, 'refresh_error': row['error']})
    # La sélection ne conserve que des capitalisations USD, comparables entre elles.
    items.sort(key=lambda d: (-d['marketCap'], d['symbol']))
    page = items[offset:offset + 50]
    return {'items': page, 'total': len(items), 'next_offset': offset + 50 if offset + 50 < len(items) else None,
        'loaded': loaded, 'universe_size': len(SYMBOLS), 'failed': sum(bool(r['error']) for r in stored),
        'daily_calls': db.usage_get('screener'), 'daily_budget': DAILY_BUDGET,
        'sectors': [{'id': k, 'label': v[0]} for k, v in SECTORS.items()]}


def refresh():
    if not _lock.acquire(blocking=False):
        return {'busy': True, 'updated': 0, 'warnings': []}
    try:
        existing = {r['symbol']: r for r in db.records(db.screener)}
        candidates = [s for s in SYMBOLS if not existing.get(s) or time.time() - existing[s]['attempted_at'] >= TTL]
        candidates.sort(key=lambda s: (existing.get(s, {}).get('attempted_at', 0), s))
        updated, warnings, consumed = 0, [], 0
        for symbol in candidates[:5]:
            # Au maximum quatre appels par titre : prix, profil, deux jeux de ratios.
            if db.usage_get('screener') + 4 > DAILY_BUDGET:
                warnings.append('Budget quotidien de la recherche atteint. Reprise à la prochaine journée UTC.')
                break
            if config.LIMITS['fmp'] - db.usage_get('fmp') < RESERVE + 4 or quota.blocked('fmp'):
                warnings.append('Quota FMP insuffisant : 50 appels sont réservés aux autres fonctions.')
                break
            before = db.usage_get('fmp')
            values = {'attempted_at': time.time(), 'error': None}
            try:
                data = service.stock(symbol)
                if data['stale'] or data['warnings']:
                    raise ProviderError('reseau', 'fmp', 'Données incomplètes ou périmées ; ancienne version conservée. ' + ' '.join(w['message'] for w in data['warnings']))
                if data['currency'] != 'USD' or not finite(data['marketCap']) or data['marketCap'] <= 0:
                    raise ProviderError('inconnu', 'fmp', 'Capitalisation en USD indisponible ; titre non classé.')
                # Projection minimale : pas de description ni de détail de séance dans la liste.
                small = {k: data[k] for k in ('symbol', 'name', 'logo', 'sector', 'country', 'currency', 'marketCap', 'indicators')}
                values.update(payload=json.dumps(small), sector=data['sector'], country=data['country'],
                              market_cap=data['marketCap'], updated_at=time.time())
                updated += 1
            except ProviderError as e:
                values['error'] = e.message
                warnings.append(symbol + ' : ' + e.message)
            finally:
                cost = max(0, db.usage_get('fmp') - before)
                db.usage_add('screener', cost)
                consumed += cost
            with db.engine.begin() as c:
                result = c.execute(update(db.screener).where(db.screener.c.symbol == symbol).values(**values))
                if not result.rowcount:
                    c.execute(insert(db.screener).values(symbol=symbol, **values))
        return {'busy': False, 'updated': updated, 'calls': consumed, 'warnings': warnings}
    finally:
        _lock.release()


def router(require_code):
    r = APIRouter(prefix='/api', dependencies=[Depends(require_code)])

    @r.get('/screener')
    def get_screener(sector: str = '', region: Literal['all', 'US', 'other'] = 'all',
                     preset: Literal['all', 'value', 'growth', 'dividend'] = 'all', offset: int = Query(default=0, ge=0, le=10000)):
        if sector and sector not in SECTORS:
            raise HTTPException(400, 'Secteur inconnu.')
        return listing(sector, region, preset, offset)

    @r.post('/screener/refresh')
    def refresh_screener():
        return refresh()
    return r


def cron_refresh(x_cron_secret: str | None = Header(default=None)):
    if not config.CRON_SECRET or not secrets.compare_digest(config.CRON_SECRET, x_cron_secret or ''):
        raise HTTPException(403, 'Secret de planification invalide.')
    return refresh()
