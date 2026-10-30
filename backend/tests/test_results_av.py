import json

from test_api import client, fake_http, financial_data, H, Resp
from app import config, db, providers, results
from app.errors import ProviderError


def av_only(monkeypatch, quarters=None, years=None):
    def denied(*args):
        raise ProviderError('payant', 'fmp', 'Refus FMP')
    monkeypatch.setattr(results, 'statements', denied)
    monkeypatch.setattr(results, 'consensus', denied)
    requests = []
    def get(url, params=None, **kwargs):
        requests.append(params['function'])
        return Resp(200, {'quarterlyReports': quarters or [], 'annualReports': years or []})
    monkeypatch.setattr(providers.requests, 'get', get)
    return requests


def annual_rows():
    return [{'fiscalDateEnding': f'{year}-12-31', 'reportedCurrency': 'USD',
             'totalRevenue': revenue, 'netIncome': '10'}
            for year, revenue in [(2025, '120'), (2024, '100')]]


def test_missing_quarters_offer_annual_and_summary_works(client, financial_data, monkeypatch):
    requests = av_only(monkeypatch, years=annual_rows())
    quarterly = client.get('/api/results/GOOG', headers=H).json()
    assert quarterly['rows'] == [] and quarterly['alternative_period'] == 'annual'
    assert quarterly['summary_unavailable']
    annual = client.get('/api/results/GOOG?period=annual', headers=H).json()
    assert annual['source'] == 'Alpha Vantage' and len(annual['rows']) == 2
    assert annual['rows'][0]['eps'] is None and annual['summary_unavailable'] is None
    assert annual['consensus_warning'] and not annual['earnings']
    generated = client.post('/api/results/GOOG/summary?period=annual', headers=H)
    assert generated.status_code == 200 and generated.json()['text']
    assert requests == ['INCOME_STATEMENT'] and len(financial_data) == 1
    assert 'null' in financial_data[0]['json']['contents'][0]['parts'][0]['text']


def test_missing_income_explains_summary_block_without_gemini_call(client, financial_data, monkeypatch):
    rows = annual_rows()
    rows[0]['netIncome'] = 'None'
    av_only(monkeypatch, years=rows)
    report = client.get('/api/results/GOOG?period=annual', headers=H).json()
    assert report['rows'][0]['netIncome'] is None
    assert 'résultat net' in report['summary_unavailable']
    assert client.post('/api/results/GOOG/summary?period=annual', headers=H).status_code == 404
    assert not financial_data


def test_missing_gemini_key_report_explains_configuration(client, monkeypatch):
    monkeypatch.setattr(config, 'GEMINI_API_KEY', '')
    av_only(monkeypatch, years=annual_rows())
    report = client.get('/api/results/GOOG?period=annual', headers=H).json()
    assert 'GEMINI_API_KEY' in report['summary_unavailable']


def test_stale_consensus_does_not_block_fresh_statement_summary(client, financial_data, monkeypatch):
    client.get('/api/results/AAPL', headers=H)
    with db.engine.begin() as c:
        c.execute(db.cache.update().where(db.cache.c.key == 'earnings:AAPL').values(fetched_at=0))
    def unavailable(*args):
        raise ProviderError('reseau', 'fmp', 'Indisponible')
    monkeypatch.setattr(results, 'consensus', unavailable)
    data = client.get('/api/results/AAPL', headers=H).json()
    assert data['consensus_stale'] and not data['stale']
    assert data['summary_unavailable'] is None
    assert client.post('/api/results/AAPL/summary', headers=H).status_code == 200


def test_empty_fmp_statements_use_av(client, financial_data, monkeypatch):
    requests = av_only(monkeypatch, years=annual_rows())
    monkeypatch.setattr(results, 'statements', lambda *args: [])
    data = client.get('/api/results/GOOG?period=annual', headers=H).json()
    assert data['source'] == 'Alpha Vantage' and data['rows']
    assert requests == ['INCOME_STATEMENT']
