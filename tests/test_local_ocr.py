"""Integration tests for opt-in localhost OCR; no model weights or download."""
from __future__ import annotations

import json
import http.client
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_ocr import OCRConfig, image_extension, run_local_ocr, safe_filename
from server import make_handler
from transcription import make_document

PNG = bytes.fromhex('89504e470d0a1a0a') + b'fixture-pixels'
REV = 'a' * 40


class LocalOCRValidationTests(unittest.TestCase):
    def test_image_signatures_and_size(self):
        self.assertEqual(image_extension(PNG,'image/png'), '.png')
        for data,mime in [(PNG,'image/jpeg'),(b'no','image/png'),(b'', 'image/png'),(PNG,'text/plain')]:
            with self.assertRaises(ValueError): image_extension(data,mime)
        with self.assertRaises(ValueError): image_extension(PNG * 1_000_000,'image/png')

    def test_filename_restrictions(self):
        self.assertEqual(safe_filename('tablilla.jpeg','.jpg'),'tablilla.jpeg')
        for name in ('../a.png','x\\a.png','bad\rname.png','x.html','file.jpg'):
            with self.assertRaises(ValueError): safe_filename(name,'.png')

    def test_config_requires_full_sha_and_existing_executable(self):
        self.assertEqual(OCRConfig(Path(sys.executable),REV).revision,REV)
        for rev in ('main','c'*39,'x'*40):
            with self.assertRaises(ValueError): OCRConfig(Path(sys.executable),rev)
        with self.assertRaises(ValueError): OCRConfig(Path('/missing/python'),REV)

    def test_process_command_fixed_and_document_provenance(self):
        cfg=OCRConfig(Path(sys.executable),REV)
        observed=[]
        def fake_executor(args, **kwargs):
            observed.append((args,kwargs))
            out=Path(args[args.index('--output')+1])
            out.write_text(json.dumps(make_document('𒀭𒆠', 16, 24, 'source.png',
                                       model='boatbomber/NabuOCR@'+REV)), encoding='utf-8')
            return subprocess.CompletedProcess(args,0,'','')
        doc=run_local_ocr(PNG,'image/png','foto.png',cfg,executor=fake_executor)
        self.assertEqual(doc['image_filename'],'foto.png')
        self.assertEqual(doc['sign_count'],2)
        self.assertEqual(len(doc['image_sha256']),64)
        args,opts=observed[0]
        self.assertIn('--trust-remote-code',args)
        self.assertEqual(args[args.index('--revision')+1], REV)
        self.assertFalse(opts['check'] if 'check' in opts else False)
        self.assertEqual(opts['cwd'],str(Path(__file__).resolve().parents[1]))

    def test_reject_mismatched_provenance(self):
        cfg=OCRConfig(Path(sys.executable),REV)
        def fake(args,**kwargs):
            Path(args[args.index('--output')+1]).write_text(json.dumps(
                make_document('𒀭',10,20,'source.png',model='boatbomber/NabuOCR@'+'b'*40)))
            return subprocess.CompletedProcess(args,0,'','')
        with self.assertRaisesRegex(RuntimeError,'procedencia'):
            run_local_ocr(PNG,'image/png','foto.png',cfg,executor=fake)


class LocalOCRHttpTests(unittest.TestCase):
    def setUp(self):
        self.events=[]
        self.config=OCRConfig(Path(sys.executable),REV)
        def runner(raw,mime,name,config):
            self.events.append((raw,mime,name))
            return make_document('𒀭𒆠',16,24,name,model='boatbomber/NabuOCR@'+REV)
        self.httpd=ThreadingHTTPServer(('127.0.0.1',0),make_handler(ocr_config=self.config,ocr_runner=runner))
        self.port=self.httpd.server_port
        self.thread=threading.Thread(target=self.httpd.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)

    def request(self,path='/api/ocr',*,headers=None,body=PNG,method='POST'):
        req=Request(f'http://127.0.0.1:{self.port}{path}',data=body if method=='POST' else None,
                    method=method,headers=headers or {})
        try:
            with urlopen(req,timeout=3) as response:
                return response.status,json.loads(response.read().decode('utf-8'))
        except HTTPError as error:
            return error.code,json.loads(error.read().decode('utf-8'))

    def good_headers(self):
        return {'Content-Type':'image/png','X-CuneiLab-Request':'ocr-v1',
                'X-CuneiLab-Filename':'tablilla.png','Origin':f'http://127.0.0.1:{self.port}'}

    def test_ocr_from_binary_to_json(self):
        status,doc=self.request(headers=self.good_headers())
        self.assertEqual(status,200)
        self.assertEqual(doc['text'],'𒀭𒆠')
        self.assertEqual(self.events,[(PNG,'image/png','tablilla.png')])

    def test_local_status_available(self):
        code,obj=self.request('/api/ocr-status',method='GET')
        self.assertEqual(code,200)
        self.assertTrue(obj['enabled'])
        self.assertNotIn('revision',obj)

    def test_csrf_and_external_origins_rejected(self):
        for headers in ({'Content-Type':'image/png'},
                        {**self.good_headers(),'Origin':'https://evil.test'},
                        {**self.good_headers(),'Sec-Fetch-Site':'cross-site'},
                        {**self.good_headers(),'Host':'evil.test'}):
            code,_=self.request(headers=headers)
            self.assertEqual(code,403)
        self.assertEqual(self.events,[])

    def test_head_cannot_expose_private_source(self):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        connection.request('HEAD','/server.py')
        response=connection.getresponse()
        self.assertEqual(response.status,404)
        response.close();connection.close()

    def test_size_and_route_validation(self):
        code,_=self.request(headers={**self.good_headers(),'Content-Type':'text/plain'})
        self.assertEqual(code,400)
        code,_=self.request('/api/secret',headers=self.good_headers())
        self.assertEqual(code,404)
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        connection.putrequest('POST','/api/ocr')
        for key,value in self.good_headers().items():connection.putheader(key,value)
        connection.putheader('Content-Length',str(15*1024*1024))
        connection.endheaders()
        response=connection.getresponse()
        self.assertEqual(response.status,413)
        response.read();connection.close()

    def test_disabled_by_default(self):
        self.shutdown()
        self.addCleanup(lambda:None)
        self.httpd=ThreadingHTTPServer(('127.0.0.1',0),make_handler())
        self.port=self.httpd.server_port
        self.thread=threading.Thread(target=self.httpd.serve_forever,daemon=True)
        self.thread.start()
        code,body=self.request(headers=self.good_headers())
        self.assertEqual(code,503)
        code,status=self.request('/api/ocr-status',method='GET')
        self.assertEqual(code,200)
        self.assertFalse(status['enabled'])


if __name__=='__main__':unittest.main()
