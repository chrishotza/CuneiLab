"""Doctor tests are independent of model weights and internet connectivity."""
from __future__ import annotations
import json
import subprocess
import sys
import unittest
from pathlib import Path
from scripts.doctor_nabu import inspect_python, main


class DoctorTests(unittest.TestCase):
    def test_reports_installed_packages_without_running_model(self):
        result = inspect_python(Path(sys.executable))
        self.assertFalse(result['model_weights_checked'])
        self.assertFalse(result['model_inference_checked'])
        self.assertEqual(set(result['packages']), {'torch','transformers','Pillow','accelerate','safetensors'})

    def test_missing_python(self):
        with self.assertRaises(ValueError):
            inspect_python(Path('/unavailable/cuneilab/python'))

    def test_bad_child_response(self):
        def broken(*args, **kwargs):
            return subprocess.CompletedProcess(args, 0, 'not-json', '')
        with self.assertRaisesRegex(ValueError, 'inválida'):
            inspect_python(Path(sys.executable), executor=broken)

    def test_child_command_is_isolated(self):
        calls=[]
        def fake(args, **kwargs):
            calls.append(args)
            data={'python':'3.11.0','platform':'Linux','packages':{k:'1.0' for k in ('torch','transformers','Pillow','accelerate','safetensors')}}
            return subprocess.CompletedProcess(args, 0, json.dumps(data), '')
        self.assertTrue(inspect_python(Path(sys.executable), executor=fake)['dependencies_present'])
        self.assertEqual(calls[0][1:3], ['-I','-c'])
        self.assertNotIn('trust_remote_code', ' '.join(calls[0]))

    def test_main_revision_validation(self):
        with self.assertRaises(SystemExit) as err:
            main(['--revision','main'])
        self.assertEqual(err.exception.code, 2)

if __name__=='__main__': unittest.main()
