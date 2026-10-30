"""Export des données personnelles et suppression explicitement confirmée."""
import json
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from . import db, portfolio, results


class DeleteIn(BaseModel):
    scope: Literal['favorites', 'positions', 'alerts', 'personal']
    confirmation: str


def router(require_code):
    r = APIRouter(prefix='/api/data', dependencies=[Depends(require_code)])

    @r.get('/export')
    def export():
        # Une lecture en transaction, sans appel fournisseur ni secrets de connexion.
        with db.engine.begin() as c:
            data = {name: [dict(row) for row in c.execute(select(table)).mappings()]
                    for name, table in [('favorites', db.favorites), ('positions', db.positions), ('alerts', db.alerts)]}
            summaries = c.execute(select(db.cache.c.key, db.cache.c.payload, db.cache.c.fetched_at)
                                  .where(db.cache.c.key.like('summary:%'))).mappings()
            data['summaries'] = [{'key': row['key'], 'value': json.loads(row['payload']),
                                   'saved_at': row['fetched_at']} for row in summaries]
        return {'format': 'my-xtb-ultra', 'version': 1,
                'exported_at': datetime.now(timezone.utc).isoformat(), **data}

    @r.post('/delete')
    def erase(body: DeleteIn):
        if body.confirmation != 'SUPPRIMER':
            raise HTTPException(400, 'Saisir SUPPRIMER pour confirmer.')
        # Attend la fin d’un contrôle avant d’effacer les alertes et abonnements.
        with portfolio.check_lock, results.summary_lock:
            with db.engine.begin() as c:
                if body.scope in ('favorites', 'personal'):
                    c.execute(delete(db.favorites))
                if body.scope in ('positions', 'personal'):
                    c.execute(delete(db.positions))
                if body.scope in ('alerts', 'personal'):
                    c.execute(delete(db.alerts))
                    c.execute(delete(db.deliveries))
                if body.scope == 'personal':
                    c.execute(delete(db.subscriptions))
                    c.execute(delete(db.cache).where(db.cache.c.key.like('summary:%')))
        return {'ok': True, 'scope': body.scope}
    return r
