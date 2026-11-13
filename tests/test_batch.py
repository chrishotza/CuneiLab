import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from scripts.batch_nabu import read_manifest,run_batch,fingerprint,main
from transcription import make_document

REV='a'*40
MODEL='boatbomber/NabuOCR'

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'tablet.png').write_bytes(b'fixture image for tests, not an OCR target')
        self.manifest=self.root/'dataset.jsonl'
        self.manifest.write_text(json.dumps({'id':'P000001','image':'tablet.png'})+'\n',encoding='utf8')

    def test_check_no_inference_and_no_directory_creation(self):
        result=main(['--manifest',str(self.manifest),'--check','--output-dir',str(self.root/'output')])
        self.assertEqual(result,0)
        self.assertFalse((self.root/'output').exists())

    def test_read_and_hash(self):
        entries=read_manifest(self.manifest)
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]['image_sha256'],hashlib.sha256((self.root/'tablet.png').read_bytes()).hexdigest())

    def test_path_traversal_and_duplicate(self):
        self.manifest.write_text(json.dumps({'id':'x','image':'../other.png'}),encoding='utf8')
        with self.assertRaises(ValueError):read_manifest(self.manifest)
        self.manifest.write_text((json.dumps({'id':'x','image':'tablet.png'})+'\n')*2,encoding='utf8')
        with self.assertRaises(ValueError):read_manifest(self.manifest)

    def test_symlink_escape(self):
        external=self.root.parent/'out-of-dir-test.png'
        # Point outside root without creating external file: path.resolve remains outside.
        (self.root/'outside.png').symlink_to(external)
        self.manifest.write_text(json.dumps({'id':'test','image':'outside.png'}),encoding='utf8')
        with self.assertRaises(ValueError):read_manifest(self.manifest)

    def test_batch_and_resume(self):
        entries=read_manifest(self.manifest)
        invoked=[]
        def fake(path):
            invoked.append(path)
            return make_document('𒀭𒆠',80,60,path.name,model=f'{MODEL}@{REV}')
        output=self.root/'output'
        report=run_batch(entries,output,model=MODEL,revision=REV,runner=fake)
        self.assertEqual((report['succeeded'],report['failed']),(1,0))
        self.assertEqual(len(invoked),1)
        predictions=[json.loads(x) for x in (output/'predictions.jsonl').read_text(encoding='utf8').splitlines()]
        self.assertEqual(predictions[0]['text'],'𒀭𒆠')
        self.assertEqual((output/'documents'/'P000001.json').exists(),True)
        with self.assertRaises(ValueError):run_batch(entries,output,model=MODEL,revision=REV,runner=fake)
        again=run_batch(entries,output,model=MODEL,revision=REV,runner=fake,resume=True)
        self.assertEqual(again['skipped_resumed'],1)
        self.assertEqual(len(invoked),1)

    def test_changed_image_invalidates_resume(self):
        entries=read_manifest(self.manifest)
        output=self.root/'output'
        fake=lambda path:make_document('𒀭',80,60,path.name,model=f'{MODEL}@{REV}')
        run_batch(entries,output,model=MODEL,revision=REV,runner=fake)
        (self.root/'tablet.png').write_bytes(b'new image')
        with self.assertRaises(ValueError):run_batch(read_manifest(self.manifest),output,model=MODEL,revision=REV,runner=fake,resume=True)

    def test_failure_recorded_not_hallucinated(self):
        entries=read_manifest(self.manifest)
        def fail(path):raise RuntimeError('GPU exhausted')
        report=run_batch(entries,self.root/'results',model=MODEL,revision=REV,runner=fail)
        self.assertEqual(report['failed'],1)
        self.assertEqual((self.root/'results'/'predictions.jsonl').read_text(), '')
        errors=json.loads((self.root/'results'/'errors.jsonl').read_text().strip())
        self.assertEqual(errors['error_type'],'RuntimeError')

    def test_wrong_model_rejected(self):
        entries=read_manifest(self.manifest)
        fake=lambda path:make_document('𒀭',20,20,path.name,model='unverified')
        report=run_batch(entries,self.root/'bad',model=MODEL,revision=REV,runner=fake)
        self.assertEqual(report['failed'],1)

if __name__=='__main__':unittest.main()
