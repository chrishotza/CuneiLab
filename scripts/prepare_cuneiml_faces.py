"""Face-aligned, auditable CuneiML image benchmark (no automatic OCR).

CuneiML `bboxes` specifies a major image cutout, not its orientation/face.
A human must confirm the face of each *cropped* image before producing gold.
Original photographs are not downloaded; their rights remain with the source.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.batch_nabu import atomic_json, atomic_jsonl, sha256
from scripts.prepare_cuneiml import (FACE_ORDER, SOURCE_URL, SOURCE_MD5, canonical_id,
    excluded_ids, find_photo, md5_file, records_from_metadata, split_for)
from transcription import is_sign, sign_count

HEX_SHA = re.compile(r'[0-9a-f]{64}\Z')


def reference_for_face(record: dict, face: str) -> tuple[str, int]:
    """Reject a damaged/incomplete face instead of silently dropping its signs."""
    if face not in FACE_ORDER:
        raise ValueError('Cara no reconocida')
    text = record.get('text')
    if not isinstance(text, dict) or face not in text:
        raise ValueError('No hay transcripción de esta cara')
    lines = text[face]
    if not isinstance(lines, list) or not lines:
        raise ValueError('La cara no tiene líneas')
    rendered = []
    for line in lines:
        if not isinstance(line, dict) or not isinstance(line.get('sign'), list):
            raise ValueError('Línea sin Unicode')
        parts = line['sign']
        if not parts or not all(isinstance(part, str) and part and all(is_sign(c) for c in part) for part in parts):
            raise ValueError('Cara dañada, incompleta o con signos desconocidos')
        rendered.append(' '.join(parts))
    result = '\n'.join(rendered)
    if sign_count(result) < 2:
        raise ValueError('Referencia demasiado corta')
    return result, sign_count(result)


def bbox_from_record(record: dict) -> tuple[int, int, int, int]:
    """Strictly parse CuneiML v1.2 major-face rectangle, never infer its face."""
    coords = record.get('bboxes')
    if not isinstance(coords, list) or len(coords) != 2 or any(
        not isinstance(pt, (tuple, list)) or len(pt) != 2 for pt in coords
    ):
        raise ValueError('bbox ausente o diferente de [[x1,y1],[x2,y2]]')
    flat = [x for pt in coords for x in pt]
    if any(type(x) not in (int, float) or not (-1e8 < x < 1e8) for x in flat):
        raise ValueError('bbox inválido')
    x1, y1, x2, y2 = map(int, flat)
    if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
        raise ValueError('bbox degenerado o fuera del origen')
    return x1, y1, x2, y2


def crop_as_png(photo: Path, bbox: tuple[int, int, int, int]) -> bytes:
    """Crop in unrotated original pixel coordinates used by CuneiML."""
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError('Instalá Pillow: py -3 -m pip install "Pillow>=10,<13"') from exc
    # Safety gate for abnormally large user-provided images.
    Image.MAX_IMAGE_PIXELS = 50_000_000
    try:
        with Image.open(photo) as im:
            width, height = im.size
            if width < 1 or height < 1 or width * height > 50_000_000:
                raise ValueError('Imagen demasiado grande o vacía')
            x1, y1, x2, y2 = bbox
            if x2 > width or y2 > height:
                raise ValueError('bbox fuera de los píxeles de la imagen')
            crop = im.crop(bbox).convert('RGB')
            buffer = io.BytesIO()
            crop.save(buffer, format='PNG')
            return buffer.getvalue()
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise ValueError(f'Imagen o recorte inválido: {exc}') from exc



def review_page(entries: list[dict]) -> str:
    """Standalone HTML tool to label local crops without editing JSON by hand.

    Images are relative files and never sent to any external server.
    """
    safe_rows = json.dumps(entries, ensure_ascii=False, separators=(',', ':'))
    safe_rows = safe_rows.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CuneiLab — revisión de caras</title>
<style>
:root{color-scheme:dark}body{background:#111b27;color:#f3f3ee;font-family:system-ui,sans-serif;margin:0}
header{position:sticky;top:0;background:#111b27ed;padding:14px 22px;border-bottom:1px solid #455263;z-index:3}
h1{font-size:1.2rem;margin:0 0 6px}p{margin:6px 0;color:#b6c7cf;line-height:1.45;font-size:.92rem}
.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:10px}button,select{background:#213649;color:white;border:1px solid #638295;border-radius:8px;padding:8px;font-size:.9rem}button{cursor:pointer;background:#285870;font-weight:600}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:16px;padding:20px}
article{border:1px solid #40536a;background:#172734;border-radius:10px;overflow:hidden;padding:12px}
article img{display:block;width:100%;height:240px;object-fit:contain;background:#08131e;border:1px solid #334b5e;border-radius:5px}
article h2{font-size:1rem;margin:10px 0}article label{display:block;color:#c7dae6;margin-bottom:5px;font-size:.85rem}
article select{width:100%}article.done{border-color:#3f9d74}small{display:block;color:#9cb1bc;margin-top:8px;overflow-wrap:anywhere}
</style></head><body>
<header><h1>CuneiLab · revisión visual de caras</h1>
<p>Elegí la cara visible del recorte SOLO si podés identificarla. No adivines. Esta página funciona sin conexión; no transmite imágenes.</p>
<div class="controls"><span id="count" aria-live="polite"></span><button id="save" type="button">Descargar mapa revisado (.jsonl)</button></div>
</header><main id="items"></main><script>
const entries=__ROWS__;
const faces=[['','Sin identificar'],['obverse','Anverso'],['reverse','Reverso'],['left','Lateral izquierdo'],['right','Lateral derecho'],['top','Superior'],['bottom','Inferior']];
const root=document.getElementById('items');const status=document.getElementById('count');
function update(){status.textContent=entries.filter(e=>e.face).length+' / '+entries.length+' caras identificadas';}
for(const entry of entries){
 const article=document.createElement('article');article.className=entry.face?'done':'';
 const title=document.createElement('h2');title.textContent=entry.id;article.append(title);
 const img=document.createElement('img');img.src=entry.image;img.alt='Recorte de '+entry.id;img.loading='lazy';article.append(img);
 const label=document.createElement('label');label.textContent='Cara que muestra el recorte';article.append(label);
 const select=document.createElement('select');select.setAttribute('aria-label','Cara de '+entry.id);
 for(const [code,name] of faces){const opt=document.createElement('option');opt.value=code;opt.textContent=name;select.append(opt);}
 select.value=entry.face||'';select.addEventListener('change',()=>{entry.face=select.value||null;article.className=entry.face?'done':'';update();});article.append(select);
 const detail=document.createElement('small');detail.textContent='Recorte: '+entry.crop_box.join(', ')+' · SHA256 '+entry.crop_sha256.slice(0,12)+'…';article.append(detail);
 root.append(article);
}
update();
document.getElementById('save').addEventListener('click',()=>{
 const lines=entries.map(e=>JSON.stringify(e)).join('\\n')+'\\n';
 const url=URL.createObjectURL(new Blob([lines],{type:'application/x-ndjson;charset=utf-8'}));
 const a=document.createElement('a');a.href=url;a.download='faces_revisadas.jsonl';a.click();
 setTimeout(()=>URL.revokeObjectURL(url),2000);
});
</script></body></html>""".replace('__ROWS__', safe_rows)

