"""CuneiLab Unicode OCR interchange & error metrics, no third-party dependencies.

OCR output is *visual glyph text*, not an ATF transliteration or Spanish translation.
The glyph-level error rate here is NOT NabuOCR's tokenizer-ID TER.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FORMAT = 'cuneilab-transcription'
FACES = {'obverse', 'reverse', 'left', 'right', 'top', 'bottom'}
FACE_MARKER = re.compile(r'@(?:obverse|reverse|left|right|top|bottom)\b')
MAX_TEXT = 250_000


class TranscriptionError(ValueError):
    pass


def is_sign(char):
    return len(char) == 1 and (0x12000 <= ord(char) <= 0x1254F)


def sign_count(text):
    return sum(map(is_sign, text))


def validate(document):
    if not isinstance(document, dict) or document.get('format') != FORMAT or document.get('version') != 1:
        raise TranscriptionError('Formato esperado: cuneilab-transcription v1')
    if document.get('kind') != 'unicode-ocr':
        raise TranscriptionError('Solo se admite OCR de glifos Unicode, no traducciones')
    raw = document.get('text')
    if not isinstance(raw, str) or not 0 < len(raw) <= MAX_TEXT or '\x00' in raw:
        raise TranscriptionError('Texto Unicode vacío, inválido o demasiado grande')
    if sign_count(raw) == 0:
        raise TranscriptionError('La predicción no contiene signos cuneiformes Unicode')
    image = document.get('image')
    if not isinstance(image, dict):
        raise TranscriptionError('Se necesitan dimensiones de imagen')
    w, h = image.get('width'), image.get('height')
    if (type(w) is not int or type(h) is not int or not (0 < w <= 30_000 and 0 < h <= 30_000)):
        raise TranscriptionError('Dimensiones de imagen inválidas')
    source = document.get('source')
    if not isinstance(source, str) or not source.strip() or len(source) > 180:
        raise TranscriptionError('Falta la procedencia del OCR')
    model = document.get('model', '')
    if not isinstance(model, str) or len(model) > 180:
        raise TranscriptionError('Identificador del modelo inválido')
    filename = document.get('image_filename', '')
    if not isinstance(filename, str) or len(filename) > 250 or '/' in filename or '\\' in filename:
        raise TranscriptionError('Nombre de archivo inválido')
    return {'format':FORMAT,'version':1,'kind':'unicode-ocr',
            'source':source.strip(),'model':model,'image':{'width':w,'height':h},
            'image_filename':filename, 'text':raw.replace('\r\n','\n'),
            'sign_count':sign_count(raw), 'confidence':'not_calibrated'}


def make_document(text, width, height, image_filename='', model='boatbomber/NabuOCR', source='NabuOCR (model output; unverified)'):
    return validate({'format':FORMAT,'version':1,'kind':'unicode-ocr','text':text,
                     'source':source,'model':model,'image':{'width':width,'height':height},
                     'image_filename':image_filename})


def glyph_tokens(text):
    """Sign codepoints and face markers; ignores whitespace and OCR prose.

    Use for simple reproducible sign edit rate. This is not a tokenizer BPE TER.
    """
    if not isinstance(text, str):
        raise TranscriptionError('Se esperaba texto')
    tokens = []
    cursor = 0
    for m in FACE_MARKER.finditer(text):
        tokens.extend(c for c in text[cursor:m.start()] if is_sign(c))
        tokens.append(m.group())
        cursor=m.end()
    tokens.extend(c for c in text[cursor:] if is_sign(c))
    return tokens


def edit_distance(expected, predicted):
    """O(min(n,m)) memory, standard Levenshtein; insertion errors may give TER > 1."""
    if len(expected) < len(predicted):
        expected, predicted = predicted, expected
    prev = list(range(len(predicted) + 1))
    for i, first in enumerate(expected, 1):
        row = [i]
        for j, second in enumerate(predicted, 1):
            row.append(min(row[j-1]+1,prev[j]+1,prev[j-1]+(first!=second)))
        prev = row
    return prev[-1]


def score(reference, prediction):
    ref=glyph_tokens(reference); pred=glyph_tokens(prediction)
    if not ref:
        raise TranscriptionError('La referencia no contiene signos para evaluar')
    if len(ref)>5000 or len(pred)>5000:
        raise TranscriptionError('Máximo 5000 signos/marcadores por par para evaluación')
    errors=edit_distance(ref,pred)
    return {'reference_tokens':len(ref),'predicted_tokens':len(pred),
            'edit_errors':errors,'sign_error_rate':errors/len(ref),
            'metric':'Unicode-sign-and-face-marker Levenshtein (not tokenizer TER)'}


def load(path):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))
