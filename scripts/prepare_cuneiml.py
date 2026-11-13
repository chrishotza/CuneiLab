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


def prepare(*args, **kwargs):
    """Unsafe v0.7 method retired: cropped photos cannot be matched to all faces."""
    raise ValueError('v0.7 sin alineación de caras está desactivada; usá make_dataset en scripts.prepare_cuneiml_faces')


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
    """Safety redirect: v0.7 generated whole-tablet gold for one crop."""
    from scripts.prepare_cuneiml_faces import main as face_main
    return face_main(argv)


if __name__ == '__main__':
    raise SystemExit(main())
