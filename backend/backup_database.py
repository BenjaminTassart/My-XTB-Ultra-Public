"""Sauvegarde JSON complète, en lecture seule. Le fichier contient des données sensibles."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from app import db


def backup(destination):
    output = Path(destination)
    if output.exists():
        raise FileExistsError(output)
    with db.engine.connect() as conn:
        if db.engine.dialect.name == 'postgresql':
            conn = conn.execution_options(isolation_level='REPEATABLE READ')
        with conn.begin():
            tables = {table.name: [dict(r) for r in conn.execute(select(table)).mappings()]
                      for table in db.metadata.sorted_tables}
    payload = json.dumps({'format': 'my-xtb-ultra-full-backup', 'version': 1,
                          'created_at': datetime.now(timezone.utc).isoformat(), 'tables': tables},
                         ensure_ascii=False, indent=2)
    with output.open('x', encoding='utf-8') as f:
        f.write(payload)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sauvegarde complète de la base configurée par DATABASE_URL.')
    parser.add_argument('destination', help='Nouveau fichier JSON, hors du dépôt de préférence.')
    args = parser.parse_args()
    backup(args.destination)
    print('Sauvegarde terminée. Conserver ce fichier dans un emplacement privé.')
