"""Portefeuille et alertes : prix en cache, jamais de déclenchement sur cache périmé."""
import hashlib
import json
import secrets
import threading
import time
import uuid
import math
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import insert, update, delete

from . import config, db, service, providers
from .errors import ProviderError

check_lock = threading.Lock()


class PositionIn(BaseModel):
    symbol: str = Field(max_length=15)
    quantity: float | None = Field(default=None, gt=0, le=1e12, allow_inf_nan=False)
    amount: float | None = Field(default=None, gt=0, le=1e12, allow_inf_nan=False)
    entry_price: float = Field(ge=0, le=1e12, allow_inf_nan=False)
    currency: Literal['EUR', 'USD', 'CAD', 'GBP', 'GBX', 'CHF', 'JPY'] = 'USD'
    exchange_rate: float | None = Field(default=None, gt=0, le=1e6, allow_inf_nan=False)

    @model_validator(mode='after')
    def purchase(self):
        if (self.quantity is None) == (self.amount is None):
            raise ValueError('Saisir soit une quantité, soit un montant investi.')
        if self.amount is not None and self.entry_price <= 0:
            raise ValueError('Le prix unitaire doit être positif pour calculer la quantité.')
        return self


class AlertIn(BaseModel):
    symbol: str = Field(max_length=15)
    threshold: float = Field(gt=0, le=1e12, allow_inf_nan=False)
    direction: Literal['above', 'below']
    currency: Literal['EUR', 'USD', 'CAD', 'GBP', 'GBX', 'CHF', 'JPY'] = 'USD'


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=2048)
    keys: dict[str, str]

    @field_validator('endpoint')
    @classmethod
    def safe_endpoint(cls, value):
        u = urlsplit(value)
        host = u.hostname or ''
        allowed = (host in {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}
                   or host.endswith('.notify.windows.com'))
        if u.scheme != 'https' or not allowed or u.port not in (None, 443) or u.username or u.password:
            raise ValueError('Service de notifications non pris en charge.')
        return value

    @field_validator('keys')
    @classmethod
    def valid_keys(cls, value):
        import base64
        for name, length in [('p256dh', 65), ('auth', 16)]:
            raw = value.get(name, '')
            if len(raw) > 100 or len(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))) != length:
                raise ValueError('Clé de notification invalide.')
        return {k: value[k] for k in ('p256dh', 'auth')}


def push_ready():
    return bool(config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY and config.VAPID_SUBJECT)


def native_currency(symbol):
    if providers.suffix(symbol) == '.L':
        raise HTTPException(400, 'La devise des cotations de Londres reste à confirmer : titre non pris en charge ici.')
    guessed = providers.guess_currency(symbol)
    if guessed:
        return guessed
    quote, _ = service.get_quote(symbol)
    if quote.get('currency'):
        return quote['currency']
    profile, _ = service.get_profile(symbol)
    currency = profile.get('currency')
    if not currency:
        raise HTTPException(400, 'Devise de cotation indisponible pour ce titre.')
    return currency


def normalize_position(body, symbol, native):
    quantity = body.quantity if body.amount is None else body.amount / body.entry_price
    rate, info = 1.0, None
    if body.currency != native:
        if 'GBX' in (body.currency, native):
            raise HTTPException(400, 'Conversion livre/pence non prise en charge.')
        if body.exchange_rate is not None:
            rate = body.exchange_rate
            info = f'Taux saisi : 1 {body.currency} = {rate:g} {native}.'
        else:
            fx, stale = service.cached(f'fx:{body.currency}:{native}', service.TTL_FX,
                                       lambda: providers.fx_rate(body.currency, native))
            if stale:
                raise HTTPException(400, 'Taux périmé : réessayer ou saisir le taux appliqué lors de l’achat.')
            rate = fx['rate']
            info = f"Conversion au taux du {fx.get('date') or 'jour'} : 1 {body.currency} = {rate:g} {native}. Estimation pour un achat passé."
    elif body.exchange_rate not in (None, 1):
        raise HTTPException(400, 'Le taux doit être 1 lorsque les deux devises sont identiques.')
    price = body.entry_price * rate
    if not math.isfinite(quantity) or not 0 < quantity <= 1e12 or not math.isfinite(price) or not 0 <= price <= 1e12:
        raise HTTPException(400, 'Quantité ou prix calculé hors limites.')
    return {'symbol': symbol, 'quantity': quantity, 'entry_price': price, 'currency': native}, info


