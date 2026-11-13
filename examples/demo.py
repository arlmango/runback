"""Offline round trip, no deletion or modification of user files."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runback.core import snapshot, verify, restore

with tempfile.TemporaryDirectory(prefix='runback-demo-') as tmp:
    root = Path(tmp).resolve(); experiment = root/'experiment'; experiment.mkdir()
    (experiment/'train.py').write_text('print("demo only")\n')
    (experiment/'metrics.json').write_text('{"loss": 0.5}\n')
    archive = root/'demo.zip'
    snapshot(experiment, ['train.py', 'metrics.json'], archive)
    verify(archive)
    restored = root/'restored'; restore(archive, restored)
    for name in ['train.py', 'metrics.json']:
        assert (experiment/name).read_bytes() == (restored/name).read_bytes()
    print('PASS: snapshot, SHA256 verification, restore, identical bytes. Demo temporary files cleaned automatically.')
