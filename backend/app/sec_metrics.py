"""Secours annuel prudent pour GOOG et SNDK, à partir des comptes publics SEC.

Pas de prévisions, de TTM reconstruit, ni de chiffres codés en dur.
"""
import json
import math
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import config, db
from .cache import cached
from .errors import ProviderError

# Identifiants des émetteurs dans leurs rapports SEC (GOOG reste la classe C).
CIKS = {'GOOG': 1652044, 'SNDK': 2023554}
TTL = 24 * 3600
_lock = threading.Lock()
_last_call = 0.0


def day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def number(value):
    return value if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) else None


def normalized_cik(value):
    # SEC peut renvoyer un entier ou une chaîne de chiffres avec zéros initiaux.
    # Ne pas accepter float/bool ni un texte contenant un autre identifiant.
    if type(value) is int:
        return value if 0 < value < 10**10 else None
    if isinstance(value, str) and re.fullmatch(r'[0-9]{1,10}', value):
        return int(value) or None
    return None


def extract(data):
    """Sélection d'un exercice complet ; toutes les entrées viennent du même dépôt."""
    today = datetime.now(timezone.utc).date()
    facts = data.get('facts', {}).get('us-gaap', {})
    if not isinstance(facts, dict):
        raise ProviderError('reseau', 'sec', 'Comptes SEC illisibles.')

    def rows(tag, unit):
        concept = facts.get(tag, {})
        units = concept.get('units', {}) if isinstance(concept, dict) else {}
        raw = units.get(unit, []) if isinstance(units, dict) else []
        return [r for r in raw if isinstance(r, dict) and r.get('form') in ('10-K', '10-K/A')
                and day(r.get('end')) and day(r.get('filed')) and day(r['end']) <= today
                and day(r['filed']) <= today and number(r.get('val')) is not None
                and isinstance(r.get('accn'), str) and re.fullmatch(r'\d{10}-\d{2}-\d{6}', r['accn'])]

    annual = [r for r in rows('NetIncomeLoss', 'USD') if day(r.get('start'))
              and 330 <= (day(r['end']) - day(r['start'])).days <= 400]
    if not annual:
        raise ProviderError('inconnu', 'sec', 'Aucun exercice annuel exploitable dans les comptes SEC.')
    anchor = max(annual, key=lambda r: (r['end'], r['filed'], r['accn']))
    start, end, accession = anchor['start'], anchor['end'], anchor['accn']

    def pick(tags, unit='USD', instant=None):
        for tag in tags:
            matching = [r for r in rows(tag, unit) if r['accn'] == accession
                        and r['end'] == (instant or end)
                        and (not r.get('start') if instant else r.get('start') == start)]
            values = {r['val'] for r in matching}
            if len(values) == 1:
                return values.pop()
            if len(values) > 1:
                return None  # contexte ambigu : ne pas choisir arbitrairement
        return None

    return {'start': start, 'end': end, 'filed': anchor['filed'], 'accn': accession,
            'income': pick(['NetIncomeLoss']),
            'revenue': pick(['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet']),
            'eps': pick(['EarningsPerShareDiluted'], 'USD/shares'),
            'equity': pick(['StockholdersEquity'], instant=end),
            'equity_start': pick(['StockholdersEquity'], instant=(day(start) - timedelta(days=1)).isoformat()),
            'shares': pick(['CommonStockSharesOutstanding'], 'shares', instant=end),
            'dividend': pick(['CommonStockDividendsPerShareCashPaid'], 'USD/shares')}


def _fetch(symbol):
    global _last_call
    if not re.search(r'[^\s@]+@[^\s@]+\.[^\s@]+', config.SEC_USER_AGENT) or '\n' in config.SEC_USER_AGENT or '\r' in config.SEC_USER_AGENT:
        raise ProviderError('config', 'sec', 'Pour activer les indicateurs gratuits SEC, renseigner SEC_USER_AGENT dans Render : nom de l’application et email de contact.')
    cooldown = db.cache_get('sec:cooldown')
    if cooldown and time.time() < float(cooldown[0]):
        raise ProviderError('reseau', 'sec', 'La SEC a suspendu les appels ; réessayer dans quelques minutes.')
    cik = CIKS[symbol]
    try:
        with _lock:
            time.sleep(max(0, 0.25 - (time.monotonic() - _last_call)))
            _last_call = time.monotonic()
            response = requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',
                                    headers={'User-Agent': config.SEC_USER_AGENT, 'Accept': 'application/json'}, timeout=25)
        if response.status_code in (403, 429):
            db.cache_set('sec:cooldown', str(time.time() + 300))
            raise ProviderError('reseau', 'sec', 'Accès SEC temporairement refusé. Vérifier SEC_USER_AGENT et réessayer dans cinq minutes.')
        if response.status_code >= 400:
            raise ProviderError('reseau', 'sec', 'Comptes SEC momentanément indisponibles.')
        data = response.json()
    except (requests.RequestException, ValueError) as e:
        raise ProviderError('reseau', 'sec', 'Impossible de lire les comptes SEC.') from e
    if not isinstance(data, dict) or normalized_cik(data.get('cik')) != cik or not isinstance(data.get('facts'), dict):
        raise ProviderError('reseau', 'sec', 'Émetteur ou format SEC incorrect ; aucun indicateur calculé.')
    return extract(data)


def calculate(symbol, price):
    snapshot, stale = cached(f'sec-annual:v1:{CIKS[symbol]}', TTL, lambda: _fetch(symbol))
    income, revenue, eps = (snapshot[k] for k in ('income', 'revenue', 'eps'))
    equity, opening, shares = (snapshot[k] for k in ('equity', 'equity_start', 'shares'))
    dated = (datetime.now(timezone.utc).date() - day(snapshot['end'])).days > 550
    values = {'per': price / eps if eps is not None and eps > 0 and not dated else None,
              'netMargin': income / revenue if income is not None and revenue is not None and revenue > 0 else None,
              'roe': income / ((equity + opening) / 2) if income is not None and equity is not None
                     and opening is not None and equity > 0 and opening > 0 else None,
              'pb': None, 'dividendYield': None, 'peg': None, 'debtToEbitda': None}
    # Pas de capitalisation ni de P/B pour Alphabet : plusieurs classes à cours distincts.
    cap = None
    if symbol == 'SNDK' and shares is not None and shares > 0 and not dated:
        cap = price * shares
        if equity is not None and equity > 0:
            values['pb'] = cap / equity
    dividend = snapshot['dividend']
    if dividend is not None and dividend >= 0 and not dated:
        values['dividendYield'] = dividend / price
    reasons = {'per': 'Bénéfice dilué annuel absent, nul ou négatif, ou comptes trop anciens.',
               'peg': 'Prévisions de croissance non disponibles dans les comptes SEC.',
               'pb': 'Classes d’actions multiples ou nombre d’actions/capitaux propres non exploitable.',
               'dividendYield': 'Dividende annuel par action non fourni dans un format exploitable.',
               'netMargin': 'Résultat net et chiffre d’affaires annuels comparables non disponibles.',
               'roe': 'Résultat annuel et capitaux propres de début/fin d’exercice non disponibles ou non positifs.',
               'debtToEbitda': 'Dette nette et EBITDA comparables non disponibles dans ce calcul.'}
    return {'values': values, 'reasons': reasons, 'marketCap': cap, 'snapshot': snapshot,
            'stale': stale or dated,
            'url': f"https://www.sec.gov/Archives/edgar/data/{CIKS[symbol]}/{snapshot['accn'].replace('-', '')}/{snapshot['accn']}-index.html"}