def converted(price, frm, to):
    if frm == to:
        return price, False
    data, stale = service.cached(f'fx:{frm}:{to}', service.TTL_FX, lambda: providers.fx_rate(frm, to))
    return price * data['rate'], stale


def portfolio(currency):
    items, total, complete = [], 0, True
    quotes = {}
    for p in db.records(db.positions):
        row = {**p, 'value': None, 'stale': False}
        try:
            if p['symbol'] not in quotes:
                quotes[p['symbol']] = service.get_quote(p['symbol'])
            q, stale = quotes[p['symbol']]
            value, fx_stale = converted(q['price'] * p['quantity'], p['currency'], currency)
            row.update(value=value, price=q['price'], stale=stale or fx_stale)
            total += value
        except ProviderError as e:
            row['error'] = e.message
            complete = False
        items.append(row)
    return {'items': items, 'total': total if complete else None, 'subtotal': total,
            'complete': complete, 'currency': currency, 'stale': any(p['stale'] for p in items)}


def send_notification(subscription, payload):
    from pywebpush import webpush
    webpush(subscription_info=json.loads(subscription['payload']), data=json.dumps(payload),
            vapid_private_key=config.VAPID_PRIVATE_KEY, vapid_claims={'sub': config.VAPID_SUBJECT},
            ttl=3600, timeout=10)


def check_alerts():
    if not check_lock.acquire(blocking=False):
        return {'busy': True}
    try:
        result = {'triggered': 0, 'sent': 0, 'warnings': []}
        quotes = {}
        for a in db.records(db.alerts):
            if a['triggered_at'] is not None:
                continue
            try:
                if a['symbol'] not in quotes:
                    quotes[a['symbol']] = service.get_quote(a['symbol'])
                q, stale = quotes[a['symbol']]
                if stale:
                    result['warnings'].append(a['symbol'] + ' : cours périmé, vérification reportée.')
                    continue
                price = q['price']
                reached = price >= a['threshold'] if a['direction'] == 'above' else price <= a['threshold']
                if reached:
                    with db.engine.begin() as c:
                        r = c.execute(update(db.alerts).where(db.alerts.c.id == a['id'],
                            db.alerts.c.triggered_at.is_(None)).values(triggered_at=time.time(), price=price))
                        result['triggered'] += r.rowcount
            except ProviderError as e:
                result['warnings'].append(a['symbol'] + ' : ' + e.message)
        if not push_ready():
            return result
        sent = {r['id'] for r in db.records(db.deliveries)}
        for a in db.records(db.alerts):
            if a['triggered_at'] is None:
                continue
            for sub in db.records(db.subscriptions):
                key = a['id'] + ':' + sub['id']
                if key in sent:
                    continue
                try:
                    send_notification(sub, {'title': 'Alerte ' + a['symbol'], 'tag': a['id'],
                        'body': f"Seuil atteint : {a['price']:g} {a['currency']} (seuil {a['threshold']:g})."})
                    with db.engine.begin() as c:
                        c.execute(insert(db.deliveries).values(id=key, sent_at=time.time()))
                    result['sent'] += 1
                except Exception as e:
                    response = getattr(e, 'response', None)
                    if response is not None and response.status_code in (404, 410):
                        with db.engine.begin() as c:
                            c.execute(delete(db.subscriptions).where(db.subscriptions.c.id == sub['id']))
                    else:
                        result['warnings'].append('Notification non envoyée ; nouvel essai à la prochaine vérification.')
        return result
    finally:
        check_lock.release()


