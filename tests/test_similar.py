"""Corpus concordance: synthetic documents only, never a model accuracy claim."""
from __future__ import annotations
import csv
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

from corpus import import_csv, similar_signs
from server import make_handler
from local_ocr import OCRConfig
from transcription import make_document
import sys


class SimilarSignsTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.db = Path(work.name) / 'tablets.sqlite3'
        csvpath = Path(work.name) / 'tablets.csv'
        with csvpath.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['id', 'period', 'genre', 'glyphs', 'transliteration'])
            writer.writeheader()
            writer.writerows([
                {'id': 'P000001', 'period': 'Ur III', 'genre': 'Administrative',
                 'glyphs': '𒀭 𒈗 𒆠 𒂍 𒌋', 'transliteration': 'an lugal ki e2 u'},
                {'id': 'P000002', 'period': 'Old Babylonian', 'genre': 'Literary',
                 'glyphs': '𒈗 𒆠 𒂍 𒀭 𒄑', 'transliteration': 'lugal ki e2 an giš'},
                {'id': 'P000003', 'period': 'Ur III', 'genre': 'Literary',
                 'glyphs': '𒀭 𒈗 𒆠', 'transliteration': 'an lugal ki'},
            ])
        import_csv(csvpath, self.db)

    def test_exact_sign_window_retrieves_attested_transliteration(self):
        report = similar_signs('𒀭𒈗𒆠𒂍', db_path=self.db)
        self.assertTrue(report['ready'])
        self.assertEqual([row['id'] for row in report['results']], ['P000001'])
        hit = report['results'][0]
        self.assertEqual(hit['ngram_width'], 4)
        self.assertEqual(hit['shared_ngrams'], 1)
        self.assertEqual(hit['query_ngrams'], 1)
        self.assertEqual(hit['transliteration'], 'an lugal ki e2 u')
        self.assertEqual(hit['cdli_url'], 'https://cdli.earth/artifacts/000001')
        self.assertNotIn('confidence', hit)

    def test_3_sign_fallback_and_rank(self):
        rows = similar_signs('𒀭 𒈗 𒆠', db_path=self.db)['results']
        self.assertEqual({r['id'] for r in rows}, {'P000001', 'P000003'})
        self.assertTrue(all(r['ngram_width'] == 3 for r in rows))
        self.assertEqual(rows[0]['id'], 'P000003')

    def test_does_not_invent_cross_face_ngrams(self):
        result = similar_signs('@obverse\n𒀭𒈗@reverse\n𒆠𒂍', db_path=self.db)
        self.assertEqual(result['results'], [])
        self.assertEqual(result['query_signs'], 4)

    def test_filters_and_unknown_glyphs(self):
        result = similar_signs('𒀭𒈗𒆠𒂍𒌋', db_path=self.db, genre='Literary')
        self.assertTrue(all(row['genre'] == 'Literary' for row in result['results']))
        self.assertTrue(all(row['ngram_width'] == 3 for row in result['results']))
        result = similar_signs('𒀭𒈗𒆠𒂍𒌋', db_path=self.db, period='Ur III')
        self.assertEqual([r['id'] for r in result['results']], ['P000001'])
        self.assertEqual(similar_signs('𒌋𒄑𒀭', db_path=self.db)['results'], [])

    def test_input_and_empty_database(self):
        for value in ('hello', '𒀭𒈗', '𒀭'*701, '𒀭'*4001):
            with self.assertRaises(ValueError):
                similar_signs(value, db_path=self.db)
        with self.assertRaises(ValueError):
            similar_signs('𒀭𒈗𒆠', db_path=self.db, limit=20)
        self.assertFalse(similar_signs('𒀭𒈗𒆠', db_path=self.db.parent/'missing')['ready'])

    def test_http_endpoint(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        self.addCleanup(connection.close)
        query = urlencode({'glyphs':'𒀭𒈗𒆠𒂍'})
        connection.request('GET', '/api/similar?' + query)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        body = json.loads(response.read())
        self.assertEqual(body['results'][0]['id'], 'P000001')
        connection.request('GET','/api/similar?glyphs=invalid')
        response = connection.getresponse()
        self.assertEqual(response.status,400)
        self.assertIn('error',json.loads(response.read()))
        connection.request('GET','/api/similar?' + query, headers={'Host':'example.test'})
        response=connection.getresponse()
        self.assertEqual(response.status,403)
        response.read()

    def test_end_to_end_mock_ocr_then_corpus_lookup(self):
        # Genuine HTTP transport and SQLite retrieval; OCR itself is mocked.
        rev = 'a' * 40
        def fake_ocr(raw, mime, name, config):
            return make_document('𒀭𒈗𒆠𒂍', 80, 60, name,
                                 model='boatbomber/NabuOCR@' + rev)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(
            self.db, ocr_config=OCRConfig(Path(sys.executable), rev), ocr_runner=fake_ocr))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=4)
        self.addCleanup(client.close)
        png_fixture = bytes.fromhex('89504e470d0a1a0a') + b'fixture-for-mocked-ocr'
        headers = {'Content-Type':'image/png','X-CuneiLab-Request':'ocr-v1',
                   'X-CuneiLab-Filename':'sample.png'}
        client.request('POST', '/api/ocr', body=png_fixture, headers=headers)
        reply = client.getresponse()
        self.assertEqual(reply.status, 200)
        transcript = json.loads(reply.read())
        self.assertEqual(transcript['text'], '𒀭𒈗𒆠𒂍')
        client.request('GET', '/api/similar?' + urlencode({'glyphs': transcript['text']}))
        search_result = client.getresponse()
        self.assertEqual(search_result.status, 200)
        candidates = json.loads(search_result.read())['results']
        self.assertEqual(candidates[0]['id'], 'P000001')
        self.assertEqual(candidates[0]['transliteration'], 'an lugal ki e2 u')

if __name__ == '__main__':
    unittest.main()
