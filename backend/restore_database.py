"""Restaurer une sauvegarde complète dans une base vide uniquement."""
import argparse
import json
import os
from pathlib import Path
from sqlalchemy import select, insert
from app import db


def restore(source):
    data = json.loads(Path(source).read_text(encoding='utf-8'))
    tables = {t.name: t for t in db.metadata.sorted_tables}
    if data.get('format') != 'my-xtb-ultra-full-backup' or data.get('version') != 1 or set(data.get('tables', {})) != set(tables):
        raise ValueError('Format ou version de sauvegarde incompatible.')
    for name, table in tables.items():
        rows = data['tables'][name]
        if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) != set(table.c.keys()) for row in rows):
            raise ValueError('Structure de table incompatible : ' + name)
    db.init()
    with db.engine.begin() as c:
        for table in tables.values():
            if c.execute(select(table).limit(1)).first() is not None:
                raise ValueError('Restauration refusée : la base cible doit être vide.')
        for name, table in tables.items():
            if data['tables'][name]:
                c.execute(insert(table), data['tables'][name])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Restaurer vers une base vide, serveur arrêté.')
    parser.add_argument('source')
    parser.add_argument('--confirm', required=True, choices=['RESTAURER'])
    args = parser.parse_args()
    if not os.environ.get('DATABASE_URL'):
        parser.error('Définir explicitement DATABASE_URL pour la base cible vide.')
    restore(args.source)
    print('Restauration terminée.')
