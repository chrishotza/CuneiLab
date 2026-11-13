"""Opt-in, loopback-only image -> NabuOCR runner. No model loads on import.

All third-party model code runs in an isolated Python environment chosen by the
operator.  The browser never controls the model revision, executable or CLI args.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from transcription import validate

ROOT = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
REVISION = re.compile(r'[0-9a-fA-F]{40}\Z')
MIME_EXTENSIONS = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/webp': '.webp'}


@dataclass(frozen=True)
class OCRConfig:
    executable: Path
    revision: str
    device: str = 'auto'
    timeout: int = 600

    def __post_init__(self):
        executable = Path(self.executable).expanduser().resolve()
        if not executable.is_file():
            raise ValueError('El Python del entorno NabuOCR no existe: ' + str(executable))
        if not REVISION.fullmatch(self.revision):
            raise ValueError('La revisión NabuOCR debe ser un SHA de 40 dígitos hexadecimales')
        if self.device not in ('auto', 'cpu', 'cuda', 'cuda:0'):
            raise ValueError('Dispositivo OCR no reconocido')
        if not (30 <= self.timeout <= 1800):
            raise ValueError('Timeout OCR fuera del rango 30–1800 segundos')
        object.__setattr__(self, 'executable', executable)


def image_extension(raw: bytes, mime: str) -> str:
    if len(raw) == 0 or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError('Imagen vacía o demasiado grande (máximo 12 MB)')
    ext = MIME_EXTENSIONS.get(mime)
    if ext is None:
        raise ValueError('Se requiere JPG, PNG o WebP')
    found = ('.png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
             '.jpg' if raw.startswith(b'\xff\xd8\xff') else
             '.webp' if len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP' else None)
    if found != ext:
        raise ValueError('La firma de imagen no coincide con su formato declarado')
    return ext


def safe_filename(name: str, extension: str) -> str:
    if not isinstance(name, str) or not (1 <= len(name) <= 250) or any(c in name for c in ('/', '\\', '\x00', '\r', '\n')):
        raise ValueError('Nombre de imagen inválido')
    if Path(name).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
        raise ValueError('Nombre de fotografía sin extensión válida')
    if {'.jpeg':'.jpg'}.get(Path(name).suffix.lower(), Path(name).suffix.lower()) != extension:
        raise ValueError('El nombre no corresponde al formato de la fotografía')
    return name


def run_local_ocr(raw: bytes, mime: str, filename: str, config: OCRConfig, *, executor=subprocess.run) -> dict:
    """Invoked only on an explicitly enabled local POST. Raw bytes never persist."""
    ext = image_extension(raw, mime)
    filename = safe_filename(filename, ext)
    with tempfile.TemporaryDirectory(prefix='cuneilab-nabu-') as temporary:
        directory = Path(temporary)
        photo = directory / ('source' + ext)
        result = directory / 'result.json'
        photo.write_bytes(raw)
        command = [str(config.executable), str(ROOT/'scripts'/'run_nabu_ocr.py'),
                   '--image', str(photo), '--output', str(result),
                   '--device', config.device, '--revision', config.revision,
                   '--trust-remote-code']
        try:
            completed = executor(command, capture_output=True, text=True,
                                 timeout=config.timeout, cwd=str(ROOT), check=False)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('La ejecución NabuOCR agotó el tiempo configurado') from error
        if completed.returncode != 0:
            # Full details stay on the operator's terminal, not in HTTP responses.
            print('NabuOCR falló:', (completed.stderr or completed.stdout or '')[-3000:], flush=True)
            raise RuntimeError('NabuOCR falló. Revisá la terminal local y las dependencias del modelo')
        if not result.is_file() or result.stat().st_size > MAX_RESPONSE_BYTES:
            raise RuntimeError('El modelo no produjo un resultado JSON válido (máximo 1 MB)')
        try:
            document = validate(json.loads(result.read_text(encoding='utf-8')))
        except (ValueError, json.JSONDecodeError) as error:
            raise RuntimeError('Resultado OCR inválido o sin signos cuneiformes') from error
        # Verify fixed model provenance and correct response image name. The model
        # only sees the temporary image; the response refers to the actual photo.
        if document['model'] != 'boatbomber/NabuOCR@' + config.revision:
            raise RuntimeError('La procedencia del OCR no coincide con el modelo configurado')
        document['image_filename'] = filename
        document['image_sha256'] = hashlib.sha256(raw).hexdigest()
        return document
