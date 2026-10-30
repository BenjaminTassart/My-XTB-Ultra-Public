import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["ACCESS_CODE"] = "secret"
os.environ["FMP_API_KEY"] = "k"
os.environ["ALPHAVANTAGE_API_KEY"] = "k"
os.environ["TWELVEDATA_API_KEY"] = ""
os.environ['SEC_USER_AGENT'] = ''
os.environ["FMP_DAILY_LIMIT"] = "12"

import pytest
from fastapi.testclient import TestClient

from app import db, providers
from app.main import app

H = {"X-Access-Code": "secret"}


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._d = status, data
        self.content = b""

    def json(self):
        return self._d


FMP = {
    "/quote": [{"symbol": "AAPL", "name": "Apple Inc.", "price": 200.5, "change": 1.2,
                "changePercentage": 0.6, "dayLow": 198, "dayHigh": 201, "yearLow": 150,
                "yearHigh": 230, "volume": 1000, "marketCap": 3e12, "exchange": "NASDAQ"}],
    "/profile": [{"companyName": "Apple Inc.", "image": "http://logo/aapl.png", "sector": "Technology",
                  "industry": "Consumer Electronics", "country": "US", "currency": "USD"}],
    "/key-metrics-ttm": [{"returnOnEquityTTM": 1.5, "netDebtToEBITDATTM": 0.7}],
    "/ratios-ttm": [{"priceToEarningsRatioTTM": 30.1, "priceToEarningsGrowthRatioTTM": 2.2,
                     "priceToBookRatioTTM": 45.0, "dividendYieldTTM": 0.005,
                     "netProfitMarginTTM": 0.24}],
}
FMP["/historical-price-eod/full"] = [
    {"date": f"2026-10-{d:02d}", "open": 100 + d, "high": 102 + d, "low": 99 + d, "close": 101 + d, "volume": 10}
    for d in (3, 2, 1)  # FMP renvoie les plus recentes d'abord
]
calls = []


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    calls.clear()

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(url)
        if "financialmodelingprep" in url:
            path = url.split("/stable")[1]
            sym = params["symbol"]
            if sym == "ZZZZ":
                return Resp(200, [])
            if sym.endswith(".PA"):
                return Resp(402, {})
            return Resp(200, FMP[path])
        if "frankfurter" in url:
            if params["symbols"] == "XXX":
                return Resp(404, {})
            return Resp(200, {"base": params["base"], "date": "2026-10-27", "rates": {params["symbols"]: 0.9}})
        if "alphavantage" in url:
            return Resp(200, {"Global Quote": {"05. price": "600.10", "09. change": "-3.0",
                                               "10. change percent": "-0.50%", "06. volume": "5"}})
        raise AssertionError(url)

    monkeypatch.setattr(providers.requests, "get", fake_get)
    db.init()
    with db.engine.begin() as c:
        for t in (db.favorites, db.cache, db.usage, db.positions, db.alerts, db.subscriptions, db.deliveries, db.screener):
            c.execute(t.delete())


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_acces_protege(client):
    assert client.get("/api/favorites").status_code == 401
    assert client.get("/api/favorites", headers={"X-Access-Code": "non"}).status_code == 401
    assert client.get("/api/auth/check", headers=H).json()["ok"] is True
    assert client.get("/api/health").status_code == 200


def test_favoris_et_fiche(client):
    assert client.post("/api/favorites", json={"symbol": "aapl"}, headers=H).status_code == 200
    items = client.get("/api/favorites", headers=H).json()["items"]
    assert items[0]["symbol"] == "AAPL" and items[0]["price"] == 200.5
    assert items[0]["logo"] == "http://logo/aapl.png"
    s = client.get("/api/stock/AAPL", headers=H).json()
    assert s["favorite"] is True and s["name"] == "Apple Inc."
    ind = {i["key"]: i["value"] for i in s["indicators"]}
    assert ind["per"] == 30.1 and ind["peg"] == 2.2 and ind["roe"] == 1.5 and ind["pb"] == 45.0
    assert client.delete("/api/favorites/AAPL", headers=H).status_code == 200
    assert client.get("/api/favorites", headers=H).json()["items"] == []


