# Changes

## 0.2.0
- `plan`: validate selected files and show hashes/size before creating a backup.
- `--include-file`: reuse an explicit UTF-8 JSON list with `plan` and `snapshot`.
- `--version`, expanded tests, Linux/macOS CI, and a saved-selection Colab example.
- Invalid selections fail closed; preview is not a backup and snapshot rechecks files.
- Archive format remains version 1; existing 0.1.0 archives remain readable.

## 0.1.0
- Initial prototype: doctor, snapshot, verify, restore; explicit files only.
