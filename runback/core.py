import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone

LIMIT = 50 * 1024 * 1024
MAX_FILES = 1000
MANIFEST_LIMIT = 1024 * 1024
SECRET = re.compile(rb'(?:-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,})|(?:api[_-]?key|access[_-]?token|password|secret)[\"\']?\s*[=:]\s*[\"\']?[^\s\"\']{8,})', re.I)

class RunBackError(ValueError):
    pass

def safe_path(name):
    if not isinstance(name, str) or not name or len(name) > 240 or '\\' in name or ':' in name or any(ord(c) < 32 or c in '<>"|?*' for c in name):
        raise RunBackError('Unsafe path')
    p = PurePosixPath(name)
    if p.is_absolute() or str(p) != name or any(x in ('', '.', '..') or x.startswith('.') for x in p.parts):
        raise RunBackError('Unsafe or hidden path: ' + name)
    # Portable extraction: avoid Windows reserved names/trailing dots/spaces.
    if any(x.endswith((' ', '.')) or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', x, re.I) for x in p.parts):
        raise RunBackError('Non-portable path: ' + name)
    return p

def blocked(name):
    for part in PurePosixPath(name).parts:
        if re.search(r'(secret|credential|password|token|^id_rsa$|^id_ed25519$)', part, re.I) or part.lower().endswith(('.pem', '.key', '.p12', '.pfx')):
            return True
    return False

def check_source(root, name):
    p = safe_path(name)
    if blocked(name):
        raise RunBackError('Sensitive filename refused: ' + name)
    cur = root
    for part in p.parts:
        cur = cur / part
        if cur.is_symlink():
            raise RunBackError('Symlink refused: ' + name)
    if not cur.is_file():
        raise RunBackError('Select regular files explicitly: ' + name)
    return cur

def snapshot(root, names, output):
    root = Path(root).resolve(strict=True)
    if not root.is_dir() or not names or len(names) > MAX_FILES:
        raise RunBackError('Select 1–1000 files from a directory')
    if len(set(n.casefold() for n in names)) != len(names):
        raise RunBackError('Duplicate file selection')
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise RunBackError('Snapshot output already exists')
    payload, total = [], 0
    for name in names:
        src = check_source(root, name)
        if src.resolve() == output.resolve():
            raise RunBackError('Output cannot be an input')
        # NOFOLLOW protects final component; do not run alongside adversarial filesystem writers.
        fd = os.open(src, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise RunBackError('Not a regular file')
            data = f.read(LIMIT + 1)
        total += len(data)
        if total > LIMIT:
            raise RunBackError('Snapshot exceeds 50 MiB uncompressed limit')
        if SECRET.search(data):
            raise RunBackError('Possible secret detected in ' + name + '; remove it first')
        payload.append((name, data))
    manifest = {'format': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'python': sys.version.split()[0], 'runback': '0.1.0',
                'files': [{'path': n, 'bytes': len(d), 'sha256': hashlib.sha256(d).hexdigest()} for n, d in payload]}
    # Exclusive creation avoids accidental overwrite even on repeated CLI calls.
    created = False
    try:
        with output.open('xb') as raw:
            created = True
            with zipfile.ZipFile(raw, 'w', zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json', json.dumps(manifest, indent=2))
                for name, data in payload:
                    z.writestr('files/' + name, data)
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise
    return manifest

def _load(archive):
    if Path(archive).stat().st_size > LIMIT + MANIFEST_LIMIT + 2 * 1024 * 1024:
        raise RunBackError('Archive physical size exceeds limit')
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES + 1 or len({i.filename.casefold() for i in infos}) != len(infos):
            raise RunBackError('Too many or duplicate archive entries')
        for i in infos:
            safe_path(i.filename)
            mode = (i.external_attr >> 16) & 0o170000
            if i.is_dir() or mode not in (0, stat.S_IFREG) or i.flag_bits & 1:
                raise RunBackError('Only unencrypted regular files allowed')
            if i.file_size > LIMIT:
                raise RunBackError('Entry too large')
        if sum(i.file_size for i in infos) > LIMIT + MANIFEST_LIMIT:
            raise RunBackError('Archive too large')
        m = z.getinfo('manifest.json')
        if m.file_size > MANIFEST_LIMIT:
            raise RunBackError('Manifest too large')
        manifest = json.loads(z.read(m))
        if not isinstance(manifest, dict) or type(manifest.get('format')) is not int or manifest['format'] != 1:
            raise RunBackError('Unsupported manifest')
        entries = manifest.get('files')
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
            raise RunBackError('Invalid file list')
        expected, payload, total = {'manifest.json'}, [], 0
        paths = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise RunBackError('Invalid manifest entry')
            name = entry.get('path'); safe_path(name)
            if blocked(name) or name.casefold() in paths:
                raise RunBackError('Sensitive or duplicate path')
            # Disallow parent-file conflicts, including on case-insensitive filesystems.
            folded = name.casefold()
            if any(folded.startswith(p + '/') or p.startswith(folded + '/') for p in paths):
                raise RunBackError('Conflicting paths')
            paths.add(folded)
            size = entry.get('bytes'); digest = entry.get('sha256')
            if type(size) is not int or size < 0 or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                raise RunBackError('Invalid size/hash')
            total += size
            if total > LIMIT:
                raise RunBackError('Payload too large')
            key = 'files/' + name; expected.add(key)
            info = z.getinfo(key)
            if info.file_size != size:
                raise RunBackError('Size mismatch: ' + name)
            data = z.read(info)
            if hashlib.sha256(data).hexdigest() != digest:
                raise RunBackError('Hash mismatch: ' + name)
            if SECRET.search(data):
                raise RunBackError('Possible secret detected in ' + name)
            payload.append((name, data))
        if {i.filename for i in infos} != expected:
            raise RunBackError('Unexpected archive entries')
        return manifest, payload

def verify(archive):
    return _load(archive)[0]

def restore(archive, destination):
    manifest, payload = _load(archive)  # Verify completely before writing anything.
    destination = Path(destination).absolute()
    # Reject symlink ancestors. Parent must already exist; destination must be new.
    if any(p.is_symlink() for p in [destination, *destination.parents]):
        raise RunBackError('Symlink destination refused')
    destination.mkdir(mode=0o700)
    try:
        for name, data in payload:
            dest = destination / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f:
                f.write(data)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return manifest

def doctor(root):
    p = Path(root).resolve(strict=True)
    if not p.is_dir():
        raise RunBackError('Storage must be a directory')
    with tempfile.TemporaryFile(dir=p) as f:
        f.write(b'runback-write-check'); f.flush()
    return {'python': sys.version.split()[0], 'storage': str(p), 'writable': True,
            'free_bytes': shutil.disk_usage(p).free,
            'warning': 'Writable does NOT mean persistent. Confirm Drive is mounted and keep a copy outside the runtime. GPU is not required for RunBack.'}
