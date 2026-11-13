"""Quick one-image class-aware detection diagnostic (NOT COCO mAP)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision import load_document, evaluate


def main():
    parser = argparse.ArgumentParser(description='Comparar predicciones con cajas de referencia corregidas')
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--iou', type=float, default=0.5)
    parser.add_argument('--score', type=float, default=0.35)
    args = parser.parse_args()
    print(json.dumps(evaluate(load_document(args.reference), load_document(args.predictions),
                              args.iou, args.score), indent=2))


if __name__ == '__main__':
    main()
