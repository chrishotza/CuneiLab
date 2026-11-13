"""Convert locally obtained CuneiML v1.2 metadata + photos into OCR benchmark files.

The original CuneiML release provides photo URLs and bounding boxes, NOT images.
No automatic downloads or claim of held-out model performance. This script is
intentionally offline: the user must have rights to each locally supplied image.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from transcription import is_sign, sign_count
from scripts.batch_nabu import atomic_json, atomic_jsonl, sha256

SOURCE_URL = 'https://zenodo.org/records/10806319'
SOURCE_MD5 = 'fb11e8d06d9f03030f4b19def7621034'
FACE_ORDER = ('obverse', 'reverse', 'left', 'right', 'top', 'bottom')
EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
ID = re.compile(r'P[0-9]{6}\Z')


def records_from_metadata(path: Path):
    """Supports the published list and ID-keyed dictionary forms.

    Metadata is ~205 MB; json.load needs substantial RAM. Avoids fetching
    corpus data or image files implicitly.
    """
    source = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(source, list):
        return source
    if isinstance(source, dict):
        return [({'id': k, **v} if 'id' not in v else v) for k,v in source.items() if isinstance(v, dict)]
    raise ValueError('CuneiML: se esperaba una lista o un objeto de registros')


def md5_file(path: Path):
    digest = hashlib.md5()  # Upstream published MD5 for integrity only, not security.
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical_id(value):
    if type(value) is int and 0 <= value <= 999999:
        return f'P{value:06d}'
    if isinstance(value, str):
        if ID.fullmatch(value):
            return value
        if re.fullmatch(r'[0-9]{1,6}', value):
            return f'P{int(value):06d}'
    raise ValueError('Identificador CDLI inválido')


def reference_glyphs(record):
    """Only wholly convertible, known-face glyph lines become gold standards.

    Unknown symbols or markup invalidate a reference; silently discarding them
    would make OCR quality appear better than it is.
    """
    faces = record.get('text')
    if not isinstance(faces, dict) or not faces:
        raise ValueError('Sin texto por cara')
    if any(face not in FACE_ORDER for face in faces):
        raise ValueError('Cara no reconocida')
    segments = []
    total = 0
    for face in FACE_ORDER:
        if face not in faces:
            continue
        lines = faces[face]
        if not isinstance(lines, list) or not lines:
            raise ValueError('Cara vacía o inválida')
        rendered = []
        for line in lines:
            if not isinstance(line, dict) or not isinstance(line.get('sign'), list):
                raise ValueError('Línea sin signos verificados')
            parts = line['sign']
            if not parts or not all(isinstance(x, str) and x and all(is_sign(c) for c in x) for x in parts):
                raise ValueError('Línea con signo desconocido, perdido o sin Unicode')
            group = ' '.join(parts)
            total += sign_count(group)
            rendered.append(group)
        segments.append('@' + face + '\n' + '\n'.join(rendered))
    if total < 2:
        raise ValueError('Referencia demasiado corta')
    return '\n'.join(segments), total


def find_photo(directory: Path, identifier: str):
    for suffix in EXTENSIONS:
        found = directory / (identifier + suffix)
        if found.is_file() and not found.is_symlink() and found.stat().st_size <= 100 * 1024 * 1024 and found.stat().st_size > 0:
            return found
    return None


def split_for(identifier: str):
    """Our own reproducible, tablet-level partition, NOT NabuOCR author's split."""
    fraction = int(hashlib.sha256(('cuneilab-v07:' + identifier).encode()).hexdigest()[:8], 16) % 100
    return 'train' if fraction < 80 else ('validation' if fraction < 90 else 'test')