def load_face_map(path: Path) -> dict[str, dict]:
    """Human-edited JSONL from --review. Every accepted face requires crop hash."""
    rows = {}
    for i, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Mapa de caras línea {i}: JSON inválido') from exc
        if not isinstance(row, dict):
            raise ValueError(f'Mapa de caras línea {i}: se esperaba objeto')
        identifier = canonical_id(row.get('id'))
        if identifier in rows:
            raise ValueError(f'Mapa de caras: ID repetido {identifier}')
        face = row.get('face')
        if face is not None and face not in FACE_ORDER:
            raise ValueError(f'{identifier}: cara inválida; usar obverse, reverse, left, right, top o bottom')
        if not isinstance(row.get('crop_sha256'), str) or not HEX_SHA.fullmatch(row['crop_sha256']):
            raise ValueError(f'{identifier}: falta huella SHA-256 del recorte revisado')
        if not isinstance(row.get('source_sha256'), str) or not HEX_SHA.fullmatch(row['source_sha256']):
            raise ValueError(f'{identifier}: falta huella SHA-256 de la fotografía original')
        rows[identifier] = row
    if not rows:
        raise ValueError('El mapa de caras está vacío')
    return rows


def _candidates(records, photos, *, partition, exclude_ids):
    stats = {'metadata_rows': 0, 'invalid_metadata': 0, 'duplicate_ids': 0,
             'not_in_partition': 0, 'excluded_ids': 0, 'missing_photo': 0}
    seen = set()
    for record in records:
        stats['metadata_rows'] += 1
        if not isinstance(record, dict):
            stats['invalid_metadata'] += 1
            continue
        try:
            identifier = canonical_id(record.get('id'))
            bbox = bbox_from_record(record)
        except ValueError:
            stats['invalid_metadata'] += 1
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
            stats['missing_photo'] += 1
            continue
        yield identifier, record, photo, bbox, stats


