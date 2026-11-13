"""Optional eBL DETR/MMDetection inference (needs separately installed model/weights).

Example (from project root):
  python scripts/run_ebl_ocr.py --image data/tablet.jpg --config path/to/detr.py \\
    --checkpoint path/to/epoch_1000.pth --classes data/classes.json --output data/signs.json

CuneiLab never downloads or silently substitutes weights; follow the upstream
project's version-specific environment and verify class mapping before use.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vision import from_mmdet


def run(args):
    if not args.image.is_file() or not args.config.is_file() or not args.checkpoint.is_file():
        raise FileNotFoundError('Falta imagen, configuración o checkpoint; consultá README.')
    try:
        from PIL import Image
        from mmdet.apis import init_detector, inference_detector
    except ImportError as exc:
        raise RuntimeError('Instalá Pillow y el entorno PyTorch/MMDetection compatible con eBL.') from exc
    with Image.open(args.image) as img:
        width, height = img.size
    model = init_detector(str(args.config), str(args.checkpoint), device=args.device)
    names = model.dataset_meta.get('classes', ()) if hasattr(model, 'dataset_meta') else ()
    if args.classes:
        loaded = json.loads(args.classes.read_text(encoding='utf-8'))
        if not isinstance(loaded, list) or not all(isinstance(v, str) and v for v in loaded):
            raise ValueError('El JSON de clases debe ser una lista de nombres no vacíos')
        names = loaded
    if not names:
        raise ValueError('No se encontró el orden de clases. Proporcioná --classes con los nombres EXACTOS del modelo.')
    output = inference_detector(model, str(args.image))
    preds = from_mmdet(output.pred_instances, width, height, names, threshold=args.threshold,
                       source='eBL/MMDetection (clases, no lecturas)')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(preds, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(preds["detections"])} detecciones exportadas a {args.output}')


def main():
    parser = argparse.ArgumentParser(description='Ejecuta un checkpoint externo de detección cuneiforme eBL')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--classes', type=Path, help='Lista JSON de clases en el orden exacto del entrenamiento')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', default='cpu', help='cpu o cuda:0 (según disponibilidad)')
    parser.add_argument('--threshold', type=float, default=0.35)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
