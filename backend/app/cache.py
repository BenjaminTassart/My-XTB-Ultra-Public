"""Cache en base : evite de gaspiller le quota et sert de secours quand l'API est indisponible."""
import json
import time

from . import db
from .errors import ProviderError


def cached(key, ttl_seconds, fetch):
    """Renvoie (donnees, perimees). Si l'API echoue (quota/reseau), on ressert l'ancien cache."""
    row = db.cache_get(key)
    if row and time.time() - row[1] < ttl_seconds:
        return json.loads(row[0]), False
    try:
        data = fetch()
    except ProviderError as e:
        if row and e.kind in ("quota", "reseau"):
            return json.loads(row[0]), True
        raise
    db.cache_set(key, json.dumps(data))
    return data, False
