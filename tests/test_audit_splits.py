"""Tests for cross-split leakage auditing; no external corpus required."""
import csv
import tempfile
import unittest
from pathlib import Path

from scripts.audit_splits import audit_splits


class SplitAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def csv(self, name, rows):
        path = self.root / (name + '.csv')
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['id', 'glyphs'])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_disjoint_sets_pass(self):
        a = self.csv('train', [{'id':'P000001','glyphs':'𒀭𒆠'}])
        b = self.csv('test', [{'id':'P000002','glyphs':'𒈗𒂍'}])
        report = audit_splits({'train':a, 'test':b})
        self.assertTrue(report['passed_exact_overlap_audit'])
        self.assertEqual(report['counts'], {'test':1,'train':1})

    def test_detects_same_id_in_two_splits(self):
        a = self.csv('train', [{'id':'P000001','glyphs':'𒀭'}])
        b = self.csv('test', [{'id':'P000001','glyphs':'𒈗'}])
        report = audit_splits({'train':a, 'test':b})
        self.assertFalse(report['passed_exact_overlap_audit'])
        self.assertEqual(report['duplicate_ids_across_splits'][0]['id'], 'P000001')

    def test_detects_same_signs_under_different_ids(self):
        a = self.csv('train', [{'id':'P000001','glyphs':'𒀭 𒆠'}])
        b = self.csv('test', [{'id':'P000002','glyphs':'𒀭𒆠'}])
        result = audit_splits({'train':a, 'test':b})
        self.assertEqual(len(result['exact_glyph_duplicates_across_splits']),1)

    def test_damage_markup_is_not_silently_discarded(self):
        a = self.csv('train', [{'id':'P000001','glyphs':'𒀭<D>𒆠'}])
        b = self.csv('test', [{'id':'P000002','glyphs':'𒀭𒆠'}])
        self.assertTrue(audit_splits({'train':a,'test':b})['passed_exact_overlap_audit'])

    def test_intrasplit_duplicates_reported(self):
        a = self.csv('train', [{'id':'P000001','glyphs':'𒀭'}, {'id':'P000001','glyphs':'𒆠'}])
        b = self.csv('test', [{'id':'P000002','glyphs':'𒈗'}])
        out = audit_splits({'train':a,'test':b})
        self.assertFalse(out['passed_exact_overlap_audit'])
        self.assertEqual(out['duplicate_ids_within_split']['train'], ['P000001'])

    def test_missing_columns_rejected(self):
        p=self.root/'bad.csv'
        p.write_text('id,transliteration\nP000001,an\n', encoding='utf-8')
        good=self.csv('test',[{'id':'P000002','glyphs':'𒀭'}])
        with self.assertRaisesRegex(ValueError,'faltan columnas'):
            audit_splits({'train':p,'test':good})


if __name__ == '__main__':
    unittest.main()
