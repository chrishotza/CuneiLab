"""CuneiLab HTTP application: loopback-only, corpus search and opt-in local OCR."""
from __future__ import annotations

import argparse
import json
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote

from corpus import DEFAULT_DB, search, status, facets, similar_signs
from local_ocr import OCRConfig, MAX_IMAGE_BYTES, image_extension, safe_filename, run_local_ocr

ROOT = Path(__file__).resolve().parent
ALLOWED_ASSETS = {'/', '/index.html', '/app.js', '/engine.js', '/catalog.js', '/styles.css',
                  '/corpus-ui.js', '/vision.js', '/transcription.js', '/transcription-ui.js'}


def make_handler(db_path: Path = DEFAULT_DB, *, ocr_config: OCRConfig | None = None, ocr_runner=None):
    # One GPU-heavy inference at a time, across all threads.
    busy = threading.BoundedSemaphore(1)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def _json(self, code: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _trusted_host(self):
            # Prevent hostile remote sites from using DNS rebinding to access the
            # local OCR process, even when the server only binds to loopback.
            host = self.headers.get('Host', '')
            port = self.server.server_port
            if host not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                return False
            origin = self.headers.get('Origin')
            if origin is not None and origin not in (f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
                return False
            return self.headers.get('Sec-Fetch-Site', 'same-origin') in ('same-origin','none')

        def do_GET(self):
            parsed = urlsplit(self.path)
            if not self._trusted_host():
                return self._json(403, {'error':'Solo se acepta acceso local a CuneiLab'})
            if parsed.path == '/api/ocr-status':
                return self._json(200, {'enabled': ocr_config is not None,
                                        'model': 'boatbomber/NabuOCR' if ocr_config else None,
                                        'note': 'El modelo solo se ejecuta mediante una solicitud explícita.'})
            if parsed.path == '/api/status':
                return self._json(200, status(db_path))
            if parsed.path == '/api/facets':
                return self._json(200, facets(db_path))
            if parsed.path == '/api/similar':
                try:
                    args = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=5)
                    result = similar_signs(args.get('glyphs', [''])[0], db_path=db_path,
                                           period=args.get('period', [''])[0],
                                           genre=args.get('genre', [''])[0])
                    return self._json(200, result)
                except ValueError as e:
                    return self._json(400, {'error': str(e)})
            if parsed.path == '/api/search':
                try:
                    args = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
                    result = search(args.get('q', [''])[0], args.get('field', ['transliteration'])[0],
                                    db_path=db_path, period=args.get('period', [''])[0],
                                    genre=args.get('genre', [''])[0])
                    return self._json(200, result)
                except ValueError as e:
                    return self._json(400, {'error': str(e)})
            if parsed.path not in ALLOWED_ASSETS:
                return self._json(404, {'error': 'Ruta inexistente'})
            return super().do_GET()

        def do_HEAD(self):
            # SimpleHTTPRequestHandler would otherwise expose non-whitelisted
            # local files through HEAD, bypassing do_GET's asset restrictions.
            if not self._trusted_host():
                return self._json(403, {'error':'Solo se acepta acceso local a CuneiLab'})
            if urlsplit(self.path).path not in ALLOWED_ASSETS:
                return self._json(404, {'error':'Ruta inexistente'})
            return super().do_HEAD()

        def do_POST(self):
            if urlsplit(self.path).path != '/api/ocr':
                return self._json(404, {'error':'Ruta inexistente'})
            if not self._trusted_host() or self.headers.get('X-CuneiLab-Request') != 'ocr-v1':
                return self._json(403, {'error':'Solicitud local no autorizada'})
            if ocr_config is None:
                return self._json(503, {'error':'OCR deshabilitado. Seguí las instrucciones de instalación del README.'})
            if self.headers.get('Transfer-Encoding'):
                return self._json(400, {'error':'No se aceptan transferencias fragmentadas'})
            size = self.headers.get('Content-Length')
            if size is None:
                return self._json(411, {'error':'Falta Content-Length'})
            try: length = int(size)
            except ValueError: return self._json(400, {'error':'Content-Length inválido'})
            if not 0 < length <= MAX_IMAGE_BYTES:
                return self._json(413, {'error':'Fotografía demasiado grande (máximo 12 MB)'})
            mime = self.headers.get('Content-Type', '').split(';',1)[0].lower().strip()
            filename = unquote(self.headers.get('X-CuneiLab-Filename', 'tablilla.jpg'))
            if not busy.acquire(blocking=False):
                return self._json(429, {'error':'NabuOCR está procesando otra fotografía. Intentá nuevamente.'})
            try:
                raw = self.rfile.read(length)
                if len(raw) != length:
                    return self._json(400, {'error':'Fotografía incompleta'})
                try:
                    extension = image_extension(raw, mime)
                    filename = safe_filename(filename, extension)
                    result = (ocr_runner or run_local_ocr)(raw, mime, filename, ocr_config)
                except ValueError as error:
                    return self._json(400, {'error':str(error)})
                except Exception as error:
                    print('Error OCR:', type(error).__name__, str(error), flush=True)
                    return self._json(502, {'error':'No se completó el OCR. Revisá la terminal local del servidor.'})
                return self._json(200, result)
            finally:
                busy.release()

        def end_headers(self):
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            super().end_headers()

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description='Servidor local CuneiLab')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    parser.add_argument('--enable-local-ocr', action='store_true',
                        help='Activa el endpoint OCR solo en localhost (terceros, descarga de pesos)')
    parser.add_argument('--ocr-python', type=Path, help='Python del entorno virtual de NabuOCR')
    parser.add_argument('--ocr-revision', help='SHA de 40 caracteres del modelo NabuOCR revisado')
    parser.add_argument('--ocr-device', choices=['auto','cpu','cuda','cuda:0'], default='auto')
    parser.add_argument('--ocr-timeout', type=int, default=600)
    parser.add_argument('--accept-third-party-model-code', action='store_true',
                        help='Confirmo que revisé y autorizo ejecutar código de terceros')
    args = parser.parse_args(argv)
    config = None
    if args.enable_local_ocr:
        if not args.accept_third_party_model_code or args.ocr_python is None or args.ocr_revision is None:
            parser.error('OCR requiere --accept-third-party-model-code, --ocr-python y --ocr-revision')
        try:
            config=OCRConfig(args.ocr_python, args.ocr_revision, args.ocr_device, args.ocr_timeout)
        except ValueError as error:
            parser.error(str(error))
    elif any((args.ocr_python, args.ocr_revision, args.accept_third_party_model_code)):
        parser.error('Los ajustes del OCR requieren --enable-local-ocr')
    with ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(args.db, ocr_config=config)) as httpd:
        print(f'CuneiLab en http://127.0.0.1:{httpd.server_port}; OCR local: {"ACTIVADO" if config else "deshabilitado"}', flush=True)
        httpd.serve_forever()

if __name__ == '__main__':
    main()