def test_cache_evite_les_appels(client):
    client.get("/api/stock/AAPL", headers=H)
    n = len(calls)
    client.get("/api/stock/AAPL", headers=H)
    assert len(calls) == n  # tout vient du cache


def test_titre_inconnu_et_symbole_invalide(client):
    r = client.post("/api/favorites", json={"symbol": "ZZZZ"}, headers=H)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "inconnu"
    assert client.get("/api/stock/A B", headers=H).status_code == 400
    assert client.get("/api/favorites", headers=H).json()["items"] == []


def test_bourse_etrangere_prix_seulement(client):
    s = client.get("/api/stock/MC.PA", headers=H).json()
    assert s["limited"] is True and s["price"] == 600.10
    assert all(i['value'] is None for i in s['indicators'])
    assert s["warnings"][0]["code"] == "limite"
    assert not any("financialmodelingprep" in u for u in calls)


def test_quota_atteint_message_et_cache_de_secours(client):
    client.get("/api/stock/AAPL", headers=H)  # remplit le cache (4 appels)
    db.usage_set("fmp", 12)  # quota epuise
    s = client.get("/api/stock/AAPL", headers=H).json()
    assert s["price"] == 200.5  # cache encore frais
    with db.engine.begin() as c:  # on perime le cache : l'ancien est ressert, marque 'stale'
        c.execute(db.cache.update().values(fetched_at=0))
    s = client.get("/api/stock/AAPL", headers=H).json()
    assert s["stale"] is True and s["price"] == 200.5
    r = client.get("/api/stock/MSFT", headers=H)  # nouveau titre sans cache : erreur quota claire
    assert r.status_code == 429 and r.json()["detail"]["code"] == "quota"
    q = client.get("/api/quota", headers=H).json()["providers"]
    assert q[0]["exhausted"] is True


def test_quota_compte_les_appels(client):
    client.get("/api/stock/AAPL", headers=H)
    assert db.usage_get("fmp") == 4


