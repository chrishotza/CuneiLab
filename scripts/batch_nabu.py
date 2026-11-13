"""Reproducible batch OCR runner: one model load, image hashes, resumable results.

Input manifest JSONL: {"id":"P000001", "image":"images/P000001.jpg"}.
Paths stay within the manifest directory. This tool does not invent gold labels.
--check validates and fingerprints inputs without downloading any model weights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from transcription import validate
from scripts.run_nabu_ocr import NabuSession, DEFAULT_MODEL

ID_PATTERN=re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z')
REVISION_PATTERN=re.compile(r'[a-fA-F0-9]{40}\Z')
EXTS={'.jpg','.jpeg','.png','.webp'}
MAX_IMAGES=100000
MAX_BYTES=100*1024*1024


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as fd:
        for block in iter(lambda:fd.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path):
    path=Path(path).resolve(strict=True)
    base=path.parent
    entries=[]
    seen=set()
    for line_no,line in enumerate(path.read_text(encoding='utf8').splitlines(),1):
        if not line.strip():continue
        try: row=json.loads(line)
        except json.JSONDecodeError as exc:raise ValueError(f'Línea {line_no}: JSON inválido') from exc
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not isinstance(row.get('image'),str):
            raise ValueError(f'Línea {line_no}: se necesitan id e image')
        name=row['id']; relative=Path(row['image'])
        if not ID_PATTERN.fullmatch(name) or name in {'.','..'} or name in seen:
            raise ValueError(f'Línea {line_no}: ID inseguro o repetido: {name!r}')
        if relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() not in EXTS:
            raise ValueError(f'Línea {line_no}: ruta de imagen inválida')
        resolved=(base/relative).resolve()
        if not resolved.is_relative_to(base) or not resolved.is_file():
            raise ValueError(f'Línea {line_no}: imagen inexistente o fuera del directorio de datos')
        size=resolved.stat().st_size
        if size<=0 or size>MAX_BYTES:
            raise ValueError(f'Línea {line_no}: tamaño no admitido ({size} bytes)')
        entries.append({'id':name,'image':row['image'],'path':resolved,'image_sha256':sha256(resolved),'bytes':size})
        seen.add(name)
        if len(entries)>MAX_IMAGES:raise ValueError('Demasiadas imágenes')
    if not entries:raise ValueError('El manifiesto está vacío')
    return entries


def fingerprint(entries,model,revision,max_tokens):
    canonical={'model':model,'revision':revision,'max_new_tokens':max_tokens,
               'images':[{'id':e['id'],'image':e['image'],'sha256':e['image_sha256']} for e in entries]}
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def atomic_json(path,obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    try:
        tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_jsonl(path,records):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    try:
        with tmp.open('w',encoding='utf8',newline='\n') as f:
            for row in records:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)


def run_batch(entries,output,*,model,revision,max_tokens=1024,runner=None,resume=False):
    """runner(image_path)->validated CuneiLab document. Inject for offline testing."""
    if not REVISION_PATTERN.fullmatch(revision):raise ValueError('Usá una revisión SHA completa de 40 caracteres')
    if not (1<=max_tokens<=4096):raise ValueError('max_tokens fuera de rango')
    output=Path(output)
    meta_path=output/'run.json'
    predictions_path=output/'predictions.jsonl'
    errors_path=output/'errors.jsonl'
    digest=fingerprint(entries,model,revision,max_tokens)
    prior={}
    if output.exists() and any(output.iterdir()):
        if not resume:raise ValueError('La carpeta de resultados no está vacía; usá otra o --resume')
        if not meta_path.is_file() or not predictions_path.is_file():
            raise ValueError('Faltan archivos de una ejecución anterior; no es seguro reanudar')
        existing=json.loads(meta_path.read_text(encoding='utf8'))
        if existing.get('fingerprint')!=digest:
            raise ValueError('El manifiesto, las imágenes o el modelo cambiaron; no se puede reanudar')
        for line in predictions_path.read_text(encoding='utf8').splitlines():
            if not line.strip():continue
            row=json.loads(line)
            if row['id'] in prior or row['id'] not in {e['id'] for e in entries}:
                raise ValueError('Resultados existentes inconsistentes')
            prior[row['id']]=row
    output.mkdir(parents=True,exist_ok=True)
    # Write provenance before any inference; a crash will still leave auditable metadata.
    atomic_json(meta_path,{'format':'cuneilab-batch','version':1,'fingerprint':digest,
                           'model':model,'revision':revision,'max_new_tokens':max_tokens,
                           'images':[{k:e[k] for k in ('id','image','image_sha256','bytes')} for e in entries]})
    results=dict(prior)
    errors=[]
    # Make crash recovery valid even when interruption precedes the first prediction.
    if not predictions_path.exists():atomic_jsonl(predictions_path,[])
    if not errors_path.exists():atomic_jsonl(errors_path,[])
    for e in entries:
        if e['id'] in results:continue
        try:
            if runner is None:raise RuntimeError('No hay motor OCR inicializado')
            doc=validate(runner(e['path']))
            if doc['image_filename']!=e['path'].name:
                raise ValueError('El OCR devolvió el nombre de otra fotografía')
            if doc['model']!=f'{model}@{revision}':
                raise ValueError('La procedencia del modelo no coincide con la ejecución')
            row={'id':e['id'],'text':doc['text'],'image_sha256':e['image_sha256'],
                 'model':doc['model'],'sign_count':doc['sign_count']}
            results[e['id']]=row
            atomic_json(output/'documents'/f'{e["id"]}.json',doc)
        except Exception as exc:
            errors.append({'id':e['id'],'error_type':type(exc).__name__,'error':str(exc)[:300]})
        atomic_jsonl(predictions_path,[results[e['id']] for e in entries if e['id'] in results])
        atomic_jsonl(errors_path,errors)
    atomic_jsonl(predictions_path,[results[e['id']] for e in entries if e['id'] in results])
    atomic_jsonl(errors_path,errors)
    summary={'total':len(entries),'succeeded':len(results),'failed':len(errors),
             'skipped_resumed':len(prior),'fingerprint':digest,
             'predictions':str(predictions_path),'failures':str(errors_path),
             'note':'No se reporta accuracy sin archivo gold independiente.'}
    atomic_json(output/'summary.json',summary)
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description='OCR cuneiforme por lotes, sin falsificar métricas')
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,default=Path('data/ocr/batch'))
    p.add_argument('--model',default=DEFAULT_MODEL)
    p.add_argument('--revision',help='SHA completo del modelo fijado')
    p.add_argument('--device',choices=['auto','cpu','cuda','cuda:0'],default='auto')
    p.add_argument('--max-new-tokens',type=int,default=1024)
    p.add_argument('--check',action='store_true',help='Solo validar y calcular hashes sin cargar modelo')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--trust-remote-code',action='store_true')
    a=p.parse_args(argv)
    try:
        entries=read_manifest(a.manifest)
        if not 1<=a.max_new_tokens<=4096:
            p.error('--max-new-tokens debe estar entre 1 y 4096')
        if a.check:
            print(json.dumps({'images':len(entries),'bytes':sum(e['bytes'] for e in entries),
                              'ids':[e['id'] for e in entries][:10],
                              'note':'Entrada validada; NO se ejecutó inferencia'},ensure_ascii=False,indent=2))
            return 0
        if not a.trust_remote_code:
            p.error('Requiere --trust-remote-code; revisá primero el código de terceros')
        if not a.revision or not REVISION_PATTERN.fullmatch(a.revision):
            p.error('Requiere --revision con SHA de 40 caracteres')
        # Validate output and resume metadata BEFORE loading expensive weights.
        if a.output_dir.exists() and any(a.output_dir.iterdir()):
            if not a.resume:p.error('La salida ya contiene datos; elegí otro directorio o --resume')
            run_file=a.output_dir/'run.json'
            if not run_file.exists() or json.loads(run_file.read_text(encoding='utf8')).get('fingerprint')!=fingerprint(entries,a.model,a.revision,a.max_new_tokens):
                p.error('La ejecución anterior no coincide; reanudar cancelado')
        session=NabuSession(a.model,a.device,a.revision,trust_remote_code=True)
        result=run_batch(entries,a.output_dir,model=a.model,revision=a.revision,
                         max_tokens=a.max_new_tokens,
                         runner=lambda path:session.predict(path,max_new_tokens=a.max_new_tokens),
                         resume=a.resume)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if not result['failed'] else 2
    except (OSError,ValueError) as exc:
        p.error(str(exc))

if __name__=='__main__':raise SystemExit(main())
