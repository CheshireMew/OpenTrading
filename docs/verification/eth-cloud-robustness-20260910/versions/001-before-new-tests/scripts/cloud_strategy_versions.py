"""Append-only, human-readable checkpoints for the ETH strategy studies."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT/'docs/verification/eth-cloud-robustness-20260910/versions'


def snapshot(label, paths):
    destination = VERSIONS/label
    if destination.exists():
        raise ValueError(f'Checkpoint already exists: {destination}')
    files = sorted({Path(p).resolve() for p in paths if Path(p).is_file()})
    for path in files:
        path.relative_to(ROOT)
    destination.mkdir(parents=True)
    records = []
    for path in files:
        relative = path.relative_to(ROOT)
        target = destination/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        records.append({'path': relative.as_posix(), 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                        'bytes': target.stat().st_size})
    record = {'label': label, 'created_at': datetime.now(timezone.utc).isoformat(), 'files': records}
    (destination/'manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (VERSIONS/'history.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False)+'\n')
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('paths', nargs='+')
    args = parser.parse_args()
    print(json.dumps(snapshot(args.label, [ROOT/p for p in args.paths]), ensure_ascii=False))
