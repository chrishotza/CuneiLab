"""Contract tests using generated photographs; NOT proof of real OCR quality."""
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from scripts.prepare_cuneiml_faces import (
    make_dataset, reference_for_face, bbox_from_record, load_face_map, main)
from scripts.batch_nabu import read_manifest
from scripts.evaluate_nabu import read_jsonl, evaluate
from scripts.prepare_cuneiml import split_for


def record():
    return {'id': 131837, 'bboxes': [[4, 6], [22, 19]],
            'text': {'obverse': [{'num': '1', 'sign': ['𒀭', '𒆠']}],
                     'reverse': [{'num': '1', 'sign': ['𒈗', '𒊩', '𒋗']}]} }


class FaceAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.photos = self.root / 'photos'
        self.photos.mkdir()
        # Deliberately textured synthetic composite with known crop.
        im = Image.new('RGB', (30, 30), 'white')
        for x in range(4, 22):
            for y in range(6, 19):
                im.putpixel((x, y), (40, 70, 100))
        im.save(self.photos / 'P131837.jpg', quality=100)
        self.records = [record()]

    def reviewed(self, face='reverse'):
        result = make_dataset(self.records, self.photos, self.root / 'review',
                              partition='all', mode='review')
        self.assertEqual(result['selected'], 1)
        path = self.root / 'review' / 'faces_template.jsonl'
        row = json.loads(path.read_text())
        row['face'] = face
        path.write_text(json.dumps(row) + '\n', encoding='utf-8')
        return path

    def test_review_crops_exact_source_geometry(self):
        path = self.reviewed()
        with Image.open(self.root / 'review' / 'images' / 'P131837_crop.png') as crop:
            self.assertEqual(crop.size, (18, 13))
        self.assertEqual(load_face_map(path)['P131837']['face'], 'reverse')
        self.assertFalse((self.root / 'review' / 'gold.jsonl').exists())
        page = (self.root / 'review' / 'revisar_caras.html').read_text(encoding='utf-8')
        self.assertIn('P131837_crop.png', page)
        self.assertIn('faces_revisadas.jsonl', page)
        self.assertIn('aria-label', page)

    def test_prepare_only_relevant_face_and_batch_compatible(self):
        path = self.reviewed()
        report = make_dataset(self.records, self.photos, self.root / 'bench',
                              mode='prepare', face_map=path, partition='all')
        self.assertEqual(report['selected'], 1)
        self.assertFalse(report['model_holdout_verified'])
        inputs = read_manifest(self.root / 'bench' / 'manifest.jsonl')
        self.assertEqual(inputs[0]['id'], 'P131837-reverse')
        gold = read_jsonl(self.root / 'bench' / 'gold.jsonl')
        self.assertEqual(gold['P131837-reverse'], '𒈗 𒊩 𒋗')
        self.assertNotIn('𒀭', next(iter(gold.values())))
        self.assertEqual(evaluate(gold, gold)['micro_sign_error_rate_including_missing'], 0)
        audit = json.loads((self.root / 'bench' / 'audit.jsonl').read_text())
        self.assertEqual(audit['face'], 'reverse')
        self.assertEqual(audit['crop_box'], [4, 6, 22, 19])

    def test_modified_photo_refused_and_no_partial_output(self):
        path = self.reviewed()
        im = Image.new('RGB', (30, 30), 'red')
        im.save(self.photos / 'P131837.jpg')
        with self.assertRaisesRegex(ValueError, 'cambió'):
            make_dataset(self.records, self.photos, self.root / 'bench',
                         mode='prepare', face_map=path, partition='all')
        self.assertFalse((self.root / 'bench').exists())

    def test_missing_review_fails_and_no_gold(self):
        with self.assertRaisesRegex(ValueError, 'Falta el mapa'):
            make_dataset(self.records, self.photos, self.root / 'bench',
                         mode='prepare', partition='all')
        self.assertFalse((self.root / 'bench').exists())

    def test_invalid_face_rejected(self):
        path = self.reviewed()
        raw = json.loads(path.read_text())
        raw['face'] = 'backside'
        path.write_text(json.dumps(raw) + '\n', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'cara inválida'):
            make_dataset(self.records, self.photos, self.root / 'bench',
                         mode='prepare', face_map=path, partition='all')

    def test_damaged_selected_face_never_partially_scored(self):
        rec = record()
        rec['text']['reverse'][0]['sign'].append('<D>')
        with self.assertRaisesRegex(ValueError, 'incompleta'):
            reference_for_face(rec, 'reverse')
        path = self.reviewed()
        with self.assertRaisesRegex(ValueError, 'No hay imágenes válidas'):
            make_dataset([rec], self.photos, self.root / 'bench',
                         mode='prepare', face_map=path, partition='all')

    def test_crop_bounds_and_ambiguous_bbox(self):
        rec = record()
        rec['bboxes'] = [[1, 2], [500, 501]]
        with self.assertRaisesRegex(ValueError, 'No hay imágenes válidas'):
            make_dataset([rec], self.photos, self.root / 'review', mode='review', partition='all')
        for bad in [None, [1,2,3,4], [[3, 4], [2, 5]]]:
            rec['bboxes'] = bad
            with self.assertRaises(ValueError): bbox_from_record(rec)

    def test_legacy_api_disabled(self):
        from scripts.prepare_cuneiml import prepare
        with self.assertRaisesRegex(ValueError, 'desactivada'):
            prepare(self.records, self.photos, self.root / 'unsafe')

    def test_main_cli_review(self):
        meta = self.root / 'meta.json'
        meta.write_text(json.dumps(self.records), encoding='utf8')
        self.assertEqual(main(['--metadata',str(meta), '--photos', str(self.photos),
                               '--output-dir',str(self.root/'review'),'--split','all']), 0)
        self.assertTrue((self.root / 'review' / 'faces_template.jsonl').exists())

if __name__ == '__main__':
    unittest.main()

class CroppedFaceMetricsTests(unittest.TestCase):
    def test_surface_markers_ignored_for_single_face(self):
        from scripts.evaluate_nabu import evaluate
        gold={'P131837-reverse':'𒈗 𒊩 𒋗'}
        prediction={'P131837-reverse':'@reverse\n𒈗 𒊩 𒋗'}
        self.assertGreater(evaluate(gold,prediction)['micro_sign_error_rate'],0)
        self.assertEqual(evaluate(gold,prediction,cropped_faces=True)['micro_sign_error_rate'],0)
        self.assertIn('surface tags ignored',evaluate(gold,prediction,cropped_faces=True)['metric'])

    def test_missing_predictions_still_penalized(self):
        from scripts.evaluate_nabu import evaluate
        gold={'P131837-obverse':'𒀭𒆠', 'P131837-reverse':'𒈗𒊩'}
        predicted={'P131837-obverse':'𒀭𒆠'}
        report=evaluate(gold,predicted,cropped_faces=True)
        self.assertEqual(report['coverage_images'],0.5)
        self.assertEqual(report['micro_sign_error_rate_including_missing'],0.5)
