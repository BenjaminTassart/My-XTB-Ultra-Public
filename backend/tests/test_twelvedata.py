import json
import time

import pytest

from test_api import client, fake_http, H, Resp
from app import config, db, providers, service, twelvedata
from app.errors import ProviderError
from datetime import datetime, timedelta, timezone


def setup_fallback(monkeypatch, response=None):
    monkeypatch.setattr(config, 'TWELVEDATA_API_KEY', 'private-test-key')
    original = providers.requests.get
    calls = []

    def get(url, params=None, **kwargs):
        if 'financialmodelingprep' in url and params['symbol'] in ('GOOG', 'SNDK'):
            return Resp(403, {})
        if 'api.twelvedata.com' in url:
            if url.endswith('/time_series'):
                assert params['interval'] == '1day' and params['outputsize'] == 1500
                assert params['adjust'] == 'splits' and params['country'] == 'United States'
                assert params['start_date'] < params['end_date']
            calls.append(params['symbol'])
            return response or Resp(200, {'symbol': params['symbol'], 'currency': 'USD',
                'close': '123.45', 'name': 'Company', 'percent_change': '1.25',
                'fifty_two_week': {'low': '80', 'high': '150'}})
        return original(url, params=params, **kwargs)

    monkeypatch.setattr(providers.requests, 'get', get)
    return calls


@pytest.mark.parametrize('symbol', ['GOOG', 'SNDK'])
def test_search_favorite_cache_and_usd(client, monkeypatch, symbol):
    calls = setup_fallback(monkeypatch)
    r = client.get('/api/stock/' + symbol, headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data['symbol'] == symbol and data['price'] == 123.45
    assert data['currency'] == 'USD' and data['marketCap'] is None
    assert any(w['code'] == 'secours' for w in data['warnings'])
    assert client.post('/api/favorites', headers=H, json={'symbol': symbol}).status_code == 200
    favorite = client.get('/api/favorites', headers=H).json()['items'][0]
    assert favorite['currency'] == 'USD' and favorite['price'] == 123.45
    assert calls == [symbol] and db.usage_get('twelvedata') == 1


def test_no_fallback_for_working_fmp_or_missing_key(client, monkeypatch):
    calls = setup_fallback(monkeypatch)
    assert client.get('/api/stock/AAPL', headers=H).status_code == 200
    assert not calls
    monkeypatch.setattr(config, 'TWELVEDATA_API_KEY', '')
    assert client.get('/api/stock/GOOG', headers=H).status_code == 403
    assert not calls


def test_daily_and_minute_limits_prevent_calls(client, monkeypatch):
    calls = setup_fallback(monkeypatch)
    db.usage_set('twelvedata', config.LIMITS['twelvedata'])
    with pytest.raises(ProviderError, match='limite quotidienne'):
        twelvedata.quote('GOOG')
    db.usage_set('twelvedata', 0)
    db.cache_set('twelvedata:recent-calls', json.dumps([time.time()] * 8))
    with pytest.raises(ProviderError, match='8 appels'):
        twelvedata.quote('GOOG')
    assert not calls


@pytest.mark.parametrize('payload', [
    {'symbol': 'GOOGL', 'currency': 'USD', 'close': '123'},
    {'symbol': 'GOOG', 'currency': 'EUR', 'close': '123'},
    {'symbol': 'GOOG', 'currency': 'USD', 'close': 'NaN'},
    {'symbol': 'GOOG', 'currency': 'USD', 'close': None},
])
def test_invalid_quote_never_saved_as_favorite(client, monkeypatch, payload):
    setup_fallback(monkeypatch, Resp(200, payload))
    r = client.post('/api/favorites', headers=H, json={'symbol': 'GOOG'})
    assert r.status_code == 502
    assert not db.list_favorites()


def test_provider_quota_redacted_and_stale_cache(client, monkeypatch):
    calls = setup_fallback(monkeypatch)
    first, _ = service.get_quote('GOOG')
    with db.engine.begin() as c:
        c.execute(db.cache.update().where(db.cache.c.key == 'quote:GOOG').values(fetched_at=0))
    setup_fallback(monkeypatch, Resp(200, {'status': 'error', 'code': 429,
                    'message': 'daily limit private-test-key'}))
    q, stale = service.get_quote('GOOG')
    assert stale and q == first
    assert db.usage_get('twelvedata') == 2
    assert 'private-test-key' not in db.cache_get('quota-block:twelvedata')[0]
    with pytest.raises(ProviderError) as err:
        twelvedata.quote('SNDK')
    assert err.value.kind == 'quota'
    assert db.usage_get('twelvedata') == 2


def history_payload(symbol='GOOG'):
    today = datetime.now(timezone.utc).date()
    return {'meta': {'symbol': symbol, 'currency': 'USD', 'interval': '1day'},
            'values': [{'datetime': (today - timedelta(days=i)).isoformat(),
                        'open': '10', 'high': '12', 'low': '9', 'close': '11', 'volume': '42'}
                       for i in (1, 3, 2)]}


@pytest.mark.parametrize('symbol', ['GOOG', 'SNDK'])
def test_history_fallback_cache_and_format(client, monkeypatch, symbol):
    calls = setup_fallback(monkeypatch, Resp(200, history_payload(symbol)))
    result = client.get('/api/history/' + symbol, headers=H)
    assert result.status_code == 200
    data = result.json()
    assert data['source'] == 'twelvedata' and not data['stale']
    assert len(data['points']) == 3 and data['points'] == sorted(data['points'])
    assert data['points'][0][1:] == [10, 12, 9, 11, 42]
    assert client.get('/api/history/' + symbol, headers=H).json() == data
    assert calls == [symbol] and db.usage_get('twelvedata') == 1


def test_history_legacy_cache_and_fmp_primary(client, monkeypatch):
    calls = setup_fallback(monkeypatch)
    old = [['2026-10-01', 10, 12, 9, 11, 42]]
    db.cache_set('history:GOOG', json.dumps(old))
    assert service.get_history('GOOG') == {'symbol': 'GOOG', 'points': old, 'source': 'fmp', 'stale': False}
    assert service.get_history('AAPL')['source'] == 'fmp'
    assert not calls


@pytest.mark.parametrize('field,value', [('symbol', 'GOOGL'), ('currency', 'EUR'), ('interval', '1min')])
def test_history_wrong_metadata_rejected(client, monkeypatch, field, value):
    payload = history_payload()
    payload['meta'][field] = value
    setup_fallback(monkeypatch, Resp(200, payload))
    assert client.get('/api/history/GOOG', headers=H).status_code == 502
    assert db.cache_get('history:GOOG') is None


def test_history_bad_points_and_quota_cache(client, monkeypatch):
    payload = history_payload()
    payload['values'] += [dict(payload['values'][0], close='NaN'),
                          dict(payload['values'][0], high='8'), {'datetime': 'wrong'}, None]
    setup_fallback(monkeypatch, Resp(200, payload))
    first = service.get_history('GOOG')
    assert len(first['points']) == 3
    with db.engine.begin() as c:
        c.execute(db.cache.update().where(db.cache.c.key == 'history:GOOG').values(fetched_at=0))
    setup_fallback(monkeypatch, Resp(429, {'message': 'minute limit'}))
    stale = service.get_history('GOOG')
    assert stale['stale'] and stale['points'] == first['points']
    assert stale['source'] == 'twelvedata'
    assert 'private-test-key' not in db.cache_get('quota-block:twelvedata')[0]
    with pytest.raises(ProviderError) as err:
        twelvedata.quote('SNDK')
    assert err.value.kind == 'quota'
    assert db.usage_get('twelvedata') == 2
