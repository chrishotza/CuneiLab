"""Cross-split audit tests use small synthetic CSVs and image manifests."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from scripts.audit_splits import audit_splits, _norm_glyphs, _photo_hashes


class SplitAuditTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)

    def csv(self, name, rows):
        path=self.root/(name+'.csv')
        with path.open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=['id','glyphs'])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def audit(self,name,rows):
        path=self.root/(name+'.jsonl')
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
        return path

    def test_disjoint_sets_pass(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭𒆠'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒈗𒂍'}])
        result=audit_splits({'train':a,'test':b})
        self.assertTrue(result['passed_exact_overlap_audit'])
        self.assertFalse(result['needs_manual_review'])

    def test_same_id_detected(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭'}])
        b=self.csv('test',[{'id':'P000001','glyphs':'𒈗'}])
        self.assertEqual(audit_splits({'train':a,'test':b})['duplicate_ids_across_splits'][0]['id'],'P000001')

    def test_same_signs_without_horizontal_spaces(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭 𒆠'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒀭𒆠'}])
        result=audit_splits({'train':a,'test':b})
        self.assertFalse(result['passed_exact_overlap_audit'])
        self.assertEqual(len(result['exact_glyph_duplicates_across_splits']),1)

    def test_line_boundary_is_review_not_exact(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭\n𒆠'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒀭𒆠'}])
        result=audit_splits({'train':a,'test':b})
        self.assertTrue(result['passed_exact_overlap_audit'])
        self.assertTrue(result['needs_manual_review'])
        self.assertEqual(len(result['potential_line_boundary_duplicates']),1)

    def test_crlf_normalized(self):
        self.assertEqual(_norm_glyphs('𒀭\r\n𒆠'),_norm_glyphs('𒀭\n𒆠'))

    def test_damage_markers_preserved(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭<D>𒆠'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒀭𒆠'}])
        self.assertTrue(audit_splits({'train':a,'test':b})['passed_exact_overlap_audit'])

    def test_intrasplit_duplicates(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭'},{'id':'P000001','glyphs':'𒆠'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒈗'}])
        self.assertEqual(audit_splits({'train':a,'test':b})['duplicate_ids_within_split']['train'],['P000001'])

    def test_same_photo_hash_different_ids(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒈗'}])
        da=self.audit('a',[{'id':'P000001','image_sha256':'a'*64}])
        db=self.audit('b',[{'id':'P000002','image_sha256':'a'*64}])
        result=audit_splits({'train':a,'test':b},image_audits={'train':da,'test':db})
        self.assertFalse(result['passed_exact_overlap_audit'])
        self.assertEqual(len(result['duplicate_photo_hashes_across_splits']),1)

    def test_changed_image_hash_no_collision(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒈗'}])
        da=self.audit('a',[{'id':'P000001','crop_sha256':'a'*64}])
        db=self.audit('b',[{'id':'P000002','crop_sha256':'b'*64}])
        self.assertTrue(audit_splits({'train':a,'test':b},image_audits={'train':da,'test':db})['passed_exact_overlap_audit'])

    def test_same_original_photo_with_different_crops_is_collision(self):
        train=self.csv('train',[{'id':'P000001','glyphs':'𒀭𒆠'}])
        test=self.csv('test',[{'id':'P000002','glyphs':'𒈗𒂍'}])
        left=self.audit('left',[{'id':'P000001','source_sha256':'a'*64,'crop_sha256':'b'*64}])
        right=self.audit('right',[{'id':'P000002','source_sha256':'a'*64,'crop_sha256':'c'*64}])
        result=audit_splits({'train':train,'test':test},image_audits={'train':left,'test':right})
        self.assertFalse(result['passed_exact_overlap_audit'])
        self.assertEqual([item['image_kind'] for item in result['duplicate_photo_hashes_across_splits']],['original'])

    def test_crop_hashes_checked_even_if_original_hash_exists(self):
        train=self.csv('train',[{'id':'P000001','glyphs':'𒀭𒆠'}])
        test=self.csv('test',[{'id':'P000002','glyphs':'𒈗𒂍'}])
        left=self.audit('left',[{'id':'P000001','source_sha256':'a'*64,'crop_sha256':'c'*64}])
        right=self.audit('right',[{'id':'P000002','source_sha256':'b'*64,'crop_sha256':'c'*64}])
        result=audit_splits({'train':train,'test':test},image_audits={'train':left,'test':right})
        self.assertEqual([item['image_kind'] for item in result['duplicate_photo_hashes_across_splits']],['crop'])

    def test_original_and_crop_not_compared_across_kinds(self):
        train=self.csv('train',[{'id':'P000001','glyphs':'𒀭𒆠'}])
        test=self.csv('test',[{'id':'P000002','glyphs':'𒈗𒂍'}])
        left=self.audit('left',[{'id':'P000001','source_sha256':'a'*64}])
        right=self.audit('right',[{'id':'P000002','crop_sha256':'a'*64}])
        result=audit_splits({'train':train,'test':test},image_audits={'train':left,'test':right})
        self.assertTrue(result['passed_exact_overlap_audit'])

    def test_conflicting_original_hashes_for_same_id_rejected(self):
        path=self.audit('bad',[{'id':'P000001','source_sha256':'a'*64},
                               {'id':'P000001','source_sha256':'b'*64}])
        with self.assertRaisesRegex(ValueError,'contradictorios'):
            _photo_hashes(path,'train')

    def test_bad_image_hash_rejected(self):
        file=self.audit('bad',[{'id':'P000001','image_sha256':'bad'}])
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            _photo_hashes(file,'train')

    def test_unknown_photo_id_rejected(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭'}])
        b=self.csv('test',[{'id':'P000002','glyphs':'𒈗'}])
        da=self.audit('a',[{'id':'P999999','image_sha256':'a'*64}])
        with self.assertRaisesRegex(ValueError,'no figura'):
            audit_splits({'train':a,'test':b},image_audits={'train':da})

    def test_same_csv_path_rejected(self):
        a=self.csv('train',[{'id':'P000001','glyphs':'𒀭'}])
        with self.assertRaisesRegex(ValueError,'mismo CSV'):
            audit_splits({'train':a,'test':a})

    def test_missing_columns_rejected(self):
        path=self.root/'bad.csv'
        path.write_text('id,transliteration\nP000001,an\n',encoding='utf-8')
        b=self.csv('test',[{'id':'P000002','glyphs':'𒈗'}])
        with self.assertRaisesRegex(ValueError,'faltan columnas'):
            audit_splits({'train':path,'test':b})


if __name__=='__main__':
    unittest.main()
