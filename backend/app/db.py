"""Base de donnees : favoris, cache des donnees, compteur d'appels aux API."""
import time
from datetime import datetime, timezone

from sqlalchemy import (Column, Float, Integer, MetaData, String, Table, Text, create_engine,
                        delete, insert, select, update)

from . import config

_kw = {"pool_pre_ping": True}
if config.DATABASE_URL.startswith("postgresql"):
    _kw["connect_args"] = {"prepare_threshold": None}  # compatible avec le pooler de Supabase
elif config.DATABASE_URL.startswith("sqlite"):
    _kw["connect_args"] = {"check_same_thread": False}

engine = create_engine(config.DATABASE_URL, **_kw)
metadata = MetaData()

favorites = Table("favorites", metadata,
                  Column("symbol", String(32), primary_key=True),
                  Column("added_at", Float, nullable=False))
cache = Table("cache", metadata,
              Column("key", String(200), primary_key=True),
              Column("payload", Text, nullable=False),
              Column("fetched_at", Float, nullable=False))
usage = Table("usage", metadata,
              Column("provider", String(32), primary_key=True),
              Column("day", String(10), primary_key=True),
              Column("count", Integer, nullable=False))


def init():
    metadata.create_all(engine)


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---- favoris
def list_favorites():
    with engine.connect() as c:
        rows = c.execute(select(favorites.c.symbol).order_by(favorites.c.added_at)).all()
    return [r[0] for r in rows]


def is_favorite(symbol):
    with engine.connect() as c:
        return c.execute(select(favorites.c.symbol).where(favorites.c.symbol == symbol)).first() is not None


def add_favorite(symbol):
    if is_favorite(symbol):
        return
    with engine.begin() as c:
        c.execute(insert(favorites).values(symbol=symbol, added_at=time.time()))


def remove_favorite(symbol):
    with engine.begin() as c:
        c.execute(delete(favorites).where(favorites.c.symbol == symbol))


# ---- cache
def cache_get(key):
    with engine.connect() as c:
        row = c.execute(select(cache.c.payload, cache.c.fetched_at).where(cache.c.key == key)).first()
    return (row[0], row[1]) if row else None


def cache_set(key, payload):
    now = time.time()
    with engine.begin() as c:
        r = c.execute(update(cache).where(cache.c.key == key).values(payload=payload, fetched_at=now))
        if r.rowcount == 0:
            c.execute(insert(cache).values(key=key, payload=payload, fetched_at=now))


# ---- compteur d'appels (par fournisseur et par jour UTC)
def usage_get(provider):
    with engine.connect() as c:
        row = c.execute(select(usage.c.count).where(usage.c.provider == provider,
                                                    usage.c.day == today())).first()
    return row[0] if row else 0


def usage_set(provider, n):
    with engine.begin() as c:
        r = c.execute(update(usage).where(usage.c.provider == provider, usage.c.day == today())
                      .values(count=n))
        if r.rowcount == 0:
            c.execute(insert(usage).values(provider=provider, day=today(), count=n))


def usage_add(provider, n=1):
    usage_set(provider, usage_get(provider) + n)

# Étape 3 : données personnelles persistantes.
positions = Table('positions', metadata,
    Column('id', String(36), primary_key=True), Column('symbol', String(32), nullable=False),
    Column('quantity', Float, nullable=False), Column('entry_price', Float, nullable=False),
    Column('currency', String(3), nullable=False))
alerts = Table('alerts', metadata,
    Column('id', String(36), primary_key=True), Column('symbol', String(32), nullable=False),
    Column('threshold', Float, nullable=False), Column('direction', String(8), nullable=False),
    Column('currency', String(3), nullable=False), Column('triggered_at', Float), Column('price', Float))
subscriptions = Table('push_subscriptions', metadata,
    Column('id', String(64), primary_key=True), Column('payload', Text, nullable=False))
deliveries = Table('push_deliveries', metadata,
    Column('id', String(110), primary_key=True), Column('sent_at', Float, nullable=False))


def records(table):
    with engine.connect() as c:
        return [dict(r) for r in c.execute(select(table)).mappings()]

screener = Table('screener', metadata,
    Column('symbol', String(32), primary_key=True),
    Column('attempted_at', Float, nullable=False), Column('updated_at', Float),
    Column('payload', Text), Column('sector', String(80)), Column('country', String(8)),
    Column('market_cap', Float), Column('error', Text))
