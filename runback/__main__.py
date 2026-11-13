import argparse
import json
import sys
import zipfile
import zlib
from .core import doctor, snapshot, verify, restore, plan, load_selection, RunBackError
from . import __version__

def main():
    parser = argparse.ArgumentParser(description='RunBack: explicit small experiment snapshots (50 MiB max).')
    parser.add_argument('--version', action='version', version='RunBack ' + __version__)
    sub = parser.add_subparsers(dest='command', required=True)
    d = sub.add_parser('doctor'); d.add_argument('--storage', required=True)
    for command in ('snapshot', 'plan'):
        s = sub.add_parser(command)
        s.add_argument('--root', required=True)
        selection = s.add_mutually_exclusive_group(required=True)
        selection.add_argument('--include', action='append', help='Relative file path; repeat for each file')
        selection.add_argument('--include-file', help='UTF-8 JSON list of relative file paths')
        if command == 'snapshot':
            s.add_argument('--output', required=True)
    v = sub.add_parser('verify'); v.add_argument('archive')
    r = sub.add_parser('restore'); r.add_argument('archive'); r.add_argument('--to', required=True)
    a = parser.parse_args()
    try:
        if a.command in ('snapshot', 'plan'):
            names = load_selection(a.include_file) if a.include_file else a.include
        if a.command == 'doctor': result = doctor(a.storage)
        elif a.command == 'snapshot': result = snapshot(a.root, names, a.output)
        elif a.command == 'plan': result = plan(a.root, names)
        elif a.command == 'verify': result = verify(a.archive)
        else: result = restore(a.archive, a.to)
        print(json.dumps({'ok': True, 'command': a.command, 'result': result}, indent=2))
        return 0
    except (RunBackError, OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError, RecursionError, zlib.error) as e:
        print('RunBack: ' + str(e), file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
