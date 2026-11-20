"""Shared atomic JSON write with first-change backup for host hooks.json files."""
import json
import os


def write_json_with_backup(path, original, data):
    """Atomically write data as JSON to path, keeping the first original bytes in path.bak."""
    path.parent.mkdir(parents=True, exist_ok=True)
    bak = path.with_name(path.name + ".bak")
    if original is not None and not bak.exists():  # keep the first backup: it is the author's original
        bak.write_bytes(original)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(path))
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
