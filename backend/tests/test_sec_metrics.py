import copy
import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from test_api import client, fake_http, H, Resp
from app import config, db, providers, sec_metrics, service
from app.errors import ProviderError


def facts(cik=1652044):
    year = datetime.now(timezone.utc).year - 1
    accn = f'{cik:010d}-{str(year + 1)[2:]}-000001'
    base = {'start': f'{year}-01-01', 'end': f'{year}-12-31', 'filed': f'{year + 1}-02-01',
            'form': '10-K', 'accn': accn}
    concepts = {}
    for tag, val, unit in [('NetIncomeLoss', 100, 'USD'), ('Revenues', 1000, 'USD'),
                           ('EarningsPerShareDiluted', 5, 'USD/shares'),
                           ('CommonStockDividendsPerShareCashPaid', 1, 'USD/shares')]:
        concepts[tag] = {'units': {unit: [{**base, 'val': val}]}}
    instant = {k: v for k, v in base.items() if k != 'start'}
    concepts['StockholdersEquity'] = {'units': {'USD': [{**instant, 'val': 500},
                                    {**instant, 'end': f'{year - 1}-12-31', 'val': 300}]}}
    concepts['CommonStockSharesOutstanding'] = {'units': {'shares': [{**instant, 'val': 20}]}}
    return {'cik': cik, 'facts': {'us-gaap': concepts}}


def wire(monkeypatch, symbol, payload=None, status=200):
    monkeypatch.setattr(config, 'SEC_USER_AGENT', 'TestApp test@example.com')
    monkeypatch.setattr(config, 'TWELVEDATA_API_KEY', 'test')
    original = providers.requests.get
    seen = []
    def get(url, params=None, **kwargs):
        if 'financialmodelingprep' in url and params['symbol'] == symbol:
            return Resp(403, {})
        if 'twelvedata.com' in url:
            return Resp(200, {'symbol': symbol, 'currency': 'USD', 'close': '100'})
        if 'data.sec.gov' in url:
            seen.append(url)
            assert kwargs['headers']['User-Agent'] == 'TestApp test@example.com'
            return Resp(status, payload if payload is not None else facts(sec_metrics.CIKS[symbol]))
        return original(url, params=params, **kwargs)
    monkeypatch.setattr(providers.requests, 'get', get)
    return seen


@pytest.mark.parametrize('symbol', ['GOOG', 'SNDK'])
def test_sec_indicators_quote_unchanged_and_cache(client, monkeypatch, symbol):
    seen = wire(monkeypatch, symbol)
    first = client.get('/api/stock/' + symbol, headers=H)
    assert first.status_code == 200
    data = first.json()
    values = {i['key']: i['value'] for i in data['indicators']}
    assert values['per'] == 20 and values['netMargin'] == .1 and values['roe'] == .25
    assert values['dividendYield'] == .01 and values['peg'] is None and values['debtToEbitda'] is None
    assert values['pb'] == (4 if symbol == 'SNDK' else None)
    assert data['marketCap'] == (2000 if symbol == 'SNDK' else None)
    assert data['price'] == 100 and data['quote_source'] == 'twelvedata'
    assert data['indicators_source'] == 'SEC (calculs annuels)'
    assert 'annuels' in data['indicators_note'] and data['indicators_url'].startswith('https://www.sec.gov/')
    client.get('/api/stock/' + symbol, headers=H)
    assert len(seen) == 1 and db.usage_get('alphavantage') == 0


def test_missing_sec_contact_does_not_break_stock(client, monkeypatch):
    seen = wire(monkeypatch, 'GOOG')
    monkeypatch.setattr(config, 'SEC_USER_AGENT', '')
    data = client.get('/api/stock/GOOG', headers=H).json()
    assert 'SEC_USER_AGENT' in data['indicators_note'] and data['price'] == 100
    assert seen == []


def test_sec_not_used_by_batch_or_working_fmp(client, monkeypatch):
    seen = wire(monkeypatch, 'GOOG')
    assert service.stock('GOOG')['price'] == 100
    assert not seen
    assert client.get('/api/stock/AAPL', headers=H).status_code == 200
    assert not seen