def prepare(records, photos: Path, output: Path, *, maximum: int = 50, partition: str = 'test', exclude_ids=frozenset()):
    """Write manifest+gold only from locally present photographs and complete Unicode.

    Existing output is rejected, preventing accidental mixing of two datasets.
    """
    photos, output = Path(photos).resolve(), Path(output).resolve()
    if maximum < 1 or maximum > 10000:
        raise ValueError('max-tablets debe estar entre 1 y 10000')
    if partition not in ('all', 'train', 'validation', 'test'):
        raise ValueError('Split inválido')
    if not photos.is_dir():
        raise ValueError('No existe la carpeta de fotos')
    if output.exists():
        raise ValueError('La carpeta de salida ya existe; elegí una carpeta nueva')
    selected = []
    seen = set()
    stats = {'metadata_rows': 0, 'invalid_or_incomplete': 0, 'not_in_partition': 0,
             'excluded_ids': 0, 'missing_local_photo': 0, 'duplicate_ids': 0}
    # Sort by ID rather than relying on the source file's iteration order.
    candidates = []
    for record in records:
        stats['metadata_rows'] += 1
        if not isinstance(record, dict):
            stats['invalid_or_incomplete'] += 1
            continue
        try:
            identifier = canonical_id(record.get('id'))
            text, count = reference_glyphs(record)
        except ValueError:
            stats['invalid_or_incomplete'] += 1
            continue
        if identifier in seen:
            stats['duplicate_ids'] += 1
            continue
        seen.add(identifier)
        if identifier in exclude_ids:
            stats['excluded_ids'] += 1
            continue
        if partition != 'all' and split_for(identifier) != partition:
            stats['not_in_partition'] += 1
            continue
        photo = find_photo(photos, identifier)
        if photo is None:
            stats['missing_local_photo'] += 1
            continue
        candidates.append((identifier, photo, text, count))
    candidates.sort(key=lambda item: item[0])
    selected = candidates[:maximum]
    if not selected:
        raise ValueError('No hay pares válidos imagen/Unicode; revisá los IDs, la carpeta de fotos y el split')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'images').mkdir()
    manifest, gold, audit = [], [], []
    for identifier, photo, reference, n in selected:
        dest = output / 'images' / photo.name
        shutil.copy2(photo, dest)
        manifest.append({'id': identifier, 'image': 'images/' + dest.name})
        gold.append({'id': identifier, 'text': reference})
        audit.append({'id': identifier, 'source_filename': photo.name, 'image_sha256': sha256(dest),
                      'reference_sign_count': n, 'partition': split_for(identifier)})
    atomic_jsonl(output / 'manifest.jsonl', manifest)
    atomic_jsonl(output / 'gold.jsonl', gold)
    atomic_jsonl(output / 'audit.jsonl', audit)
    summary = {'format': 'cuneilab-cuneiml-benchmark', 'version': 1,
               'source': SOURCE_URL, 'source_version': '1.2',
               'partition': partition, 'images_selected': len(selected), 'stats': stats,
               'model_holdout_verified': False,
               'warning': 'Evaluación exploratoria: CuneiML puede coincidir con el entrenamiento de NabuOCR; este split por ID NO verifica independencia respecto al modelo. Los derechos de las fotografías deben verificarse por separado.',
               'reference': 'CuneiML (Chen et al.); doi:10.5281/zenodo.10806319'}
    atomic_json(output / 'dataset.json', summary)
    return summary


def excluded_ids(path):
    if not path:
        return set()
    result = set()
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        token = line.strip()
        if not token or token.startswith('#'):
            continue
        result.add(canonical_id(token))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Preparar benchmark exploratorio CuneiML desde fotos LOCALES')
    parser.add_argument('--metadata', required=True, type=Path, help='Archivo CuneiMLv1.2.json original')
    parser.add_argument('--verify-md5', action='store_true', help='Comprobar checksum MD5 publicado por Zenodo antes de abrir el archivo')
    parser.add_argument('--photos', required=True, type=Path, help='Carpeta con imágenes P123456.jpg/png/webp obtenidas legítimamente')
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--max-tablets', type=int, default=50)
    parser.add_argument('--split', choices=['all', 'train', 'validation', 'test'], default='test')
    parser.add_argument('--exclude-ids', type=Path, help='Lista de IDs conocidos del entrenamiento (uno por línea)')
    args = parser.parse_args(argv)
    try:
        if args.verify_md5 and md5_file(args.metadata) != SOURCE_MD5:
            raise ValueError('Checksum MD5 de CuneiML distinto del publicado por Zenodo (v1.2). No se usó el archivo.')
        report = prepare(records_from_metadata(args.metadata), args.photos, args.output_dir,
                         maximum=args.max_tablets, partition=args.split, exclude_ids=excluded_ids(args.exclude_ids))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f'Error: {exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