def router(require_code, clean_symbol):
    r = APIRouter(prefix='/api', dependencies=[Depends(require_code)])

    @r.get('/portfolio')
    def get_portfolio(currency: Literal['EUR', 'USD'] = 'EUR'):
        return portfolio(currency)

    def save(table, body, ident=None):
        data = body.model_dump()
        data['symbol'] = clean_symbol(data['symbol'])
        # Prix d’entrée et seuil toujours exprimés dans la devise réelle de cotation.
        service.get_quote(data['symbol'])
        native = native_currency(data['symbol'])
        conversion = None
        if table is db.positions:
            data, conversion = normalize_position(body, data['symbol'], native)
        elif data['currency'] != native:
            raise HTTPException(400, f"Pour {data['symbol']}, saisir les montants en {native}.")
        with db.engine.begin() as c:
            if ident:
                values = {**data}
                if table is db.alerts:
                    values.update(triggered_at=None, price=None)
                    c.execute(delete(db.deliveries).where(db.deliveries.c.id.like(ident + ':%')))
                result = c.execute(update(table).where(table.c.id == ident).values(**values))
                if not result.rowcount:
                    raise HTTPException(404, 'Élément introuvable.')
            else:
                ident = str(uuid.uuid4())
                c.execute(insert(table).values(id=ident, **data))
        return {'id': ident, 'conversion': conversion}

    @r.post('/positions')
    def add_position(body: PositionIn):
        return save(db.positions, body)

    @r.put('/positions/{ident}')
    def edit_position(ident: uuid.UUID, body: PositionIn):
        return save(db.positions, body, str(ident))

    def remove(table, ident):
        with db.engine.begin() as c:
            c.execute(delete(table).where(table.c.id == str(ident)))
            if table is db.alerts:
                c.execute(delete(db.deliveries).where(db.deliveries.c.id.like(str(ident) + ':%')))
        return {'ok': True}

    @r.delete('/positions/{ident}')
    def remove_position(ident: uuid.UUID):
        return remove(db.positions, ident)

    @r.get('/alerts')
    def get_alerts():
        return {'items': db.records(db.alerts)}

    @r.post('/alerts')
    def add_alert(body: AlertIn):
        return save(db.alerts, body)

    @r.put('/alerts/{ident}')
    def edit_alert(ident: uuid.UUID, body: AlertIn):
        return save(db.alerts, body, str(ident))

    @r.delete('/alerts/{ident}')
    def remove_alert(ident: uuid.UUID):
        return remove(db.alerts, ident)

    @r.post('/alerts/check')
    def manual_check():
        return check_alerts()

    @r.get('/push/config')
    def push_config():
        return {'enabled': push_ready(), 'publicKey': config.VAPID_PUBLIC_KEY if push_ready() else None}

    @r.post('/push/subscribe')
    def subscribe(body: SubscriptionIn):
        if not push_ready():
            raise HTTPException(503, 'Notifications non configurées sur le serveur.')
        ident = hashlib.sha256(body.endpoint.encode()).hexdigest()
        payload = json.dumps(body.model_dump())
        with db.engine.begin() as c:
            result = c.execute(update(db.subscriptions).where(db.subscriptions.c.id == ident).values(payload=payload))
            if not result.rowcount:
                c.execute(insert(db.subscriptions).values(id=ident, payload=payload))
        return {'ok': True}

    @r.post('/push/status')
    def subscription_status(body: SubscriptionIn):
        ident = hashlib.sha256(body.endpoint.encode()).hexdigest()
        return {'subscribed': any(row['id'] == ident for row in db.records(db.subscriptions))}

    @r.post('/push/unsubscribe')
    def unsubscribe(body: SubscriptionIn):
        return remove(db.subscriptions, hashlib.sha256(body.endpoint.encode()).hexdigest())

    return r


def cron_check(x_cron_secret: str | None = Header(default=None)):
    if not config.CRON_SECRET or not secrets.compare_digest(x_cron_secret or '', config.CRON_SECRET):
        raise HTTPException(403, 'Secret de planification invalide.')
    return check_alerts()
