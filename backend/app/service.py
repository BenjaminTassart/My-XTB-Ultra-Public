"""Assemble les donnees d'un titre (prix, profil, indicateurs) avec cache et tolerance aux pannes."""
import json
from . import config, db, providers, twelvedata, sec_metrics
from .cache import cached
from .errors import ProviderError

TTL_QUOTE = 15 * 60          # prix differes de 15 minutes de toute facon
TTL_PROFILE = 7 * 24 * 3600  # le profil change rarement
TTL_METRICS = 24 * 3600
TTL_HISTORY = 12 * 3600
TTL_FX = 6 * 3600


def get_quote(symbol):
    def fetch():
        if providers.is_foreign(symbol):
            if providers.suffix(symbol) in providers.AV_SUFFIX:
                return providers.av_quote(symbol)
            raise ProviderError("payant", "fmp",
                                "Les titres de cette bourse ne sont pas couverts par l'offre gratuite.")
        try:
            return providers.fmp_quote(symbol)
        except ProviderError as e:
            if e.kind not in ('payant', 'inconnu') or not config.TWELVEDATA_API_KEY:
                raise
            return twelvedata.quote(symbol)

    return cached(f"quote:{symbol}", TTL_QUOTE, fetch)


def get_profile(symbol):
    if providers.is_foreign(symbol):
        return {}, False
    return cached(f"profile:{symbol}", TTL_PROFILE, lambda: providers.fmp_profile(symbol))


def get_metrics(symbol):
    if providers.is_foreign(symbol):
        return [], False
    try:
        return cached(f"metrics:{symbol}", TTL_METRICS, lambda: providers.fmp_metrics(symbol))
    except ProviderError as e:
        previous = db.cache_get(f'metrics:{symbol}')
        if previous and e.kind in ('payant', 'inconnu'):
            return json.loads(previous[0]), True
        raise


def get_history(symbol):
    if providers.is_foreign(symbol):
        raise ProviderError("payant", "fmp",
                            "L'historique des prix n'est pas disponible gratuitement pour cette bourse.")
    def fetch():
        try:
            return {'points': providers.fmp_history(symbol), 'source': 'fmp'}
        except ProviderError as e:
            if e.kind not in ('payant', 'inconnu') or not config.TWELVEDATA_API_KEY:
                raise
            return {'points': twelvedata.history(symbol), 'source': 'twelvedata'}
    data, stale = cached(f"history:{symbol}", TTL_HISTORY, fetch)
    # Les caches déjà enregistrés avant le secours contiennent directement la liste FMP.
    if isinstance(data, list):
        data = {'points': data, 'source': 'fmp'}
    return {"symbol": symbol, **data, "stale": stale}


def get_fx(frm, to):
    if frm == to:
        return {"from": frm, "to": to, "rate": 1.0, "date": None}
    data, _ = cached(f"fx:{frm}:{to}", TTL_FX, lambda: providers.fx_rate(frm, to))
    return data


def _warn(e):
    return {"code": e.kind, "message": e.message}


def summary(symbol):
    """Version legere pour la liste des favoris (ne leve jamais d'erreur)."""
    out = {"symbol": symbol}
    try:
        q, stale = get_quote(symbol)
    except ProviderError as e:
        out["error"] = _warn(e)
        return out
    out.update(price=q["price"], change=q["change"], changePercent=q["changePercent"],
               name=q.get("name"), stale=stale, limited=q["source"] != "fmp",
               currency=q.get("currency") or providers.guess_currency(symbol))
    try:
        p, _ = get_profile(symbol)
        out["name"] = p.get("name") or out["name"]
        out["logo"] = p.get("logo")
        out["currency"] = p.get("currency") or out.get("currency")
    except ProviderError as e:
        out["warning"] = _warn(e)
    return out


