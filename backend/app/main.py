"""API My XTB Ultra (FastAPI). Sert aussi l'interface compilee en production."""
import os
import re
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, news, quota, service
from .errors import ProviderError


@asynccontextmanager
async def lifespan(_):
    db.init()
    yield


app = FastAPI(title="My XTB Ultra", lifespan=lifespan)

SYMBOL_RE = re.compile(r"^[A-Z0-9.\-^=]{1,15}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def error_body(code, message, provider=None):
    return {"detail": {"code": code, "message": message, "provider": provider}}


@app.exception_handler(ProviderError)
async def provider_error_handler(_, e: ProviderError):
    return JSONResponse(status_code=e.status, content=error_body(e.kind, e.message, e.provider))


def require_code(x_access_code: str | None = Header(default=None)):
    if config.ACCESS_CODE and not secrets.compare_digest(x_access_code or "", config.ACCESS_CODE):
        raise HTTPException(status_code=401, detail=error_body("auth", "Code d'accès invalide.")["detail"])


def clean_symbol(raw: str) -> str:
    symbol = raw.strip().upper()
    if not SYMBOL_RE.match(symbol):
        raise HTTPException(status_code=400, detail=error_body("invalide", "Symbole invalide.")["detail"])
    return symbol


class FavoriteIn(BaseModel):
    symbol: str


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/auth/check", dependencies=[Depends(require_code)])
def auth_check():
    return {"ok": True, "protected": bool(config.ACCESS_CODE)}


@app.get("/api/quota", dependencies=[Depends(require_code)])
def get_quota():
    return {"providers": quota.status()}


@app.post("/api/quota/alphavantage/diagnose", dependencies=[Depends(require_code)])
def diagnose_alpha():
    return quota.diagnose_legacy_alpha()


@app.get("/api/favorites", dependencies=[Depends(require_code)])
def get_favorites():
    return {"items": [service.summary(s) for s in db.list_favorites()]}


@app.post("/api/favorites", dependencies=[Depends(require_code)])
def add_favorite(body: FavoriteIn):
    symbol = clean_symbol(body.symbol)
    service.get_quote(symbol)  # verifie que le titre existe avant de l'enregistrer
    db.add_favorite(symbol)
    return {"ok": True, "symbol": symbol}


@app.delete("/api/favorites/{symbol}", dependencies=[Depends(require_code)])
def delete_favorite(symbol: str):
    db.remove_favorite(clean_symbol(symbol))
    return {"ok": True}


@app.get("/api/stock/{symbol}", dependencies=[Depends(require_code)])
def get_stock(symbol: str):
    return service.stock(clean_symbol(symbol), use_sec=True)


@app.get("/api/history/{symbol}", dependencies=[Depends(require_code)])
def get_history(symbol: str):
    return service.get_history(clean_symbol(symbol))


@app.get("/api/fx", dependencies=[Depends(require_code)])
def get_fx(frm: str = Query(alias="from"), to: str = Query()):
    frm, to = frm.strip().upper(), to.strip().upper()
    if not (CURRENCY_RE.match(frm) and CURRENCY_RE.match(to)):
        raise HTTPException(status_code=400, detail=error_body("invalide", "Devise invalide.")["detail"])
    return service.get_fx(frm, to)


@app.get("/api/news", dependencies=[Depends(require_code)])
def get_news():
    return {"items": news.latest(db.list_favorites())}


from . import portfolio
app.include_router(portfolio.router(require_code, clean_symbol))
app.post('/api/tasks/check-alerts')(portfolio.cron_check)


from . import results
app.include_router(results.router(require_code, clean_symbol))

from . import screener
app.include_router(screener.router(require_code))
app.post('/api/tasks/refresh-screener')(screener.cron_refresh)

from . import data_management
app.include_router(data_management.router(require_code))

# Interface compilee (production) : servie par le meme serveur
if config.STATIC_DIR and os.path.isdir(config.STATIC_DIR):
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
