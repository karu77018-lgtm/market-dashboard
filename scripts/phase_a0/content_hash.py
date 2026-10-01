"""Fingerprint preserved content, excluding only acquisition/run timestamps."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

VOLATILE = {'generated_at', 'checked_at', 'updated_at', 'recorded_at',
            'github_run_id', 'github_run_attempt', 'actions_started_at',
            'fetched_sessions', 'fetched_at', 'pages', 'source_before_delta'}


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def content_bytes(path: Path):
    raw = path.read_bytes()
    if path.suffix == '.json':
        return json.dumps(stable(json.loads(raw)), sort_keys=True,
                          separators=(',', ':'), ensure_ascii=False).encode()
    if path.suffix == '.html':
        text = raw.decode()
        # This digest is for archive dedup only. Keep trading dates, prices,
        # correction notices and model versions intact.
        text = re.sub(r'"(?:generated_at|checked_at)"\s*:\s*"[^"]*"', '"run_timestamp":""', text)
        text = re.sub(r'<meta\b(?=[^>]*\bname="dashboard-source-sha256")[^>]*>', '', text)
        text = re.sub(r'(更新(?:時点|日時)?[:： ]*)(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}(?::\d{2})?(?:Z| UTC| JST)?)', r'\1RUN_TIME', text)
        return text.encode()
    return raw


def content_hash(files, session, mode):
    evidence = [[relative, hashlib.sha256(content_bytes(staged)).hexdigest()]
                for staged, relative in files]
    return hashlib.sha256(json.dumps([session, mode, sorted(evidence)],
                                    separators=(',', ':')).encode()).hexdigest()
