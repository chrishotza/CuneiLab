import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from vision import VisionFormatError, validate_predictions, from_coco, from_mmdet, iou, evaluate, load_document

D = {'format':'cuneilab-detections','version':1, 'image':{'width':100,'height':100},
     'source':'test','detections':[{'bbox':[10,10,20,20],'label':'AN','confidence':0.9}]}

class Tests(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(validate_predictions(D)['detections'][0]['label'], 'AN')
    def test_bad_box(self):
        a={**D,'detections':[{'bbox':[95,0,20,10],'label':'AN'}]}
        with self.assertRaises(VisionFormatError):validate_predictions(a)
    def test_nan_score(self):
        a={**D,'detections':[{'bbox':[0,0,1,1],'label':'AN','confidence':float('nan')}]}
        with self.assertRaises(VisionFormatError):validate_predictions(a)
    def test_coco(self):
        c={'images':[{'id':1,'width':100,'height':100,'file_name':'a.png'}],
           'categories':[{'id':3,'name':'AN'}], 'annotations':[{'image_id':1,'category_id':3,'bbox':[1,2,10,12]}]}
        self.assertEqual(from_coco(c)['detections'][0]['label'],'AN')
    def test_multiple_images_rejected(self):
        c={'images':[{'id':1,'width':100,'height':100},{'id':2,'width':100,'height':100}], 'categories':[],'annotations':[]}
        with self.assertRaises(VisionFormatError):from_coco(c)
    def test_mmdet_adapter(self):
        class Tensor:
            def __init__(self, value):self.value=value
            def tolist(self):return self.value
        ins=SimpleNamespace(bboxes=Tensor([[10,20,30,50],[100,0,110,12]]),scores=Tensor([0.91,0.20]),labels=Tensor([2,1]))
        out=from_mmdet(ins,100,100,['A','B','C'])
        self.assertEqual(len(out['detections']),1)
        self.assertEqual(out['detections'][0]['label'],'C')
        self.assertEqual(out['detections'][0]['bbox'],[10,20,20,30])
        self.assertEqual(out['detections'][0]['reading'],'')
    def test_iou(self):
        self.assertEqual(iou([0,0,2,2],[0,0,2,2]),1)
        self.assertEqual(iou([0,0,2,2],[4,4,2,2]),0)
    def test_evaluate(self):
        pred={**D,'detections':D['detections']+[{'bbox':[60,60,10,10],'label':'KI','confidence':0.8}]}
        metrics=evaluate(D,pred)
        self.assertEqual((metrics['true_positives'],metrics['false_positives'],metrics['false_negatives']),(1,1,0))
        self.assertAlmostEqual(metrics['precision'],0.5)
    def test_evaluate_class_aware(self):
        wrong={**D,'detections':[{'bbox':[10,10,20,20],'label':'KI'}]}
        self.assertEqual(evaluate(D,wrong)['true_positives'],0)
    def test_evaluate_dimensions(self):
        wrong={**D,'image':{'width':200,'height':100}}
        with self.assertRaises(VisionFormatError):evaluate(D,wrong)
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'data.json'
            path.write_text(json.dumps(D),encoding='utf-8')
            self.assertEqual(load_document(path)['detections'][0]['label'],'AN')

if __name__=='__main__':unittest.main()
