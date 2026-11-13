"""Strict, dependency-free interchange format and evaluation for visual sign detections.

The OCR output is *sign-class hypotheses*, not transliteration or translation.
Coordinates are pixel-space COCO XYWH in the ORIGINAL image dimensions.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

MAX_SIGNS = 5000
MAX_LABEL = 120


class VisionFormatError(ValueError):
    """A prediction file is invalid or incompatible with the supplied image."""


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise VisionFormatError(f'{field} debe ser un número finito')
    return float(value)


def _size(info):
    if not isinstance(info, dict):
        raise VisionFormatError('Se requiere image: {width, height}')
    w = _number(info.get('width'), 'image.width')
    h = _number(info.get('height'), 'image.height')
    if not (0 < w <= 30000 and 0 < h <= 30000):
        raise VisionFormatError('Dimensiones de imagen inválidas')
    return w, h


def _prediction(d, width, height):
    if not isinstance(d, dict) or not isinstance(d.get('bbox'), list) or len(d['bbox']) != 4:
        raise VisionFormatError('Cada predicción requiere bbox: [x,y,ancho,alto]')
    x, y, w, h = [_number(v, 'bbox') for v in d['bbox']]
    if not (0 <= x < width and 0 <= y < height and w > 0 and h > 0 and x + w <= width + 0.001 and y + h <= height + 0.001):
        raise VisionFormatError('Recuadro fuera de la imagen o sin superficie')
    label = str(d.get('label', '')).strip()
    if not (0 < len(label) <= MAX_LABEL):
        raise VisionFormatError('Cada predicción requiere una clase de signo (label)')
    confidence = _number(d.get('confidence', 1.0), 'confidence')
    if not 0 <= confidence <= 1:
        raise VisionFormatError('La confianza debe estar entre 0 y 1')
    reading = d.get('reading', '')
    if not isinstance(reading, str) or len(reading) > 100:
        raise VisionFormatError('reading debe ser texto breve o vacío')
    return dict(bbox=[x, y, w, h], label=label, confidence=confidence, reading=reading)


def validate_predictions(document):
    """Validate a canonical CuneiLab JSON object, returning a sanitized copy."""
    if not isinstance(document, dict) or document.get('format') != 'cuneilab-detections' or document.get('version') != 1:
        raise VisionFormatError('Formato esperado: cuneilab-detections versión 1')
    w, h = _size(document.get('image'))
    raw = document.get('detections')
    if not isinstance(raw, list) or len(raw) > MAX_SIGNS:
        raise VisionFormatError(f'detections debe contener hasta {MAX_SIGNS} signos')
    source = str(document.get('source', 'sin especificar'))[:180]
    return {'format': 'cuneilab-detections', 'version': 1,
            'image': {'width': int(w), 'height': int(h)},
            'source': source, 'detections': [_prediction(d, w, h) for d in raw]}


def from_coco(document, image_filename=None):
    """Accept COCO annotations for one image. COCO labels are *not* readings."""
    if not isinstance(document, dict) or not all(isinstance(document.get(k), list) for k in ('images', 'categories', 'annotations')):
        raise VisionFormatError('COCO requiere images, categories y annotations')
    if image_filename:
        images = [im for im in document['images'] if Path(str(im.get('file_name', ''))).name == Path(image_filename).name]
    else:
        images = document['images']
    if len(images) != 1:
        raise VisionFormatError('COCO debe contener exactamente una imagen coincidente; seleccioná su nombre')
    im = images[0]
    names = {cat.get('id'): str(cat.get('name', '')) for cat in document['categories'] if isinstance(cat, dict)}
    items = []
    for row in document['annotations']:
        if row.get('image_id') != im.get('id'):
            continue
        label = names.get(row.get('category_id'))
        if not label:
            raise VisionFormatError('category_id desconocido')
        items.append({'bbox': row.get('bbox'), 'label': label,
                      'confidence': row.get('score', 1.0), 'reading': ''})
    return validate_predictions({'format': 'cuneilab-detections', 'version': 1,
                                 'image': {'width': im.get('width'), 'height': im.get('height')},
                                 'source': 'COCO (clases sin transliterar)', 'detections': items})


def load_document(path, image_filename=None):
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(document, dict) and document.get('format') == 'cuneilab-detections':
        return validate_predictions(document)
    return from_coco(document, image_filename)


def from_mmdet(pred_instances, width, height, classes, threshold=0.35, source='eBL/MMDetection'):
    """Build canonical predictions from MMDetection DetDataSample.pred_instances.

    MMDetection bboxes are XYXY; CuneiLab stores XYWH. Unknown class IDs
    remain visible as CLASS_N but never receive invented phonetic readings.
    """
    threshold = _number(threshold, 'threshold')
    if not 0 <= threshold <= 1:
        raise VisionFormatError('threshold fuera de [0,1]')
    rows = []
    for bbox, score, class_index in zip(pred_instances.bboxes.tolist(),
                                       pred_instances.scores.tolist(),
                                       pred_instances.labels.tolist()):
        if score < threshold:
            continue
        index = int(class_index)
        if index < 0:
            raise VisionFormatError('Identificador de clase inválido')
        label = classes[index] if index < len(classes) else f'CLASS_{index}'
        x1, y1, x2, y2 = map(float, bbox)
        # Models occasionally return boxes marginally outside the image.
        x1, x2 = max(0, min(width, x1)), max(0, min(width, x2))
        y1, y2 = max(0, min(height, y1)), max(0, min(height, y2))
        if x2 <= x1 or y2 <= y1:
            continue
        rows.append({'bbox': [x1, y1, x2 - x1, y2 - y1],
                     'label': str(label), 'confidence': float(score), 'reading': ''})
    rows.sort(key=lambda r: r['confidence'], reverse=True)
    return validate_predictions({'format': 'cuneilab-detections', 'version': 1,
                                 'image': {'width': width, 'height': height},
                                 'source': source, 'detections': rows[:MAX_SIGNS]})


def iou(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    w = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    h = max(0, min(ay + ah, by + bh) - max(ay, by))
    overlap = w * h
    union = aw * ah + bw * bh - overlap
    return overlap / union if union else 0.0


def evaluate(reference, predictions, iou_threshold=0.5, score_threshold=0):
    """Class-aware greedy matching; diagnostic P/R/F1, not COCO mAP."""
    ref = validate_predictions(reference)
    pred = validate_predictions(predictions)
    if ref['image'] != pred['image']:
        raise VisionFormatError('No coinciden dimensiones de imagen')
    if not 0 < iou_threshold <= 1 or not 0 <= score_threshold <= 1:
        raise VisionFormatError('Umbral inválido')
    truth = ref['detections']
    ordered = sorted((r for r in pred['detections'] if r['confidence'] >= score_threshold),
                     key=lambda r: r['confidence'], reverse=True)
    remaining = set(range(len(truth)))
    tp = 0
    for detection in ordered:
        candidates = [(iou(detection['bbox'], truth[k]['bbox']), k)
                      for k in remaining if truth[k]['label'] == detection['label']]
        if not candidates:
            continue
        best, index = max(candidates)
        if best >= iou_threshold:
            remaining.remove(index)
            tp += 1
    fp, fn = len(ordered) - tp, len(truth) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {'true_positives': tp, 'false_positives': fp, 'false_negatives': fn,
            'precision': precision, 'recall': recall,
            'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            'iou_threshold': iou_threshold, 'score_threshold': score_threshold,
            'metric': 'class-aware greedy IoU; NOT COCO mAP'}
