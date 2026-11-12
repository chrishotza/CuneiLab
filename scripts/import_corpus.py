#!/usr/bin/env python3
"""Import SumTablets corpus from official CSV (no dependencies)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from corpus import DEFAULT_DB, import_csv


def main():
    parser = argparse.ArgumentParser(description='Indexa SumTablets en la base local de CuneiLab.')
    parser.add_argument('csv', type=Path, help='Archivo train.csv de colesimmons/SumTablets')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB, help='Destino SQLite')
    parser.add_argument('--limit', type=int, default=None, help='Limitar filas para pruebas')
    args = parser.parse_args()
    try:
        report = import_csv(args.csv, args.db, limit=args.limit)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(f"Filas leídas: {report['rows_scanned']} | nuevas: {report['rows_added']} | DB: {report['database']}")

if __name__ == '__main__':
    main()
