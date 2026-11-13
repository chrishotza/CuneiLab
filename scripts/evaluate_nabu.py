"""Evaluate Unicode OCR predictions against user-supplied held-out gold standard.

Reference and prediction JSONL: each line {"id":"P123456","text":"𒀭𒆠..."}.
This reports glyph-level edit rate; it does NOT reproduce the author's tokenizer TER.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from transcription import score, TranscriptionError


def read_jsonl(path):
    rows={}
    for n,line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(),1):
        if not line.strip():continue
        obj=json.loads(line)
        if not isinstance(obj,dict) or not isinstance(obj.get('id'),str) or not isinstance(obj.get('text'),str):
            raise ValueError(f'{path}:{n}: se requieren id y text')
        if obj['id'] in rows: raise ValueError(f'{path}:{n}: ID duplicado {obj["id"]}')
        rows[obj['id']]=obj['text']
    if not rows: raise ValueError('El JSONL está vacío')
    return rows


def evaluate(gold, predicted):
    missing=sorted(set(gold)-set(predicted)); extra=sorted(set(predicted)-set(gold))
    scored=[]
    for name in sorted(set(gold)&set(predicted)):
        try: metrics=score(gold[name],predicted[name])
        except TranscriptionError as e: raise ValueError(f'{name}: {e}') from e
        scored.append({'id':name,**metrics})
    edits=sum(r['edit_errors'] for r in scored)
    tokens=sum(r['reference_tokens'] for r in scored)
    # Count absent predictions as complete deletions in the dataset-wide metric.
    # Otherwise a model returning only its easiest image could appear perfect.
    missing_tokens=sum(score(gold[name], '')['reference_tokens'] for name in missing)
    all_tokens=tokens+missing_tokens
    return {'images_scored':len(scored),'missing_predictions':missing,'unmatched_predictions':extra,
            'micro_sign_error_rate':(edits/tokens if tokens else None),
            'coverage_images':(len(scored)/len(gold) if gold else None),
            'micro_sign_error_rate_including_missing':((edits+missing_tokens)/all_tokens if all_tokens else None),
            'missing_reference_signs':missing_tokens,
            'all_reference_signs':all_tokens,
            'dataset_warning':'The including_missing metric treats each missing OCR output as deleting every reference sign; both error rates can exceed 1 with insertions.',
            'macro_sign_error_rate':(sum(r['sign_error_rate'] for r in scored)/len(scored) if scored else None),
            'total_edit_errors':edits,'reference_signs':tokens,
            'metric':'Levenshtein over Unicode signs and surface markers (not BPE/tokenizer TER)',
            'items':scored}


def main(argv=None):
    p=argparse.ArgumentParser(description='Evaluate image OCR against held-out Unicode transcriptions')
    p.add_argument('--gold',type=Path,required=True,help='JSONL con {id,text} de referencia')
    p.add_argument('--predicted',type=Path,required=True,help='JSONL con {id,text} generados')
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv)
    report=evaluate(read_jsonl(a.gold),read_jsonl(a.predicted))
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(text,encoding='utf-8')
    print(text)
    if not report['images_scored']:
        raise SystemExit('No hay identificadores compartidos: evaluación cancelada')

if __name__=='__main__':main()
