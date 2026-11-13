"""Localhost-only API and static files for CuneiLab v0.2. No dependencies."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from corpus import DEFAULT_DB, search, status, facets

ROOT = Path(__file__).resolve().parent
ALLOWED_ASSETS = {'/', '/index.html', '/app.js', '/engine.js', '/catalog.js', '/styles.css', '/corpus-ui.js'}


def make_handler(db_path: Path = DEFAULT_DB):
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
            self.wfile.write(body)

        def _valid_host(self) -> bool:
            # A loopback bind does not stop hostile websites from targeting a
            # local server via DNS rebinding. Require the exact local authority.
            hosts = self.headers.get_all('Host', [])
            valid = {f'127.0.0.1:{self.server.server_port}',
                     f'localhost:{self.server.server_port}'}
            return len(hosts) == 1 and hosts[0] in valid

        def do_HEAD(self):
            if not self._valid_host():
                self.send_error(403, 'Local host required')
                return
            # SimpleHTTPRequestHandler's inherited HEAD ignores our GET
            # allowlist; refuse requests for Python, SQLite and private files.
            if urlsplit(self.path).path not in ALLOWED_ASSETS:
                self.send_error(404, 'Ruta inexistente')
                return
            return super().do_HEAD()

        def do_GET(self):
            if not self._valid_host():
                self.send_error(403, 'Local host required')
                return
            parsed = urlsplit(self.path)
            if parsed.path == '/api/status':
                return self._json(200, status(db_path))
            if parsed.path == '/api/facets':
                return self._json(200, facets(db_path))
            if parsed.path == '/api/search':
                try:
                    args = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=8)
                    query = args.get('q', [''])[0]
                    field = args.get('field', ['transliteration'])[0]
                    period = args.get('period', [''])[0]
                    genre = args.get('genre', [''])[0]
                    result = search(query, field, db_path=db_path, period=period, genre=genre)
                    return self._json(200, result)
                except ValueError as e:
                    return self._json(400, {'error': str(e)})
            if parsed.path not in ALLOWED_ASSETS:
                return self._json(404, {'error': 'Ruta inexistente'})
            return super().do_GET()

        def end_headers(self):
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            super().end_headers()
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Servidor local CuneiLab')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    # Bind to loopback only: do not expose uploaded or researched material to the LAN.
    with ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(args.db)) as httpd:
        print(f'CuneiLab v0.3 en http://127.0.0.1:{httpd.server_port} (Ctrl+C para cerrar)', flush=True)
        httpd.serve_forever()

if __name__ == '__main__':
    main()
