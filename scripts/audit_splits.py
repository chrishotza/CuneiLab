"""Audit dataset split overlap before reporting cuneiform OCR benchmarks.

Uses only Python's standard library. This checks *textual* leakage; passing it
cannot prove photo-level or model-pretraining independence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def _norm_glyphs(raw: str) -> str:
    # Only whitespace is ignored. Damage markers and face boundaries remain.
    return ''.join((raw or '').split())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def audit_splits(sources: dict[str, Path]) -> dict:
    if len(sources) < 2 or len(set(sources)) != len(sources):
        raise ValueError('Se necesitan al menos dos particiones distintas')
    by_id: dict[str, set[str]] = defaultdict(set)
    by_text: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    counts = {}
    repeated_within = {}
    for split, path in sorted(sources.items()):
        if not split or not isinstance(path, Path):
            raise ValueError('Nombre o ruta de split inválido')
        seen = set()
        duplicates = set()
        total = 0
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'id', 'glyphs'}.issubset(reader.fieldnames or []):
                raise ValueError(f'{path}: faltan columnas id y glyphs')
            for line, row in enumerate(reader, 2):
                identifier = (row.get('id') or '').strip().upper()
                if not identifier:
                    raise ValueError(f'{path}:{line}: identificador vacío')
                total += 1
                if identifier in seen:
                    duplicates.add(identifier)
                seen.add(identifier)
                by_id[identifier].add(split)
                glyphs = _norm_glyphs(row.get('glyphs') or '')
                if glyphs:
                    by_text[_digest(glyphs)][split].add(identifier)
        counts[split] = total
        repeated_within[split] = sorted(duplicates)

    cross_ids = [
        {'id': key, 'splits': sorted(splits)}
        for key, splits in sorted(by_id.items()) if len(splits) > 1
    ]
    cross_glyphs = [
        {'sha256': digest,
         'splits': sorted(table),
         'ids_by_split': {part: sorted(table[part]) for part in sorted(table)}}
        for digest, table in sorted(by_text.items()) if len(table) > 1
    ]
    conflicts = bool(cross_ids or cross_glyphs or any(repeated_within.values()))
    return {
        'format': 'cuneilab-split-audit',
        'version': 1,
        'counts': counts,
        'duplicate_ids_within_split': repeated_within,
        'duplicate_ids_across_splits': cross_ids,
        'exact_glyph_duplicates_across_splits': cross_glyphs,
        'passed_exact_overlap_audit': not conflicts,
        'limitations': (
            'Solo compara IDs y secuencias Unicode exactas ignorando espacios. '
            'No detecta variantes, duplicados de fotos ni solapamiento con '
            'los datos previos de entrenamiento de NabuOCR. '
            'No demuestra independencia de evaluación.'
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Auditar fuga de datos entre splits CSV')
    parser.add_argument('--train', required=True, type=Path)
    parser.add_argument('--validation', type=Path)
    parser.add_argument('--test', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    sources = {'train': args.train, 'test': args.test}
    if args.validation:
        sources['validation'] = args.validation
    try:
        report = audit_splits(sources)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f'Error: {exc}\n')
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + '\n', encoding='utf-8')
    print(serialized)
    return 1 if not report['passed_exact_overlap_audit'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
