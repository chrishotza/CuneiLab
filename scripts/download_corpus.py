#!/usr/bin/env python3
"""Download *training* CSV only; validate bytes before importing locally.

Pinned SHA256 for colesimmons/SumTablets train.csv as published on 2026-11-12.
This script does not fetch validation/test to protect their status as held-out sets.
"""
from __future__ import annotations
import argparse
import hashlib
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from corpus import DEFAULT_DB, import_csv

TRAIN_URL = 'https://huggingface.co/datasets/colesimmons/SumTablets/resolve/main/train.csv'
TRAIN_SHA256 = '57c78a77ead81790b4a7efcd94090e2957ef11645998bc7edfdff5db1a3db6ce'
MAX_BYTES = 250 * 1024 * 1024


def sha256_file(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def download(url: str, output: Path, expected_sha256: str, *, max_bytes: int = MAX_BYTES) -> dict:
    """Atomic content-addressed download, up to max_bytes; existing valid file reused."""
    output = Path(output)
    if output.is_file() and sha256_file(output) == expected_sha256:
        return {'path': str(output), 'reused': True, 'sha256': expected_sha256}
    if output.exists():
        raise ValueError(f'Existe {output}, pero su SHA256 no coincide. Revisá la fuente antes de reemplazarlo.')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + '.part')
    checksum = hashlib.sha256()
    total = 0
    try:
        # Only vetted host constant is used by main() below; no user URL input.
        with urlopen(Request(url, headers={'User-Agent': 'CuneiLab/0.3'}), timeout=45) as response, temp.open('wb') as file:
            for chunk in iter(lambda: response.read(1024 * 1024), b''):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError('Descarga superior al límite de seguridad')
                checksum.update(chunk)
                file.write(chunk)
        obtained = checksum.hexdigest()
        if obtained != expected_sha256:
            raise ValueError(f'SHA256 inesperado: {obtained}; esperado: {expected_sha256}. Archivo no instalado.')
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)
    return {'path': str(output), 'reused': False, 'sha256': expected_sha256, 'bytes': total}


def main() -> None:
    parser = argparse.ArgumentParser(description='Descarga y verifica el entrenamiento de SumTablets')
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'train.csv')
    parser.add_argument('--import', dest='import_data', action='store_true', help='Importar datos a SQLite tras descargar')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print('Origen:', TRAIN_URL, '\nConjunto: train (no incluye validación ni prueba)', flush=True)
    try:
        report = download(TRAIN_URL, args.output, TRAIN_SHA256)
        print('Descarga verificada:', report, flush=True)
        if args.import_data:
            print('Importando al índice local...', flush=True)
            print(import_csv(args.output, args.db), flush=True)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
