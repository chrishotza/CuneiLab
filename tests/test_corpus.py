"""Corpus tests with synthetic fixtures; not a claim of historical attestation."""
import csv
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer

from corpus import import_csv, search, status, normalize, facets, cdli_url, make_context
from server import make_handler


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.csv = Path(self.folder.name) / 'example.csv'
        self.db = Path(self.folder.name) / 'example.sqlite3'
        with self.csv.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'period', 'genre', 'glyphs', 'transliteration', 'glyph_names'])
            writer.writeheader()
            writer.writerow({'id':'P000001','period':'Ur III','genre':'Administrative','glyphs':'𒈗𒂍','glyph_names':'LUGAL E2','transliteration':'lugal e2'})
            writer.writerow({'id':'P000002','period':'Ur III','genre':'Literary','glyphs':'𒀭 𒈗','glyph_names':'AN LUGAL','transliteration':'an lugal'})
            writer.writerow({'id':'P000003','period':'Old Babylonian','genre':'Literary','glyphs':'𒂍 𒈗 𒆠','glyph_names':'E2 LUGAL KI','transliteration':'e2 lugal ki'})
            writer.writerow({'id':'P000004','period':'Ur III','genre':'Administrative','glyphs':'𒋯','glyph_names':'DEMO','transliteration':'a_100%'})
        self.report = import_csv(self.csv, self.db)

    def test_schema_and_idempotence(self):
        self.assertEqual(self.report['rows_added'], 4)
        self.assertEqual(status(self.db)['count'], 4)
        self.assertEqual(import_csv(self.csv,self.db)['rows_added'], 0)

    def test_unicode_whitespace_normalized(self):
        self.assertEqual(normalize('𒀭 𒈗\n','glyphs'), '𒀭𒈗')
        r = search('𒀭𒈗', 'glyphs', db_path=self.db)
        self.assertEqual(len(r['results']),1)
        self.assertEqual(r['results'][0]['id'], 'P000002')
        self.assertEqual(r['results'][0]['match_type'], 'exacta')

    def test_ranking_and_metadata(self):
        r=search('lugal', db_path=self.db)
        self.assertEqual([v['id'] for v in r['results']], ['P000001','P000002','P000003'])
        self.assertEqual(r['results'][0]['match_type'], 'prefijo')
        self.assertEqual(len(search('lugal',db_path=self.db,period='Ur III')['results']),2)

    def test_sql_like_metacharacters_literal(self):
        self.assertEqual(search('_100%',db_path=self.db)['results'][0]['id'], 'P000004')
        self.assertEqual(search('anything%',db_path=self.db)['results'], [])

    def test_unavailable_db_and_bad_input(self):
        self.assertFalse(status(self.db.parent/'nothing.db')['ready'])
        self.assertFalse(search('lugal', db_path=self.db.parent/'nothing.db')['ready'])
        for query, field in [('x','glyphs'), ('lugal','id'), ('x'*1501,'glyphs')]:
            with self.assertRaises(ValueError):
                search(query,field,db_path=self.db)

    def test_csv_missing_fields(self):
        corrupt = self.csv.parent / 'broken.csv'
        corrupt.write_text('id,translation\nP000001,foo\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'faltan columnas'):
            import_csv(corrupt, self.csv.parent/'broken.sqlite3')

    def test_cdli_record_links_and_id_lookup(self):
        self.assertEqual(cdli_url('P119622'), 'https://cdli.earth/artifacts/119622')
        self.assertIsNone(cdli_url('Q119622'))
        self.assertIsNone(cdli_url('<script>'))
        found = search('p000001','id',db_path=self.db)
        self.assertEqual(found['results'][0]['id'],'P000001')
        self.assertEqual(found['results'][0]['cdli_url'], 'https://cdli.earth/artifacts/000001')
        with self.assertRaisesRegex(ValueError, 'Identificador'):
            search('P%001','id',db_path=self.db)

    def test_facets_and_filters(self):
        info = facets(self.db)
        self.assertTrue(info['ready'])
        self.assertEqual(info['periods'][0], {'name': 'Ur III', 'count': 3})
        results = search('lugal', db_path=self.db,genre='Literary')
        self.assertEqual([r['id'] for r in results['results']], ['P000002','P000003'])
        self.assertEqual(facets(self.db.parent/'missing.db')['genres'],[])
        with self.assertRaises(ValueError):
            search('lugal', db_path=self.db, genre='a'*101)

    def test_context_snippets_not_translations(self):
        rows=search('lugal',db_path=self.db)['results']
        self.assertEqual(rows[0]['context']['match'], 'lugal')
        self.assertIn('documentadas',search('lugal',db_path=self.db)['message'])
        cut=make_context('a'*100+'LUGAL'+'b'*100,'lugal',radius=10)
        self.assertEqual(cut['match'],'LUGAL')
        self.assertTrue(cut['truncated'])

    def test_http_api_and_static_allowlist(self):
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.db))
        thread = threading.Thread(target=httpd.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        con = http.client.HTTPConnection('127.0.0.1', httpd.server_port,timeout=3)
        try:
            con.request('GET','/api/status')
            res=con.getresponse()
            self.assertEqual(res.status,200)
            self.assertEqual(json.loads(res.read())['count'],4)
            con.request('GET','/api/search?field=glyphs&q=%F0%92%80%AD%F0%92%88%97')
            res=con.getresponse()
            self.assertEqual(res.status,200)
            self.assertEqual(json.loads(res.read())['results'][0]['id'],'P000002')
            con.request('GET','/api/search?field=evil&q=lugal')
            res=con.getresponse()
            self.assertEqual(res.status,400)
            self.assertIn('error',json.loads(res.read()))
            con.request('GET','/api/facets')
            res=con.getresponse()
            self.assertEqual(res.status,200)
            self.assertIn('periods',json.loads(res.read()))
            con.request('GET','/corpus.py')
            res=con.getresponse()
            self.assertEqual(res.status,404)
            res.read()
        finally:
            con.close()


if __name__=='__main__': unittest.main()
