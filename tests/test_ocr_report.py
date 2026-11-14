"""Synthetic smoke tests: safe static offline HTML report; no model weights."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.ocr_error_analysis import analyze
from scripts.render_ocr_report import render_report, main


class OCRReportTests(unittest.TestCase):
    def setUp(self):
        self.report = analyze(
            {'P000001':'𒀭𒆠', 'P000002':'𒈗𒂍'},
            {'P000001':'𒀭𒈗'}, top=10)

    def test_self_contained_html_contains_metrics_and_tablets(self):
        html = render_report(self.report)
        self.assertIn('<!doctype html>', html)
        self.assertIn('CuneiLab · Diagnóstico OCR', html)
        self.assertIn('P000001', html)
        self.assertIn('P000002', html)
        self.assertIn('Sin lectura', html)
        self.assertIn('50.00%', html)
        self.assertIn('75.00%', html)
        self.assertIn('𒆠', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('https://', html)

    def test_rejects_missing_or_wrong_schema(self):
        for value in ({}, {'format':'other','version':1},
                      {'format':'cuneilab-ocr-error-analysis','version':1}):
            with self.assertRaises(ValueError):
                render_report(value)

    def test_escapes_untrusted_document_ids_and_messages(self):
        self.report['worst_tablets'][0]['id'] = '<img src=x onerror=alert(1)>'
        self.report['limitations'] = '<script>alert("x")</script>'
        html = render_report(self.report)
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('<script>alert', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&lt;img', html)

    def test_empty_prediction_and_no_confusions(self):
        report = analyze({'P000001':'𒀭𒆠'}, {})
        html = render_report(report)
        self.assertIn('Sin datos', html)
        self.assertIn('100.00%', html)
        self.assertIn('Sin registros', html)

    def test_cropped_face_label(self):
        report = analyze({'P000001':'@obverse 𒀭'}, {'P000001':'@reverse 𒀭'},
                         cropped_faces=True)
        self.assertIn('Recortes de una cara', render_report(report))

    def test_cli_writes_standalone_html(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root/'analysis.json', root/'diagnostico.html'
            source.write_text(json.dumps(self.report, ensure_ascii=False), encoding='utf-8')
            main(['--input', str(source), '--output', str(target)])
            self.assertTrue(target.is_file())
            self.assertIn('P000001', target.read_text(encoding='utf-8'))

    def test_cli_does_not_write_invalid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source,target=root/'bad.json',root/'report.html'
            source.write_text('{}',encoding='utf-8')
            with self.assertRaises(SystemExit):
                main(['--input',str(source),'--output',str(target)])
            self.assertFalse(target.exists())

    def test_invalid_numeric_metrics_rejected(self):
        self.report['evaluation']['coverage_images'] = float('nan')
        with self.assertRaises(ValueError):
            render_report(self.report)


if __name__ == '__main__':
    unittest.main()
