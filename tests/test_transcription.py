import json
import unittest
from transcription import make_document,validate,score,glyph_tokens,TranscriptionError
from scripts.evaluate_nabu import evaluate
from scripts.run_nabu_ocr import prepare_messages, infer

class TranscriptionTests(unittest.TestCase):
    def test_valid(self):
        d=make_document('@obverse\n𒀭𒆠',800,900,'test.jpg')
        self.assertEqual(d['sign_count'],2)
        self.assertEqual(d['confidence'],'not_calibrated')
        self.assertEqual(validate(d),d)
    def test_missing_sign_rejected(self):
        with self.assertRaises(TranscriptionError): make_document('fictional translation',800,900)
    def test_dimensions_rejected(self):
        with self.assertRaises(TranscriptionError): make_document('𒀭',True,1)
    def test_traversal_rejected(self):
        with self.assertRaises(TranscriptionError): make_document('𒀭',8,8,'../passwd')
    def test_score_exact(self):
        self.assertEqual(score('𒀭𒆠','𒀭𒆠')['sign_error_rate'],0)
    def test_score_substitution(self):
        self.assertAlmostEqual(score('𒀭𒆠','𒀭𒈗')['sign_error_rate'],0.5)
    def test_score_insertion(self):
        self.assertAlmostEqual(score('𒀭','𒀭𒆠')['sign_error_rate'],1)
    def test_markers(self):
        self.assertEqual(glyph_tokens('@obverse 𒀭\n@reverse 𒈗'),['@obverse','𒀭','@reverse','𒈗'])
    def test_gold_empty(self):
        with self.assertRaises(TranscriptionError): score('bad', '𒀭')
    def test_evaluate_micro(self):
        report=evaluate({'a':'𒀭𒆠','b':'𒀭'},{'a':'𒀭𒈗','b':'𒀭','c':'𒀭'})
        self.assertEqual(report['images_scored'],2)
        self.assertAlmostEqual(report['micro_sign_error_rate'],1/3)
        self.assertEqual(report['unmatched_predictions'],['c'])
    def test_missing_predictions_count_as_deleted_signs(self):
        report=evaluate({'a':'𒀭𒆠','b':'𒀭𒈗'}, {'a':'𒀭𒆠'})
        self.assertEqual(report['micro_sign_error_rate'],0)
        self.assertEqual(report['coverage_images'],0.5)
        self.assertEqual(report['missing_reference_signs'],2)
        self.assertAlmostEqual(report['micro_sign_error_rate_including_missing'],0.5)

    def test_all_predictions_missing_is_not_perfect(self):
        report=evaluate({'a':'𒀭𒆠'}, {})
        self.assertIsNone(report['micro_sign_error_rate'])
        self.assertEqual(report['coverage_images'],0)
        self.assertEqual(report['micro_sign_error_rate_including_missing'],1)

    def test_requires_explicit_remote_code(self):
        with self.assertRaises(ValueError): infer('any.jpg')
    def test_author_prompt(self):
        self.assertEqual(prepare_messages('image')[0]['content'][1]['text'],'OCR:')

if __name__ == '__main__':unittest.main()