def stock(symbol, use_sec=False):
    q, stale = get_quote(symbol)
    quote_stale = stale
    warnings = []
    profile, indicators = {}, []
    indicators_stale = False
    try:
        profile, s = get_profile(symbol)
        stale = stale or s
    except ProviderError as e:
        warnings.append({**_warn(e), 'section': 'profile'})
    try:
        indicators, s = get_metrics(symbol)
        indicators_stale = s
        stale = stale or s
    except ProviderError as e:
        warnings.append({**_warn(e), 'section': 'indicators'})
    limited = q["source"] != "fmp"
    if not indicators:
        indicators = [{'key': k, 'label': label, 'kind': kind, 'value': None}
                      for k, label, kind, _ in providers.INDICATORS]
    metrics_source, metrics_note, metrics_url = 'FMP', None, None
    market_cap, cap_label = q['marketCap'], 'Capitalisation'
    currency = q.get('currency') or profile.get('currency') or providers.guess_currency(symbol)
    if (use_sec and symbol in sec_metrics.CIKS and currency == 'USD' and q['price'] > 0
            and (market_cap is None or any(i['value'] is None for i in indicators))):
        try:
            backup = sec_metrics.calculate(symbol, q['price'])
            original = any(i['value'] is not None for i in indicators)
            labels = {'per': 'PER (bénéfice annuel)', 'netMargin': 'Marge nette annuelle', 'roe': 'ROE annuel',
                      'pb': 'P/B estimé', 'dividendYield': 'Dividende annuel / cours'}
            for item in indicators:
                if item['value'] is None:
                    item['value'] = backup['values'].get(item['key'])
                    item['source'] = 'SEC (calcul annuel)'
                    item['reason'] = backup['reasons'].get(item['key']) if item['value'] is None else None
                    item['label'] = labels.get(item['key'], item['label'])
                else:
                    item['source'] = 'FMP'
            if market_cap is None and backup['marketCap'] is not None:
                market_cap = backup['marketCap']
                cap_label = 'Capitalisation estimée'
            metrics_source = 'FMP + SEC' if original else 'SEC (calculs annuels)'
            snapshot = backup['snapshot']
            metrics_note = (f"Comptes du {snapshot['start']} au {snapshot['end']}, déposés le {snapshot['filed']}. "
                            'Calculs annuels, pas sur les douze derniers mois glissants. '
                            'Le PER utilise le cours affiché et le bénéfice annuel publié. ')
            metrics_note += ('Capitalisation et P/B estimés avec le nombre d’actions en fin d’exercice ; '
                             'les émissions ou rachats ultérieurs ne sont pas pris en compte.' if symbol == 'SNDK'
                             else 'La capitalisation et le P/B d’Alphabet ne sont pas estimés : ses classes d’actions ont des cours distincts.')
            metrics_url = backup['url']
            indicators_stale = indicators_stale or backup['stale']
            stale = stale or backup['stale']
        except ProviderError as e:
            metrics_note = 'Secours des indicateurs : ' + e.message
    if q['source'] == 'twelvedata':
        warnings.append({'code': 'secours', 'message': 'Cours fourni par Twelve Data en secours de FMP. '
                         'Un secours est aussi prévu pour le graphique. Le profil, les indicateurs et les résultats peuvent rester indisponibles.'})
    elif limited and not warnings:
        warnings.append({"code": "limite", "message": "Pour cette bourse, seul le prix est disponible "
                         "gratuitement (pas de profil ni d'indicateurs)."})
    return {
        "symbol": symbol, "favorite": db.is_favorite(symbol), "stale": stale, "limited": limited,
        "quote_stale": quote_stale, "quote_source": q['source'],
        "name": profile.get("name") or q.get("name") or symbol,
        "logo": profile.get("logo"), "sector": profile.get("sector"),
        "industry": profile.get("industry"), "country": profile.get("country"),
        "currency": q.get("currency") or profile.get("currency") or providers.guess_currency(symbol), "exchange": profile.get("exchange") or q.get("exchange"),
        "website": profile.get("website"), "description": profile.get("description"),
        "price": q["price"], "change": q["change"], "changePercent": q["changePercent"],
        "dayLow": q["dayLow"], "dayHigh": q["dayHigh"], "yearLow": q["yearLow"],
        "yearHigh": q["yearHigh"], "volume": q["volume"], "marketCap": market_cap,
        "marketCapLabel": cap_label, "indicators_source": metrics_source,
        "indicators_note": metrics_note, "indicators_url": metrics_url,
        "indicators": indicators, "indicators_stale": indicators_stale, "warnings": warnings,
    }
