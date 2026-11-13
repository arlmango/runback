import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from runback.core import snapshot, verify, restore, doctor, RunBackError, safe_path

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve(); self.root = self.base/'experiment'; self.root.mkdir()
        (self.root/'train.py').write_text('print("hello")\n'); (self.root/'metrics.json').write_text('{"loss": 0.5}')
        self.archive = self.base/'backup.zip'
    def snap(self):
        return snapshot(self.root, ['train.py', 'metrics.json'], self.archive)
    def forged(self, name='result.json', data=b'{}', **kwargs):
        entry = {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}; entry.update(kwargs)
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('manifest.json', json.dumps({'format':1, 'files':[entry]})); z.writestr('files/'+name, data)
    def test_round_trip(self):
        m=self.snap(); self.assertEqual(m, verify(self.archive)); out=self.base/'restored'; restore(self.archive,out)
        self.assertEqual((out/'train.py').read_bytes(), (self.root/'train.py').read_bytes())
    def test_repeated_snapshot_never_overwrites(self):
        self.snap(); original=self.archive.read_bytes()
        with self.assertRaises(RunBackError): self.snap()
        self.assertEqual(original,self.archive.read_bytes())
    def test_existing_restore_refused(self):
        self.snap()
        with self.assertRaises(FileExistsError): restore(self.archive,self.root)
    def test_missing_input(self):
        with self.assertRaises(RunBackError): snapshot(self.root,['missing'],self.archive)
        self.assertFalse(self.archive.exists())
    def test_explicit_files_only(self):
        (self.root/'folder').mkdir()
        with self.assertRaises(RunBackError): snapshot(self.root,['folder'],self.archive)
    def test_hidden(self):
        with self.assertRaises(RunBackError): snapshot(self.root,['.env'],self.archive)
    def test_sensitive_name(self):
        (self.root/'credentials.json').write_text('{}')
        with self.assertRaises(RunBackError): snapshot(self.root,['credentials.json'],self.archive)
    def test_secret_content(self):
        (self.root/'config.txt').write_text('password=supersecret123')
        with self.assertRaises(RunBackError): snapshot(self.root,['config.txt'],self.archive)
    def test_json_secret(self):
        (self.root/'config.json').write_text('{"api_key":"abcdefghijklmnop"}')
        with self.assertRaises(RunBackError): snapshot(self.root,['config.json'],self.archive)
    def test_controls_and_punctuation(self):
        for p in ['a\\nb', 'a?b', 'a|b', 'x'*241]:
            with self.subTest(p=p), self.assertRaises(RunBackError): safe_path(p)
    def test_physical_size_limit(self):
        with self.archive.open('wb') as f: f.truncate(54*1024*1024)
        with self.assertRaises(RunBackError): verify(self.archive)
    def test_symlink_source(self):
        (self.root/'link').symlink_to(self.root/'train.py')
        with self.assertRaises(RunBackError): snapshot(self.root,['link'],self.archive)
    def test_symlink_parent(self):
        (self.root/'linkdir').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(RunBackError): snapshot(self.root,['linkdir/train.py'],self.archive)
    def test_duplicates(self):
        with self.assertRaises(RunBackError): snapshot(self.root,['train.py','train.py'],self.archive)
    def test_invalid_paths(self):
        for p in ['../x','/x','a//x','a/./x','a/../x','C:/x','a\\x','.env','a/.git/x','CON','x.','x ']:
            with self.subTest(p=p), self.assertRaises(RunBackError): safe_path(p)
    def test_tampered_hash(self):
        self.forged(sha256='0'*64)
        with self.assertRaises(RunBackError): restore(self.archive,self.base/'restored')
        self.assertFalse((self.base/'restored').exists())
    def test_traversal_archive(self):
        self.forged('../escaped')
        with self.assertRaises(RunBackError): restore(self.archive,self.base/'restored')
        self.assertFalse((self.base/'escaped').exists())
    def test_extra_entry(self):
        self.snap()
        with zipfile.ZipFile(self.archive,'a') as z: z.writestr('extra.txt','extra')
        with self.assertRaises(RunBackError): verify(self.archive)
    def test_symlink_archive(self):
        self.forged()
        with zipfile.ZipFile(self.archive,'a') as z:
            i=zipfile.ZipInfo('link'); i.create_system=3; i.external_attr=(stat.S_IFLNK|0o777)<<16; z.writestr(i,'/tmp/outside')
        with self.assertRaises(RunBackError): verify(self.archive)
    def test_restore_symlink_parent(self):
        self.snap(); (self.base/'linked').symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(RunBackError): restore(self.archive,self.base/'linked'/'new')
    def test_bad_size(self):
        self.forged(bytes=True)
        with self.assertRaises(RunBackError): verify(self.archive)
    def test_bad_hash_format(self):
        self.forged(sha256='a')
        with self.assertRaises(RunBackError): verify(self.archive)
    def test_secret_in_forged_archive(self):
        self.forged(data=b'password=supersecret123')
        with self.assertRaises(RunBackError): verify(self.archive)
    def test_doctor(self):
        self.assertTrue(doctor(self.root)['writable'])
    def test_cli_failure(self):
        result=subprocess.run([sys.executable,'-m','runback','verify',str(self.base/'missing')],capture_output=True,text=True)
        self.assertEqual(result.returncode,1); self.assertNotIn('Traceback',result.stderr)
    def test_cli_round_trip(self):
        commands=[['snapshot','--root',str(self.root),'--include','train.py','--output',str(self.archive)],['verify',str(self.archive)],['restore',str(self.archive),'--to',str(self.base/'restored')]]
        for args in commands:
            p=subprocess.run([sys.executable,'-m','runback',*args],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr); self.assertTrue(json.loads(p.stdout)['ok'])

if __name__=='__main__': unittest.main()