def test_sec_refusal_cooldown_and_old_cache(client, monkeypatch):
    wire(monkeypatch, 'GOOG')
    first = sec_metrics.calculate('GOOG', 100)
    with db.engine.begin() as c:
        c.execute(db.cache.update().where(db.cache.c.key == 'sec-annual:v1:1652044').values(fetched_at=0))
    seen = wire(monkeypatch, 'GOOG', status=403)
    stale = sec_metrics.calculate('GOOG', 100)
    assert stale['stale'] and stale['values'] == first['values']
    sec_metrics.calculate('GOOG', 100)
    assert len(seen) == 1


def test_sec_rejects_wrong_company(client, monkeypatch):
    wire(monkeypatch, 'GOOG', facts(2023554))
    with pytest.raises(ProviderError, match='Émetteur'):
        sec_metrics.calculate('GOOG', 100)
    assert db.cache_get('sec-annual:v1:1652044') is None


@pytest.mark.parametrize('symbol,cik', [('GOOG', '1652044'), ('GOOG', '0001652044'),
                                      ('SNDK', '0002023554'), ('SNDK', 2023554)])
def test_sec_accepts_numeric_or_text_cik(client, monkeypatch, symbol, cik):
    payload = facts(sec_metrics.CIKS[symbol])
    payload['cik'] = cik
    wire(monkeypatch, symbol, payload)
    result = client.get('/api/stock/' + symbol, headers=H).json()
    assert result['indicators_source'] == 'SEC (calculs annuels)'
    assert next(i['value'] for i in result['indicators'] if i['key'] == 'per') == 20


@pytest.mark.parametrize('cik', [None, True, 1652044.0, '1652044.0', 'CIK1652044',
                               '1652044x', '0000000000', '00001652044', {}, []])
def test_invalid_cik_not_coerced(cik):
    assert sec_metrics.normalized_cik(cik) is None


@pytest.mark.parametrize('symbol,end', [('GOOG', '2025-12-31'), ('SNDK', '2026-07-03')])
def test_real_sec_response_excerpt(client, monkeypatch, symbol, end):
    # Extraits publics téléchargés le 30/10/2026, aucun contact ou secret conservé.
    path = Path(__file__).parent / 'fixtures' / ('sec_' + symbol.lower() + '.json')
    payload = json.loads(path.read_text(encoding='utf-8'))
    wire(monkeypatch, symbol, payload)
    snapshot = sec_metrics._fetch(symbol)
    assert snapshot['end'] == end
    assert snapshot['income'] is not None and snapshot['revenue'] > 0
    assert snapshot['eps'] > 0 and snapshot['equity'] > 0
    result = client.get('/api/stock/' + symbol, headers=H).json()
    values = {i['key']: i['value'] for i in result['indicators']}
    assert values['netMargin'] == pytest.approx(snapshot['income'] / snapshot['revenue'])
    assert values['per'] == pytest.approx(100 / snapshot['eps'])


def test_sec_annual_alignment_and_conflicting_values():
    data = facts()
    gaap = data['facts']['us-gaap']
    row = gaap['NetIncomeLoss']['units']['USD'][0]
    gaap['NetIncomeLoss']['units']['USD'].append({**row, 'start': row['end'][:4] + '-10-01', 'val': 900})
    gaap['Revenues']['units']['USD'][0]['accn'] = '0001652044-20-000001'
    gaap['EarningsPerShareDiluted']['units']['USD/shares'].append(
        {**gaap['EarningsPerShareDiluted']['units']['USD/shares'][0], 'val': 6})
    snapshot = sec_metrics.extract(data)
    assert snapshot['income'] == 100  # pas de mélange trimestre/année
    assert snapshot['revenue'] is None  # pas de mélange de dépôts
    assert snapshot['eps'] is None  # classes ou contextes ambigus


def test_loss_does_not_produce_negative_per(client, monkeypatch):
    data = facts()
    data['facts']['us-gaap']['EarningsPerShareDiluted']['units']['USD/shares'][0]['val'] = -5
    wire(monkeypatch, 'GOOG', data)
    calculated = sec_metrics.calculate('GOOG', 100)
    assert calculated['values']['per'] is None
