"""Deterministic synthetic fixtures for Unicode OCR error analysis."""
import unittest
from scripts.ocr_error_analysis import align, analyze, MAX_ALIGN_TOKENS


class OCRAnalysisTests(unittest.TestCase):
    def test_correct_alignment(self):
        self.assertEqual(align(list('𒀭𒆠'), list('𒀭𒆠')),
                         [('correct','𒀭','𒀭'),('correct','𒆠','𒆠')])

    def test_substitution(self):
        result = analyze({'P000001':'𒀭𒆠'}, {'P000001':'𒀭𒈗'})
        self.assertEqual(result['totals']['substitution'], 1)
        self.assertEqual(result['most_common_substitutions'][0],
                         {'reference':'𒆠','prediction':'𒈗','count':1})
        self.assertAlmostEqual(result['evaluation']['micro_sign_error_rate'], 0.5)

    def test_missing_prediction_is_deletion(self):
        result = analyze({'P000001':'𒀭𒆠'}, {})
        self.assertEqual(result['totals']['deletion'], 2)
        self.assertEqual(result['worst_tablets'][0]['status'], 'missing_prediction')
        self.assertEqual(result['evaluation']['micro_sign_error_rate_including_missing'], 1.0)

    def test_insertions(self):
        result=analyze({'P000001':'𒀭'}, {'P000001':'𒀭𒈗𒆠'})
        self.assertEqual(result['totals']['insertion'], 2)
        self.assertEqual(result['evaluation']['micro_sign_error_rate'], 2.0)

    def test_cropped_faces_strip_markers(self):
        result=analyze({'a':'@obverse\n𒀭𒆠'},
                       {'a':'@reverse\n𒀭𒆠'},cropped_faces=True)
        self.assertEqual(result['totals']['correct'], 2)
        self.assertEqual(result['totals']['substitution'], 0)

    def test_full_tablet_markers_are_not_ignored(self):
        result=analyze({'a':'@obverse\n𒀭'},
                       {'a':'@reverse\n𒀭'})
        self.assertEqual(result['totals']['substitution'], 1)

    def test_glyph_diagnostics_sorted_deterministically(self):
        result=analyze({'a':'𒀭𒆠','b':'𒀭𒆠'},
                       {'a':'𒀭𒈗','b':'𒀭𒈗'})
        self.assertEqual(result['most_substituted_reference_signs'][0]['count'],2)

    def test_unmatched_predictions_reported_not_scored(self):
        result=analyze({'a':'𒀭'}, {'a':'𒀭', 'unexpected':'𒈗'})
        self.assertEqual(result['evaluation']['unmatched_predictions'],['unexpected'])
        self.assertEqual(len(result['worst_tablets']),1)

    def test_alignment_length_limit(self):
        with self.assertRaisesRegex(ValueError,'máximo'):
            align(['𒀭']*(MAX_ALIGN_TOKENS+1), [])

    def test_invalid_top_rejected(self):
        with self.assertRaises(ValueError):
            analyze({'a':'𒀭'}, {}, top=0)

    def test_reference_without_signs_rejected(self):
        with self.assertRaises(ValueError):
            analyze({'a':'nonsense'}, {})

    def test_complex_edits_match_canonical_levenshtein(self):
        gold={'a':'𒀭𒆠𒈗𒂍','b':'𒆠𒆠𒀭'}
        pred={'a':'𒀭𒈗𒂍𒆠','b':'𒆠𒀭'}
        result=analyze(gold,pred)
        self.assertEqual(result['evaluation']['images_scored'],2)
        self.assertEqual(result['totals']['correct'] +
                         result['totals']['substitution'] +
                         result['totals']['deletion'],7)


if __name__=='__main__':
    unittest.main()