def test_historique_ordre_croissant_et_cache(client):
    h = client.get("/api/history/AAPL", headers=H).json()
    assert [p[0] for p in h["points"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert h["points"][0][4] == 102.0  # cloture
    n = len(calls)
    client.get("/api/history/AAPL", headers=H)
    assert len(calls) == n  # cache


def test_historique_bourse_etrangere_non_gratuit(client):
    r = client.get("/api/history/MC.PA", headers=H)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "payant"


def test_taux_de_change(client):
    d = client.get("/api/fx?from=USD&to=EUR", headers=H).json()
    assert d["rate"] == 0.9
    assert client.get("/api/fx?from=EUR&to=EUR", headers=H).json()["rate"] == 1.0
    assert client.get("/api/fx?from=us&to=EUR", headers=H).status_code == 400
    n = len(calls)
    client.get("/api/fx?from=USD&to=EUR", headers=H)
    assert len(calls) == n
    assert client.get("/api/fx?from=USD&to=XXX", headers=H).status_code == 404


def test_devise_deduite_pour_bourse_etrangere(client):
    s = client.get("/api/stock/MC.PA", headers=H).json()
    assert s["currency"] == "EUR"
    client.post("/api/favorites", json={"symbol": "MC.PA"}, headers=H)
    items = client.get("/api/favorites", headers=H).json()["items"]
    assert items[0]["currency"] == "EUR"

# Étape 3 : aucune requête réelle, y compris pour les notifications.
def test_positions_crud_conversion_and_validation(client):
    body = {'symbol': 'aapl', 'quantity': 2, 'entry_price': 180, 'currency': 'USD'}
    assert client.post('/api/positions', json=body).status_code == 401
    ident = client.post('/api/positions', json=body, headers=H).json()['id']
    p = client.get('/api/portfolio?currency=EUR', headers=H).json()
    assert p['complete'] and p['total'] == pytest.approx(360.9)
    body['quantity'] = 3
    assert client.put('/api/positions/' + ident, json=body, headers=H).status_code == 200
    assert client.get('/api/portfolio?currency=USD', headers=H).json()['total'] == 601.5
    body['quantity'] = -1
    assert client.post('/api/positions', json=body, headers=H).status_code == 422
    body.update(quantity=1, currency='EUR')
    converted = client.post('/api/positions', json=body, headers=H)
    assert converted.status_code == 200 and converted.json()['conversion']
    client.delete('/api/positions/' + converted.json()['id'], headers=H)
    client.delete('/api/positions/' + ident, headers=H)
    assert client.get('/api/portfolio', headers=H).json()['items'] == []


def test_portfolio_missing_price_not_zero_total(client, monkeypatch):
    from app import service
    from app.errors import ProviderError
    client.post('/api/positions', json={'symbol': 'AAPL', 'quantity': 1, 'entry_price': 0}, headers=H)
    def unavailable(_):
        raise ProviderError('quota', 'fmp', 'Quota atteint')
    monkeypatch.setattr(service, 'get_quote', unavailable)
    p = client.get('/api/portfolio', headers=H).json()
    assert p['total'] is None and not p['complete'] and p['items'][0]['error']


def test_alert_once_rearm_and_no_stale_trigger(client):
    body = {'symbol': 'AAPL', 'threshold': 200, 'direction': 'above', 'currency': 'USD'}
    ident = client.post('/api/alerts', json=body, headers=H).json()['id']
    assert client.post('/api/alerts/check', headers=H).json()['triggered'] == 1
    assert client.post('/api/alerts/check', headers=H).json()['triggered'] == 0
    assert client.get('/api/alerts', headers=H).json()['items'][0]['price'] == 200.5
    client.put('/api/alerts/' + ident, json=body, headers=H)
    with db.engine.begin() as c:
        c.execute(db.cache.update().values(fetched_at=0))
    db.usage_set('fmp', 12)
    result = client.post('/api/alerts/check', headers=H).json()
    assert result['triggered'] == 0 and result['warnings']
    client.delete('/api/alerts/' + ident, headers=H)
    assert client.get('/api/alerts', headers=H).json()['items'] == []


def test_alert_below_and_cron_secret(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'CRON_SECRET', 'cron-test')
    assert client.post('/api/tasks/check-alerts', headers=H).status_code == 403
    client.post('/api/alerts', json={'symbol': 'AAPL', 'threshold': 201, 'direction': 'below'}, headers=H)
    r = client.post('/api/tasks/check-alerts', headers={'X-Cron-Secret': 'cron-test'})
    assert r.status_code == 200 and r.json()['triggered'] == 1


def test_push_retry_and_deduplication(client, monkeypatch):
    import json
    from app import portfolio, config
    monkeypatch.setattr(config, 'VAPID_PUBLIC_KEY', 'public')
    monkeypatch.setattr(config, 'VAPID_PRIVATE_KEY', 'private')
    monkeypatch.setattr(config, 'VAPID_SUBJECT', 'mailto:test@example.com')
    with db.engine.begin() as c:
        c.execute(db.subscriptions.insert().values(id='test-device', payload=json.dumps({})))
    client.post('/api/alerts', json={'symbol': 'AAPL', 'threshold': 200, 'direction': 'above'}, headers=H)
    def fail(*_):
        raise RuntimeError('network')
    monkeypatch.setattr(portfolio, 'send_notification', fail)
    assert client.post('/api/alerts/check', headers=H).json()['warnings']
    sent = []
    monkeypatch.setattr(portfolio, 'send_notification', lambda *args: sent.append(args))
    assert client.post('/api/alerts/check', headers=H).json()['sent'] == 1
    assert client.post('/api/alerts/check', headers=H).json()['sent'] == 0
    assert len(sent) == 1


def test_push_endpoint_security(client):
    r = client.post('/api/push/subscribe', json={'endpoint': 'https://127.0.0.1/private', 'keys': {}}, headers=H)
    assert r.status_code == 422

def test_generated_keys_and_push_subscription_lifecycle(client, monkeypatch):
    import base64
    import subprocess
    import sys
    from pathlib import Path
    from py_vapid import Vapid
    from app import config
    output = subprocess.check_output([sys.executable, str(Path(__file__).parents[1] / 'generate_push_keys.py')], text=True)
    values = dict(line.split('=', 1) for line in output.splitlines())
    # Ne jamais afficher ces clés éphémères dans la sortie des tests.
    Vapid.from_string(values['VAPID_PRIVATE_KEY'])
    monkeypatch.setattr(config, 'VAPID_PUBLIC_KEY', values['VAPID_PUBLIC_KEY'])
    monkeypatch.setattr(config, 'VAPID_PRIVATE_KEY', values['VAPID_PRIVATE_KEY'])
    monkeypatch.setattr(config, 'VAPID_SUBJECT', 'mailto:test@example.com')
    sub = {'endpoint': 'https://fcm.googleapis.com/fcm/send/test',
           'keys': {'p256dh': values['VAPID_PUBLIC_KEY'], 'auth': base64.urlsafe_b64encode(b'x' * 16).decode()}}
    assert client.post('/api/push/subscribe', json=sub, headers=H).status_code == 200
    assert client.post('/api/push/subscribe', json=sub, headers=H).status_code == 200
    assert len(db.records(db.subscriptions)) == 1
    assert client.get('/api/push/config', headers=H).json()['enabled']
    assert client.post('/api/push/unsubscribe', json=sub, headers=H).status_code == 200
    assert db.records(db.subscriptions) == []


def test_multiple_alerts_share_quote_and_foreign_portfolio(client):
    for direction in ('above', 'below'):
        client.post('/api/alerts', json={'symbol': 'AAPL', 'threshold': 200, 'direction': direction}, headers=H)
    with db.engine.begin() as c:
        c.execute(db.cache.update().values(fetched_at=0))
    calls.clear()
    client.post('/api/alerts/check', headers=H)
    assert len(calls) == 1
    response = client.post('/api/positions', json={'symbol': 'MC.PA', 'quantity': 2, 'entry_price': 500, 'currency': 'EUR'}, headers=H)
    assert response.status_code == 200
    p = client.get('/api/portfolio?currency=EUR', headers=H).json()
    assert p['total'] == pytest.approx(1200.2)


def test_provider_quota_refusal_does_not_inflate_usage(client, monkeypatch):
    from app import quota
    quota.hit('alphavantage')
    quota.exhaust('alphavantage')
    q = client.get('/api/quota', headers=H).json()['providers'][1]
    assert q['used'] == 1 and q['provider_blocked'] and q['exhausted']
    assert q['reset_at'].endswith('+00:00')
    from app.errors import ProviderError
    with pytest.raises(ProviderError):
        quota.check('alphavantage')
    monkeypatch.setattr(db, 'today', lambda: '2099-01-01')
    quota.check('alphavantage')
    assert db.usage_get('alphavantage') == 0
    assert not quota.blocked('alphavantage')

@pytest.fixture
def financial_data(monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'GEMINI_API_KEY', 'fake-key')
    monkeypatch.setitem(FMP, '/income-statement', [
        {'date': '2026-06-30', 'period': 'Q2', 'reportedCurrency': 'USD', 'revenue': 120, 'netIncome': -5, 'epsDiluted': -0.1},
        {'date': '2026-03-31', 'period': 'Q1', 'reportedCurrency': 'USD', 'revenue': 100, 'netIncome': -10, 'epsDiluted': -0.2}])
    monkeypatch.setitem(FMP, '/earnings', [
        {'date': '2026-07-25', 'epsActual': -0.1, 'epsEstimated': -0.2, 'revenueActual': 120, 'revenueEstimated': 130},
        {'date': '2099-07-25', 'epsActual': None, 'epsEstimated': 5}])
    posted = []
    def post(*args, **kwargs):
        posted.append(kwargs)
        return Resp(200, {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Ce qui change : la perte diminue.\nLimites : perspectives non déductibles.'}]}}]})
    monkeypatch.setattr(providers.requests, 'post', post)
    return posted


def test_results_growth_consensus_cache_and_auth(client, financial_data):
    assert client.get('/api/results/AAPL').status_code == 401
    assert client.get('/api/results/AAPL?period=bad', headers=H).status_code == 422
    r = client.get('/api/results/AAPL', headers=H).json()
    assert r['rows'][0]['revenueGrowth'] == 20
    assert r['rows'][0]['netIncomeGrowth'] == 50
    assert r['earnings'][0]['epsResult'] == 'beat'
    assert r['earnings'][0]['revenueResult'] == 'miss'
    assert len(r['earnings']) == 1 and r['summary'] is None
    n = len(calls)
    client.get('/api/results/AAPL', headers=H)
    assert len(calls) == n and not financial_data
    assert client.get('/api/results/MC.PA', headers=H).status_code == 403


def test_summary_only_post_and_persistent_cache(client, financial_data, monkeypatch):
    from app import config
    url = '/api/results/AAPL/summary'
    assert client.post(url).status_code == 401
    first = client.post(url, headers=H).json()
    assert first['cached'] is False and len(financial_data) == 1
    monkeypatch.setattr(config, 'GEMINI_API_KEY', '')
    second = client.post(url, headers=H).json()
    assert second['cached'] and second['text'] == first['text'] and len(financial_data) == 1
    assert client.get('/api/results/AAPL', headers=H).json()['summary']['text'] == first['text']
    assert db.usage_get('gemini') == 1


def test_summary_quota_and_invalid_response_not_cached(client, financial_data, monkeypatch):
    monkeypatch.setattr(providers.requests, 'post', lambda *a, **k: Resp(429, {}))
    assert client.post('/api/results/AAPL/summary', headers=H).status_code == 429
    assert client.get('/api/results/AAPL', headers=H).json()['summary'] is None
    assert db.usage_get('gemini') == 1
    assert client.post('/api/results/AAPL/summary', headers=H).status_code == 429
    assert db.usage_get('gemini') == 1


def test_summary_refuses_incomplete_and_stale_data(client, financial_data, monkeypatch):
    client.get('/api/results/AAPL', headers=H)
    with db.engine.begin() as c:
        c.execute(db.cache.update().values(fetched_at=0))
    db.usage_set('fmp', 12)
    assert client.post('/api/results/AAPL/summary', headers=H).status_code == 502
    assert not financial_data


def test_annual_and_zero_base(client, financial_data, monkeypatch):
    monkeypatch.setitem(FMP, '/income-statement', [
        {'date': '2025-12-31', 'period': 'FY', 'reportedCurrency': 'USD', 'revenue': 100, 'netIncome': 0},
        {'date': '2024-12-31', 'period': 'FY', 'reportedCurrency': 'USD', 'revenue': 0, 'netIncome': -10}])
    r = client.get('/api/results/AAPL?period=annual', headers=H).json()
    assert len(r['rows']) == 2 and r['rows'][0]['revenueGrowth'] is None
    assert r['rows'][0]['netIncomeGrowth'] == 100


def test_summary_malformed_response_and_missing_key(client, financial_data, monkeypatch):
    from app import config
    monkeypatch.setattr(config, 'GEMINI_API_KEY', '')
    assert client.post('/api/results/AAPL/summary', headers=H).status_code == 500
    assert not financial_data
    monkeypatch.setattr(config, 'GEMINI_API_KEY', 'fake')
    monkeypatch.setattr(providers.requests, 'post', lambda *a, **k: Resp(200, {'candidates': []}))
    assert client.post('/api/results/AAPL/summary', headers=H).status_code == 502
    assert client.get('/api/results/AAPL', headers=H).json()['summary'] is None


def test_consensus_unavailable_keeps_statements(client, financial_data, monkeypatch):
    from app import results
    from app.errors import ProviderError
    def unavailable(_):
        raise ProviderError('payant', 'fmp', 'Consensus non inclus')
    monkeypatch.setattr(results, 'consensus', unavailable)
    r = client.get('/api/results/AAPL', headers=H).json()
    assert r['rows'] and not r['earnings'] and r['warnings']


def test_summary_revision_is_flagged_without_regeneration(client, financial_data):
    import json
    client.post('/api/results/AAPL/summary', headers=H)
    row = db.cache_get('results:AAPL:quarter')
    changed = json.loads(row[0])
    changed[0]['revenue'] = 130
    db.cache_set('results:AAPL:quarter', json.dumps(changed))
    r = client.post('/api/results/AAPL/summary', headers=H).json()
    assert r['data_changed'] and len(financial_data) == 1


def test_results_fmp_denied_falls_back_to_av_shared_cache(client, monkeypatch):
    from app import results
    from app.errors import ProviderError
    def denied(*args):
        raise ProviderError('payant', 'fmp', 'Refus')
    monkeypatch.setattr(results, 'statements', denied)
    monkeypatch.setattr(results, 'consensus', denied)
    seen = []
    def fetch(url, params=None, **kwargs):
        seen.append(params['function'])
        return Resp(200, {'annualReports': [
            {'fiscalDateEnding': '2025-12-31', 'reportedCurrency': 'USD', 'totalRevenue': '100', 'netIncome': '-10'}],
            'quarterlyReports': [
            {'fiscalDateEnding': '2026-06-30', 'reportedCurrency': 'USD', 'totalRevenue': '50', 'netIncome': 'None'},
            {'fiscalDateEnding': '2026-03-31', 'reportedCurrency': 'USD', 'totalRevenue': '40', 'netIncome': '5'}]})
    monkeypatch.setattr(providers.requests, 'get', fetch)
    r = client.get('/api/results/AAPL', headers=H).json()
    assert r['source'] == 'Alpha Vantage' and r['rows'][0]['revenueGrowth'] == 25
    assert r['rows'][0]['eps'] is None and r['rows'][0]['netIncome'] is None
    a = client.get('/api/results/AAPL?period=annual', headers=H).json()
    assert a['rows'][0]['revenue'] == 100 and len(seen) == 1
    assert db.usage_get('alphavantage') == 1


def test_results_fallback_respects_av_quota(client, monkeypatch):
    from app import results
    from app.errors import ProviderError
    monkeypatch.setattr(results, 'statements', lambda *a: (_ for _ in ()).throw(ProviderError('payant', 'fmp', 'Refus')))
    db.usage_set('alphavantage', 25)
    r = client.get('/api/results/AAPL', headers=H)
    assert r.status_code == 429 and 'FMP' in r.json()['detail']['message']
    assert not calls


def test_temporary_provider_limit_expires_without_resetting_count(client, monkeypatch):
    from app import quota
    now = 1000
    monkeypatch.setattr(quota.time, 'time', lambda: now)
    quota.hit('alphavantage')
    quota.exhaust('alphavantage', 'Temporary limit', retry_seconds=300)
    assert quota.blocked('alphavantage')
    now = 1301
    assert not quota.blocked('alphavantage')
    assert db.usage_get('alphavantage') == 1


def test_provider_refusal_reason_redacts_key_and_short_limit(client, monkeypatch):
    from app import config, quota
    monkeypatch.setattr(config, 'ALPHAVANTAGE_API_KEY', 'private-test-secret')
    monkeypatch.setattr(providers.requests, 'get', lambda *a, **k: Resp(200, {
        'Information': 'Please spread requests: 1 request per second. Key private-test-secret. https://example.com/?apikey=private-test-secret'}))
    r = client.get('/api/stock/MC.PA', headers=H)
    assert r.status_code == 429
    q = client.get('/api/quota', headers=H).json()['providers'][1]
    assert q['retry_at'] and q['used'] == 1
    assert 'private-test-secret' not in q['last_refusal'] and 'https://' not in q['last_refusal']


def test_legacy_diagnostic_one_counted_request(client):
    from app import quota
    quota.hit('alphavantage')
    quota.exhaust('alphavantage')
    assert client.post('/api/quota/alphavantage/diagnose').status_code == 401
    assert client.post('/api/quota/alphavantage/diagnose', headers=H).status_code == 200
    assert db.usage_get('alphavantage') == 2 and not quota.blocked('alphavantage')
    client.post('/api/quota/alphavantage/diagnose', headers=H)
    assert db.usage_get('alphavantage') == 2


def test_legacy_diagnostic_refusal_records_detail_once(client, monkeypatch):
    from app import quota
    quota.exhaust('alphavantage')
    monkeypatch.setattr(providers.requests, 'get', lambda *a, **k: Resp(200, {'Information': 'Daily rate limit: 25 requests per day.'}))
    assert client.post('/api/quota/alphavantage/diagnose', headers=H).status_code == 429
    q = client.get('/api/quota', headers=H).json()['providers'][1]
    assert q['last_refusal'] and q['used'] == 1
    client.post('/api/quota/alphavantage/diagnose', headers=H)
    assert db.usage_get('alphavantage') == 1


def test_legacy_diagnostic_never_overrides_local_cap(client):
    from app import quota
    quota.exhaust('alphavantage')
    db.usage_set('alphavantage', 25)
    assert client.post('/api/quota/alphavantage/diagnose', headers=H).status_code == 429
    assert not calls and db.usage_get('alphavantage') == 25


def test_screener_local_filter_sort_and_pagination(client):
    import json
    import time
    from app import screener
    with db.engine.begin() as c:
        for i, symbol in enumerate(screener.SYMBOLS):
            data = {'symbol': symbol, 'name': symbol, 'logo': None, 'marketCap': 1000 + i,
                    'currency': 'USD', 'sector': 'Technology', 'country': 'US',
                    'indicators': [{'key': 'per', 'value': 10}, {'key': 'pb', 'value': 2},
                                   {'key': 'dividendYield', 'value': None}, {'key': 'peg', 'value': 1}, {'key': 'roe', 'value': .2}]}
            c.execute(db.screener.insert().values(symbol=symbol, attempted_at=time.time(), updated_at=time.time(),
                payload=json.dumps(data), sector='Technology', country='US', market_cap=1000 + i))
    start = time.monotonic()
    r = client.get('/api/screener?preset=value&sector=Technology&region=US', headers=H).json()
    assert time.monotonic() - start < 10
    assert len(r['items']) == 50 and r['total'] == 55 and r['next_offset'] == 50
    assert r['items'][0]['marketCap'] == 1054
    last = client.get('/api/screener?offset=50', headers=H).json()
    assert len(last['items']) == 5 and last['next_offset'] is None
    assert not set(x['symbol'] for x in r['items']) & set(x['symbol'] for x in last['items'])
    assert client.get('/api/screener?preset=dividend', headers=H).json()['items'] == []
    assert client.get('/api/screener?preset=growth', headers=H).json()['total'] == 55
    assert client.get('/api/screener?region=other', headers=H).json()['items'] == []
    assert not calls


def test_screener_refresh_budget_rotation_and_auth(client, monkeypatch):
    from app import config
    monkeypatch.setitem(config.LIMITS, 'fmp', 250)
    assert client.get('/api/screener').status_code == 401
    assert client.post('/api/screener/refresh').status_code == 401
    assert client.post('/api/tasks/refresh-screener', headers=H).status_code == 403
    first = client.post('/api/screener/refresh', headers=H).json()
    assert first['updated'] == 5 and first['calls'] == 20
    second = client.post('/api/screener/refresh', headers=H).json()
    assert second['updated'] == 5 and db.usage_get('screener') == 40
    n = len(calls)
    third = client.post('/api/screener/refresh', headers=H).json()
    assert third['updated'] == 0 and third['warnings'] and len(calls) == n
    assert client.get('/api/screener', headers=H).json()['loaded'] == 10


def test_screener_reserve_and_validation(client):
    # Avec la limite de test à 12, la réserve interdit tout appel.
    result = client.post('/api/screener/refresh', headers=H).json()
    assert result['updated'] == 0 and result['warnings'] and not calls
    assert client.get('/api/screener?offset=-1', headers=H).status_code == 422
    assert client.get('/api/screener?preset=free', headers=H).status_code == 422
    assert client.get('/api/screener?sector=invalid', headers=H).status_code == 400


def test_screener_refresh_failure_preserves_snapshot(client, monkeypatch):
    import json
    from app import config, screener, service
    from app.errors import ProviderError
    monkeypatch.setitem(config.LIMITS, 'fmp', 250)
    monkeypatch.setattr(screener, 'SYMBOLS', ['AAPL'])
    with db.engine.begin() as c:
        c.execute(db.screener.insert().values(symbol='AAPL', attempted_at=0, updated_at=1,
            payload=json.dumps({'symbol': 'AAPL', 'marketCap': 100, 'indicators': []}), market_cap=100))
    def fail(_):
        raise ProviderError('payant', 'fmp', 'Accès refusé')
    monkeypatch.setattr(service, 'stock', fail)
    assert client.post('/api/screener/refresh', headers=H).json()['updated'] == 0
    r = client.get('/api/screener', headers=H).json()
    assert r['loaded'] == 1 and r['items'][0]['marketCap'] == 100
    assert r['items'][0]['outdated'] and r['items'][0]['refresh_error']


def test_export_personal_data_without_secrets_or_requests(client):
    import json
    client.post('/api/favorites', json={'symbol': 'AAPL'}, headers=H)
    client.post('/api/positions', json={'symbol': 'AAPL', 'quantity': 2, 'entry_price': 180}, headers=H)
    db.cache_set('summary:AAPL:quarter:2026-06-30', json.dumps({'text': 'Résumé conservé'}))
    db.cache_set('quota-block:alphavantage', json.dumps({'reason': 'private diagnostic'}))
    with db.engine.begin() as c:
        c.execute(db.subscriptions.insert().values(id='private', payload='private endpoint'))
    before = len(calls)
    assert client.get('/api/data/export').status_code == 401
    response = client.get('/api/data/export', headers=H)
    data = response.json()
    assert data['version'] == 1 and data['favorites'][0]['symbol'] == 'AAPL'
    assert data['positions'][0]['quantity'] == 2 and data['summaries'][0]['value']['text']
    assert 'private' not in response.text and 'subscriptions' not in data and len(calls) == before


def test_delete_requires_confirmation_and_scope_preserves_other_data(client):
    import json
    db.add_favorite('AAPL')
    with db.engine.begin() as c:
        c.execute(db.positions.insert().values(id='test', symbol='AAPL', quantity=1, entry_price=2, currency='USD'))
    db.cache_set('summary:test', json.dumps({'text': 'keep'}))
    db.usage_set('fmp', 7)
    assert client.post('/api/data/delete', json={'scope': 'favorites', 'confirmation': 'SUPPRIMER'}).status_code == 401
    assert client.post('/api/data/delete', json={'scope': 'favorites', 'confirmation': 'oui'}, headers=H).status_code == 400
    assert db.list_favorites() == ['AAPL']
    assert client.post('/api/data/delete', json={'scope': 'everything', 'confirmation': 'SUPPRIMER'}, headers=H).status_code == 422
    assert client.post('/api/data/delete', json={'scope': 'favorites', 'confirmation': 'SUPPRIMER'}, headers=H).status_code == 200
    assert not db.list_favorites() and len(db.records(db.positions)) == 1
    assert db.cache_get('summary:test') and db.usage_get('fmp') == 7


def test_delete_all_personal_preserves_quota_and_market_cache(client):
    import json
    db.add_favorite('AAPL')
    db.cache_set('summary:test', json.dumps({'text': 'remove'}))
    db.cache_set('quote:AAPL', json.dumps({'price': 12}))
    db.usage_set('alphavantage', 25)
    with db.engine.begin() as c:
        c.execute(db.alerts.insert().values(id='a', symbol='AAPL', threshold=10, direction='above', currency='USD'))
        c.execute(db.subscriptions.insert().values(id='s', payload='{}'))
        c.execute(db.deliveries.insert().values(id='a:s', sent_at=1))
    r = client.post('/api/data/delete', json={'scope': 'personal', 'confirmation': 'SUPPRIMER'}, headers=H)
    assert r.status_code == 200
    for table in (db.favorites, db.positions, db.alerts, db.subscriptions, db.deliveries):
        assert db.records(table) == []
    assert db.cache_get('summary:test') is None
    assert db.cache_get('quote:AAPL') and db.usage_get('alphavantage') == 25


def test_full_backup_read_only_and_no_overwrite(client, tmp_path):
    import json
    from backup_database import backup
    db.add_favorite('AAPL')
    path = tmp_path / 'backup.json'
    backup(path)
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['tables']['favorites'][0]['symbol'] == 'AAPL'
    assert 'cache' in data['tables'] and 'push_subscriptions' in data['tables']
    with pytest.raises(FileExistsError):
        backup(path)
    assert db.list_favorites() == ['AAPL']


def test_full_backup_restore_roundtrip_and_nonempty_refusal(client, tmp_path):
    from backup_database import backup
    from restore_database import restore
    db.add_favorite('AAPL')
    db.usage_set('fmp', 9)
    path = tmp_path / 'full.json'
    backup(path)
    with pytest.raises(ValueError, match='vide'):
        restore(path)
    with db.engine.begin() as c:
        for table in reversed(db.metadata.sorted_tables):
            c.execute(table.delete())
    restore(path)
    assert db.list_favorites() == ['AAPL'] and db.usage_get('fmp') == 9
