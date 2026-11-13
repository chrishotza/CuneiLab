"""Auditoría conservadora de duplicados entre splits cuneiformes.

No descarga corpus, no infiere signos y no prueba independencia del preentrenamiento.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


def _norm_glyphs(raw: str) -> str:
    """Ignora espaciado horizontal, conserva límites de líneas/caras y daños."""
    text = (raw or '').replace('\r\n', '\n').replace('\r', '\n')
    return re.sub(r'[ \t\u00a0]+', '', text).strip('\n')


def _compact_glyphs(raw: str) -> str:
    """Versión de revisión: elimina TODO espacio, incluidos los saltos de línea."""
    return ''.join((raw or '').split())


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _photo_hashes(path: Path, split: str) -> dict[str, str]:
    """Lee audit.jsonl producido por CuneiLab: id + image_sha256/crop_sha256.

    Se exige hash real de 64 caracteres; nunca se usan nombres como sustitutos
    de la identidad del archivo. Un ID con hashes inconsistentes aborta.
    """
    hashes: dict[str, dict[str, str]] = {}
    with path.open('r', encoding='utf-8') as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f'{path}:{line_no}: JSON inválido') from error
            if not isinstance(obj, dict):
                raise ValueError(f'{path}:{line_no}: registro inválido')
            identifier = obj.get('id')
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError(f'{path}:{line_no}: id inválido')
            identifier = identifier.strip().upper()
            digests = {}
            for field in ('image_sha256', 'source_sha256', 'crop_sha256'):
                value = obj.get(field)
                if value is None:
                    continue
                if not isinstance(value, str) or re.fullmatch(r'[a-fA-F0-9]{64}', value) is None:
                    raise ValueError(f'{path}:{line_no}: SHA-256 de imagen inválido en {field}')
                digests[field] = value.lower()
            if not digests:
                raise ValueError(f'{path}:{line_no}: SHA-256 de imagen ausente')
            prior = hashes.setdefault(identifier, {})
            for field, digest in digests.items():
                if field in prior and prior[field] != digest:
                    raise ValueError(f'{path}:{line_no}: hashes contradictorios para {identifier}')
                prior[field] = digest
    return hashes


def _collisions(table: dict[str, dict[str, set[str]]], *, label: str):
    return [
        {label: key, 'splits': sorted(splits),
         'ids_by_split': {split: sorted(ids) for split, ids in sorted(splits.items())}}
        for key, splits in sorted(table.items()) if len(splits) > 1
    ]


def audit_splits(sources: dict[str, Path], *, image_audits: dict[str, Path] | None = None) -> dict:
    if len(sources) < 2 or len(set(sources)) != len(sources):
        raise ValueError('Se necesitan al menos dos particiones distintas')
    if any(not name or not isinstance(path, Path) for name, path in sources.items()):
        raise ValueError('Nombre o ruta de split inválido')
    resolved = [path.resolve() for path in sources.values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError('Las particiones no pueden apuntar al mismo CSV')

    image_audits = image_audits or {}
    if set(image_audits) - set(sources):
        raise ValueError('Auditoría fotográfica sin partición correspondiente')

    by_id: dict[str, set[str]] = defaultdict(set)
    by_exact: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    by_compact: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    by_photo: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set)))
    counts = {}
    repeated_within = {}
    photo_counts = {}

    for split, path in sorted(sources.items()):
        seen, duplicates = set(), set()
        total = 0
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'id', 'glyphs'}.issubset(reader.fieldnames or []):
                raise ValueError(f'{path}: faltan columnas id y glyphs')
            for line_no, row in enumerate(reader, 2):
                identifier = (row.get('id') or '').strip().upper()
                if not identifier:
                    raise ValueError(f'{path}:{line_no}: identificador vacío')
                total += 1
                if identifier in seen:
                    duplicates.add(identifier)
                seen.add(identifier)
                by_id[identifier].add(split)
                original = row.get('glyphs') or ''
                exact = _norm_glyphs(original)
                compact = _compact_glyphs(original)
                if exact:
                    by_exact[_digest(exact)][split].add(identifier)
                if compact:
                    by_compact[_digest(compact)][split].add(identifier)
        counts[split] = total
        repeated_within[split] = sorted(duplicates)

        if split in image_audits:
            records = _photo_hashes(Path(image_audits[split]), split)
            photo_counts[split] = len(records)
            for identifier, digests in records.items():
                if identifier not in seen:
                    raise ValueError(f'{split}: la foto {identifier} no figura en el CSV del split')
                # Compare originals independently of crops: distinct crops of the
                # same source photograph must not appear in separate splits.
                # Never compare a crop hash against an original hash by accident.
                for field, digest in digests.items():
                    kind = 'original' if field in ('source_sha256', 'image_sha256') else 'crop'
                    by_photo[kind][digest][split].add(identifier)

    exact_matches = _collisions(by_exact, label='sha256')
    exact_hashes = {row['sha256'] for row in exact_matches}
    review_matches = [
        row for row in _collisions(by_compact, label='sha256')
        if row['sha256'] not in exact_hashes
    ]
    # Un texto compacto puede ser idéntico a otro aunque sus hashes exactos
    # difieran: para no ocultarlo, siempre se presenta como revisión.
    photo_matches = [
        {'image_kind': kind, **row}
        for kind in sorted(by_photo)
        for row in _collisions(by_photo[kind], label='sha256')
    ]
    cross_ids = [{'id': key, 'splits': sorted(splits)}
                 for key, splits in sorted(by_id.items()) if len(splits) > 1]
    blocking = bool(cross_ids or exact_matches or photo_matches or any(repeated_within.values()))
    return {
        'format': 'cuneilab-split-audit', 'version': 2,
        'counts': counts, 'photo_audit_counts': photo_counts,
        'duplicate_ids_within_split': repeated_within,
        'duplicate_ids_across_splits': cross_ids,
        'exact_glyph_duplicates_across_splits': exact_matches,
        'potential_line_boundary_duplicates': review_matches,
        'duplicate_photo_hashes_across_splits': photo_matches,
        'passed_exact_overlap_audit': not blocking,
        'needs_manual_review': bool(review_matches),
        'limitations': (
            'Los hashes de imágenes proceden de archivos de auditoría aportados '
            'por el usuario, no de fotos verificadas aquí. Si los recortes son '
            'distintos, sus hashes pueden diferir aunque sean la misma tablilla. '
            'Se comparan por separado los SHA-256 de originales y recortes. '
            'No se detectan variantes textuales, fotografías transformadas ni '
            'datos vistos por NabuOCR en su entrenamiento.'
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Auditar fugas entre conjuntos de tablillas')
    parser.add_argument('--train', required=True, type=Path)
    parser.add_argument('--validation', type=Path)
    parser.add_argument('--test', required=True, type=Path)
    parser.add_argument('--train-audit', type=Path, help='audit.jsonl con hashes de imágenes train')
    parser.add_argument('--validation-audit', type=Path)
    parser.add_argument('--test-audit', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    sources = {'train':args.train, 'test':args.test}
    if args.validation:
        sources['validation'] = args.validation
    audits = {}
    for split in ('train', 'validation', 'test'):
        value = getattr(args, split + '_audit')
        if value:
            audits[split] = value
    try:
        result = audit_splits(sources, image_audits=audits)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f'Error: {exc}\n')
    report = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report + '\n', encoding='utf-8')
    print(report)
    return 1 if not result['passed_exact_overlap_audit'] else (3 if result['needs_manual_review'] else 0)


if __name__ == '__main__':
    raise SystemExit(main())
