import json
import pytest

from test_api import client, fake_http, financial_data, H, Resp
from app import db, service, providers
from app.errors import ProviderError


def test_position_invested_amount_manual_fx_and_edit(client):
    body = {'symbol': 'AAPL', 'amount': 1000, 'entry_price': 80, 'currency': 'EUR', 'exchange_rate': 1.25}
    response = client.post('/api/positions', json=body, headers=H)
    assert response.status_code == 200
    saved = db.records(db.positions)[0]
    assert saved['quantity'] == 12.5 and saved['entry_price'] == 100 and saved['currency'] == 'USD'
    body = {'symbol': 'AAPL', 'quantity': saved['quantity'], 'entry_price': saved['entry_price'], 'currency': 'USD'}
    assert client.put('/api/positions/' + saved['id'], json=body, headers=H).status_code == 200
    assert db.records(db.positions)[0] == saved


@pytest.mark.parametrize('changes', [{'amount': 100, 'quantity': 1}, {'amount': 100, 'entry_price': 0},
                                   {'quantity': 1, 'exchange_rate': -1}, {'quantity': None}])
def test_invalid_position_inputs(client, changes):
    body = {'symbol': 'AAPL', 'entry_price': 10, **changes}
    assert client.post('/api/positions', json=body, headers=H).status_code == 422
    assert not db.records(db.positions)


def test_automatic_fx_and_stale_refusal(client, monkeypatch):
    body = {'symbol': 'AAPL', 'amount': 900, 'entry_price': 90, 'currency': 'EUR'}
    result = client.post('/api/positions', json=body, headers=H)
    assert result.status_code == 200
    saved = db.records(db.positions)[0]
    assert saved['quantity'] == 10 and saved['entry_price'] == 81  # taux simulé 0,9
    with db.engine.begin() as c:
        c.execute(db.cache.update().where(db.cache.c.key == 'fx:EUR:USD').values(fetched_at=0))
    def unavailable(*a):
        raise ProviderError('reseau', 'fx', 'Indisponible')
    monkeypatch.setattr(providers, 'fx_rate', unavailable)
    assert client.post('/api/positions', json=body, headers=H).status_code == 400
    assert len(db.records(db.positions)) == 1


def test_metrics_partial_and_expired_access_refusal(client, monkeypatch):
    original = providers._fmp
    def partial(path, **kwargs):
        if path == '/key-metrics-ttm':
            raise ProviderError('payant', 'fmp', 'Refus')
        return original(path, **kwargs)
    monkeypatch.setattr(providers, '_fmp', partial)
    first = client.get('/api/stock/AAPL', headers=H).json()
    assert next(i['value'] for i in first['indicators'] if i['key'] == 'per') == 30.1
    with db.engine.begin() as c:
        c.execute(db.cache.update().where(db.cache.c.key == 'metrics:AAPL').values(fetched_at=0))
    def denied(*a, **k):
        raise ProviderError('payant', 'fmp', 'Refus')
    monkeypatch.setattr(providers, 'fmp_metrics', denied)
    second = client.get('/api/stock/AAPL', headers=H).json()
    assert second['indicators'] == first['indicators'] and second['indicators_stale']
    assert not second['quote_stale']


def test_summary_payload_and_refresh_preserves_old_on_failure(client, financial_data, monkeypatch):
    first = client.post('/api/results/AAPL/summary', headers=H).json()
    assert first['prompt_version'] == 2
    prompt = financial_data[0]['json']['contents'][0]['parts'][0]['text']
    payload = json.loads(prompt.split('\n', 1)[1])
    assert all('revenueGrowth' not in r for r in payload['statements'])
    assert payload['variation_derniere_vs_precedente_pourcent']['revenue'] == 20
    assert client.post('/api/results/AAPL/summary', headers=H).json()['cached']
    assert len(financial_data) == 1
    assert client.post('/api/results/AAPL/summary?refresh=true', headers=H).status_code == 200
    assert len(financial_data) == 2
    stored = db.cache_get('summary:AAPL:quarter:2026-06-30')[0]
    monkeypatch.setattr(providers.requests, 'post', lambda *a, **kw: Resp(503, {}))
    assert client.post('/api/results/AAPL/summary?refresh=true', headers=H).status_code == 502
    assert db.cache_get('summary:AAPL:quarter:2026-06-30')[0] == stored
