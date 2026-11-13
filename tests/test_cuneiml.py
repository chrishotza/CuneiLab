"""Synthetic fixtures only; do not confuse with the external published dataset."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.prepare_cuneiml import canonical_id, reference_glyphs, prepare, split_for, records_from_metadata, excluded_ids, md5_file
from scripts.batch_nabu import read_manifest
from scripts.evaluate_nabu import read_jsonl, evaluate


def row(i=123456, sign='𒀭'):
    return {'id': i, 'text': {'obverse': [{'raw': 'an ki', 'num': '1', 'sign': [sign, '𒆠']}],
                             'reverse': [{'raw': 'lugal', 'num': '1', 'sign': ['𒈗']}]}}


class CuneiMLTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photos = self.root / 'photos'
        self.photos.mkdir()
        (self.photos / 'P123456.jpg').write_bytes(b'local synthetic photo fixture')

    def test_id_formats(self):
        self.assertEqual(canonical_id(123456), 'P123456')
        self.assertEqual(canonical_id('12'), 'P000012')
        for value in [True, -1, 'Pxx', '../P123456', 1234567]:
            with self.assertRaises(ValueError): canonical_id(value)

    def test_strict_ground_truth_preserves_faces(self):
        text, count = reference_glyphs(row())
        self.assertEqual(count, 3)
        self.assertEqual(text, '@obverse\n𒀭 𒆠\n@reverse\n𒈗')
        with self.assertRaisesRegex(ValueError, 'desconocido'):
            reference_glyphs(row(sign='<D>'))
        with self.assertRaises(ValueError):
            reference_glyphs({'text': {'unknown': [{'sign': ['𒀭']}]}})

    def test_read_both_json_shapes(self):
        f = self.root / 'meta.json'
        f.write_text(json.dumps([row()], ensure_ascii=False), encoding='utf-8')
        self.assertEqual(records_from_metadata(f)[0]['id'], 123456)
        f.write_text(json.dumps({'P123456': row()}, ensure_ascii=False), encoding='utf-8')
        self.assertEqual(len(records_from_metadata(f)), 1)
        f.write_text('123', encoding='utf-8')
        with self.assertRaises(ValueError): records_from_metadata(f)

    def test_manifest_compatible_with_batch_and_evaluation(self):
        report = prepare([row()], self.photos, self.root / 'out', partition='all')
        self.assertEqual(report['images_selected'], 1)
        self.assertFalse(report['model_holdout_verified'])
        inputs = read_manifest(self.root / 'out' / 'manifest.jsonl')
        self.assertEqual(inputs[0]['id'], 'P123456')
        gold = read_jsonl(self.root / 'out' / 'gold.jsonl')
        metrics = evaluate(gold, gold)
        self.assertEqual(metrics['micro_sign_error_rate'], 0)
        self.assertEqual(metrics['images_scored'], 1)
        self.assertEqual(json.loads((self.root / 'out' / 'dataset.json').read_text())['source_version'], '1.2')
        with self.assertRaisesRegex(ValueError, 'ya existe'):
            prepare([row()], self.photos, self.root / 'out', partition='all')

    def test_no_images_no_fake_results(self):
        with self.assertRaisesRegex(ValueError, 'No hay pares'):
            prepare([row()], self.photos, self.root / 'nope', partition='test', exclude_ids={'P123456'})
        self.assertFalse((self.root / 'nope').exists())

    def test_dict_without_row_ids_and_integrity(self):
        f=self.root/'records.json'
        data=row(); del data['id']
        f.write_text(json.dumps({'P123456':data},ensure_ascii=False),encoding='utf-8')
        self.assertEqual(records_from_metadata(f)[0]['id'],'P123456')
        self.assertEqual(len(md5_file(f)),32)

    def test_deterministic_split_and_exclusions(self):
        self.assertEqual(split_for('P123456'), split_for('P123456'))
        f=self.root / 'excluded.txt'
        f.write_text('# Nabu training set\nP123456\n12\n', encoding='utf-8')
        self.assertEqual(excluded_ids(f), {'P123456', 'P000012'})

if __name__ == '__main__': unittest.main()
