import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from runback import __version__
from runback.core import load_selection, plan, snapshot, verify, RunBackError

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root/'result.txt').write_text('example', encoding='utf-8')
        self.selection = self.root/'selection.json'

    def write(self, value):
        self.selection.write_text(json.dumps(value), encoding='utf-8')
        return self.selection

    def test_selection_valid(self):
        self.assertEqual(load_selection(self.write(['result.txt'])), ['result.txt'])

    def test_selection_invalid_types(self):
        for value in ({'files': ['result.txt']}, 'result.txt', [], [None], [42]):
            with self.subTest(value=value), self.assertRaises(RunBackError):
                load_selection(self.write(value))

    def test_selection_invalid_paths(self):
        for value in (['../outside'], ['/etc/passwd'], ['.env'], ['result.txt','RESULT.txt']):
            with self.subTest(value=value), self.assertRaises(RunBackError):
                load_selection(self.write(value))

    def test_selection_bad_encoding(self):
        self.selection.write_bytes(b'\xff')
        with self.assertRaises(UnicodeError): load_selection(self.selection)

    def test_selection_size_limit(self):
        self.selection.write_bytes(b' '*(1024*1024+1))
        with self.assertRaises(RunBackError): load_selection(self.selection)

    def test_selection_symlink(self):
        self.write(['result.txt'])
        link = self.root/'link.json'; link.symlink_to(self.selection)
        with self.assertRaises(RunBackError): load_selection(link)

    def test_plan_does_not_write(self):
        before = sorted(self.root.iterdir())
        result = plan(self.root, ['result.txt'])
        self.assertEqual(result['total_bytes'], 7)
        self.assertEqual(result['file_count'], 1)
        self.assertFalse(result['writes_performed'])
        self.assertEqual(before, sorted(self.root.iterdir()))
        out = self.root/'backup.zip'
        manifest = snapshot(self.root, ['result.txt'], out)
        self.assertEqual(result['files'], manifest['files'])
        self.assertEqual(manifest['runback'], __version__)
        verify(out)

    def test_plan_rejects_secrets(self):
        (self.root/'result.txt').write_text('password=synthetic-test-value')
        with self.assertRaises(RunBackError): plan(self.root, ['result.txt'])

    def test_plan_rejects_oversize(self):
        with patch('runback.core.LIMIT', 6):
            with self.assertRaises(RunBackError): plan(self.root, ['result.txt'])

    def test_snapshot_rechecks_after_plan(self):
        plan(self.root, ['result.txt'])
        (self.root/'result.txt').write_text('password=synthetic-test-value')
        out = self.root/'backup.zip'
        with self.assertRaises(RunBackError): snapshot(self.root, ['result.txt'], out)
        self.assertFalse(out.exists())

    def test_cli_selection_round_trip(self):
        self.write(['result.txt'])
        base = [sys.executable, '-m', 'runback']
        args = ['--root',str(self.root),'--include-file',str(self.selection)]
        for command in ([*base,'plan',*args], [*base,'snapshot',*args,'--output',str(self.root/'out.zip')]):
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['ok'])
        verify(self.root/'out.zip')

    def test_cli_invalid_selection_has_no_traceback(self):
        self.selection.write_text('{broken')
        result = subprocess.run([sys.executable,'-m','runback','plan','--root',str(self.root),'--include-file',str(self.selection)],capture_output=True,text=True)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('Traceback',result.stderr)

    def test_interrupted_write_removes_incomplete_archive(self):
        out = self.root/'backup.zip'
        with patch('runback.core.zipfile.ZipFile.writestr', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError): snapshot(self.root, ['result.txt'], out)
        self.assertFalse(out.exists())
        self.assertEqual((self.root/'result.txt').read_text(), 'example')

    def test_truncated_archive_is_rejected(self):
        out = self.root/'backup.zip'
        snapshot(self.root, ['result.txt'], out)
        out.write_bytes(out.read_bytes()[:20])
        import zipfile
        with self.assertRaises(zipfile.BadZipFile): verify(out)

    def test_cli_version(self):
        result = subprocess.run([sys.executable,'-m','runback','--version'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stdout.strip(),'RunBack '+__version__)

if __name__ == '__main__': unittest.main()
