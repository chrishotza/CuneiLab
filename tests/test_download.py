"""Network-free integrity tests for the opt-in corpus installer."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from download_corpus import download, sha256_file

class DownloadTests(unittest.TestCase):
    def test_download_file_and_reuse(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root)/'fixture.bin'
            source.write_bytes(b'abc,train only\n')
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            output = Path(root)/'train.csv'
            report = download(source.as_uri(), output, sha)
            self.assertFalse(report['reused'])
            self.assertEqual(sha256_file(output), sha)
            self.assertTrue(download(source.as_uri(), output, sha)['reused'])

    def test_bad_hash_leaves_no_dataset(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/'source.csv'
            src.write_bytes(b'corrupt')
            target=Path(root)/'data'/'train.csv'
            with self.assertRaisesRegex(ValueError,'SHA256'):
                download(src.as_uri(), target, '0'*64)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.csv.part').exists())

    def test_size_limit(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/'too-big.bin'; src.write_bytes(b'hello')
            dest=Path(root)/'out.bin'
            with self.assertRaisesRegex(ValueError,'límite'):
                download(src.as_uri(), dest, '0'*64, max_bytes=3)
            self.assertFalse(dest.exists())

if __name__ == '__main__':
    unittest.main()
