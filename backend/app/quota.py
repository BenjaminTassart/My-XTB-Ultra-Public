"""Compteur local séparé des refus de quota signalés par les fournisseurs."""
import json
import time
from datetime import datetime, timedelta, timezone

from . import config, db
from .errors import ProviderError

NOMS = {'fmp': 'Financial Modeling Prep', 'alphavantage': 'Alpha Vantage', 'gemini': 'Gemini (limite locale)'}
NOMS['twelvedata'] = 'Twelve Data (secours cours)'


def blocked(provider):
    row = db.cache_get('quota-block:' + provider)
    if not row:
        return False
    info = json.loads(row[0])
    return time.time() < info['until'] if info.get('until') else info.get('day') == db.today()


def message(provider):
    reason = ('Le fournisseur signale une limite d’appels.' if blocked(provider)
              else 'La limite quotidienne configurée dans l’application est atteinte.')
    return (f'{NOMS.get(provider, provider)} : {reason} '
            'Les données en cache restent affichées. Le compteur local repart à zéro à minuit UTC ; '
            'cela ne garantit pas la disponibilité du quota chez le fournisseur.')


def check(provider):
    if blocked(provider) or db.usage_get(provider) >= config.LIMITS[provider]:
        raise ProviderError('quota', provider, message(provider))


def hit(provider):
    db.usage_add(provider)


def exhaust(provider, reason=None, retry_seconds=None):
    # Un refus ne signifie pas que cette application a effectué tous les appels autorisés.
    db.cache_set('quota-block:' + provider, json.dumps({'day': db.today(), 'reason': reason, 'at': time.time(),
        'until': time.time() + retry_seconds if retry_seconds else None}))


def status():
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    reset = datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    out = []
    for provider, limit in config.LIMITS.items():
        used = db.usage_get(provider)
        provider_blocked = blocked(provider)
        row = db.cache_get('quota-block:' + provider)
        info = json.loads(row[0]) if row else {}
        out.append({'provider': provider, 'name': NOMS.get(provider, provider), 'used': used,
                    'limit': limit, 'remaining': max(limit - used, 0),
                    'provider_blocked': provider_blocked, 'reset_at': reset,
                    'last_refusal': info.get('reason'), 'last_refusal_at': info.get('at'),
                    'retry_at': info.get('until'),
                    'exhausted': provider_blocked or used >= limit})
    return out

# Diagnostic ponctuel des anciens refus qui ne contenaient aucun détail.
import threading
_diagnostic_lock = threading.Lock()


def diagnose_legacy_alpha():
    from . import providers
    with _diagnostic_lock:
        provider = 'alphavantage'
        row = db.cache_get('quota-block:' + provider)
        info = json.loads(row[0]) if row else {}
        if not blocked(provider) or info.get('reason'):
            return {'message': 'Aucun ancien refus sans détail à diagnostiquer.'}
        if db.usage_get(provider) >= config.LIMITS[provider]:
            raise ProviderError('quota', provider, 'Limite locale atteinte : aucun appel de diagnostic effectué.')
        # Ne touche jamais au compteur. Marque la tentative avant l’appel, pour éviter les répétitions.
        db.cache_set('quota-block:' + provider, json.dumps({
            'day': '', 'reason': 'Diagnostic demandé ; résultat en attente.', 'at': time.time()}))
        try:
            providers.av_quote('IBM')
        except ProviderError as e:
            if not blocked(provider):
                exhaust(provider, 'Diagnostic : ' + e.message)
            raise
        db.cache_set('quota-block:' + provider, json.dumps({'day': ''}))
        return {'message': 'Alpha Vantage a accepté l’appel de diagnostic. Tu peux retester les résultats.'}