def make_dataset(records, photos: Path, output: Path, *, mode: str = 'review',
                 face_map=None, maximum=50, partition='test', exclude_ids=frozenset()):
    """Two-phase workflow: review crops first, then prepare face-aligned gold.

    Existing output is never overwritten. Build in a temporary directory and
    rename only once all accepted records are written.
    """
    photos = Path(photos).resolve()
    output = Path(output).resolve()
    if mode not in ('review', 'prepare'):
        raise ValueError('Modo inválido')
    if not 1 <= maximum <= 10_000:
        raise ValueError('max-tablets debe estar entre 1 y 10000')
    if partition not in ('test', 'validation', 'train', 'all'):
        raise ValueError('Split inválido')
    if not photos.is_dir() or not output.parent.is_dir() or output.exists():
        raise ValueError('Fotos o carpeta de salida inválidas / salida ya existe')
    if mode == 'prepare' and face_map is None:
        raise ValueError('Falta el mapa de caras revisado')
    face_rows = load_face_map(face_map) if mode == 'prepare' else {}
    stats = {'invalid_crop': 0, 'unreviewed': 0, 'damaged_or_missing_face_text': 0,
             'reviewed_other_partition': 0}
    selected = []
    # Deterministic sampling order independent of upstream JSON row order.
    # Stable hash order avoids taking only the numerically smallest CDLI IDs.
    def sample_key(record):
        identifier = record.get('id', '') if isinstance(record, dict) else ''
        try:
            identifier = canonical_id(identifier)
        except ValueError:
            identifier = repr(identifier)
        return hashlib.sha256(('cuneilab-v08-sample:' + identifier).encode()).hexdigest()
    iterator = _candidates(sorted(records, key=sample_key), photos,
                           partition=partition, exclude_ids=exclude_ids)
    for identifier, record, photo, bbox, base_stats in iterator:
        if mode == 'prepare' and identifier not in face_rows:
            stats['unreviewed'] += 1
            continue
        try:
            png = crop_as_png(photo, bbox)
        except ValueError:
            stats['invalid_crop'] += 1
            continue
        src_hash = sha256(photo)
        crop_hash = hashlib.sha256(png).hexdigest()
        face = None
        reference = None
        sign_total = None
        if mode == 'prepare':
            face_row = face_rows[identifier]
            face = face_row['face']
            if face is None:
                stats['unreviewed'] += 1
                continue
            if face_row['source_sha256'] != src_hash or face_row['crop_sha256'] != crop_hash:
                raise ValueError(f'{identifier}: la foto/el recorte cambió después de la revisión')
            try:
                reference, sign_total = reference_for_face(record, face)
            except ValueError:
                stats['damaged_or_missing_face_text'] += 1
                continue
        selected.append((identifier, photo, bbox, png, src_hash, crop_hash, face, reference, sign_total))
        if len(selected) >= maximum:
            break
    # Generator stats are mutable and shared; populated while iterating.
    stats.update(base_stats if 'base_stats' in locals() else {})
    if not selected:
        raise ValueError('No hay imágenes válidas seleccionadas; revisá fotos, bbox, split y mapa de caras')
    selected.sort(key=lambda item: item[0])
    with tempfile.TemporaryDirectory(prefix='.cuneilab-staging-', dir=output.parent) as staging:
        stage = Path(staging) / output.name
        stage.mkdir()
        (stage / 'images').mkdir()
        manifest, gold, review, audit = [], [], [], []
        for identifier, photo, bbox, png, src_hash, crop_hash, face, reference, n in selected:
            name = f'{identifier}_crop.png' if mode == 'review' else f'{identifier}_{face}.png'
            (stage / 'images' / name).write_bytes(png)
            preview = {'id': identifier, 'face': face, 'source_sha256': src_hash,
                       'crop_sha256': crop_hash, 'crop_box': list(bbox),
                       'image': 'images/' + name}
            review.append(preview)
            if mode == 'prepare':
                item_id = f'{identifier}-{face}'
                manifest.append({'id': item_id, 'image': 'images/' + name})
                gold.append({'id': item_id, 'text': reference})
                audit.append({**preview, 'benchmark_id': item_id,
                              'reference_sign_count': n, 'split': split_for(identifier),
                              'source_url': SOURCE_URL})
        if mode == 'review':
            atomic_jsonl(stage / 'faces_template.jsonl', review)
            (stage / 'revisar_caras.html').write_text(review_page(review), encoding='utf-8')
            (stage / 'INSTRUCCIONES.txt').write_text(
                'Abrí cada recorte en images/, reconocé si se ve el anverso, reverso u otra cara.\n'
                'Abrí revisar_caras.html, elegí las caras que realmente reconozcas y descargá faces_revisadas.jsonl.\n'
                'No adivines: dejá null si no sabés la cara. NO edites los hashes.\n'
                'Luego corré --mode prepare --face-map <faces_revisadas.jsonl> (en tu carpeta Descargas).\n', encoding='utf-8')
        else:
            atomic_jsonl(stage / 'manifest.jsonl', manifest)
            atomic_jsonl(stage / 'gold.jsonl', gold)
            atomic_jsonl(stage / 'audit.jsonl', audit)
        summary = {'format': 'cuneilab-cuneiml-faces', 'version': 2, 'mode': mode,
                   'partition': partition, 'selected': len(selected), 'stats': stats,
                   'source': SOURCE_URL, 'face_alignment': 'human-reviewed' if mode == 'prepare' else 'pending',
                   'model_holdout_verified': False,
                   'warning': 'No es un benchmark independiente de NabuOCR. Identificar caras manualmente no prueba ausencia de fuga de datos.'}
        atomic_json(stage / 'dataset.json', summary)
        stage.rename(output)
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description='CuneiML: recortes revisables y benchmark por cara, NO por tablilla entera')
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--photos', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--mode', choices=['review', 'prepare'], default='review')
    p.add_argument('--face-map', type=Path)
    p.add_argument('--max-tablets', type=int, default=50)
    p.add_argument('--split', choices=['test', 'validation', 'train', 'all'], default='test')
    p.add_argument('--exclude-ids', type=Path)
    p.add_argument('--verify-md5', action='store_true')
    a = p.parse_args(argv)
    try:
        if a.verify_md5 and md5_file(a.metadata) != SOURCE_MD5:
            raise ValueError('El MD5 del archivo CuneiML no coincide con el publicado')
        result = make_dataset(records_from_metadata(a.metadata), a.photos, a.output_dir,
                              mode=a.mode, face_map=a.face_map, maximum=a.max_tablets,
                              partition=a.split, exclude_ids=excluded_ids(a.exclude_ids))
    except (ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        p.exit(2, f'Error: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
