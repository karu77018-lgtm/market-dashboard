#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


TEXT_SUFFIXES = {
    ".csv", ".html", ".ini", ".js", ".json", ".log", ".md", ".py",
    ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
TOKEN_PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b")),
    ("stripe-live-key", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b")),
)
ASSIGNMENT = re.compile(
    r'''(?ix)
    ["']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|
             password|passwd|authorization|bearer[_-]?token)["']?
    \s*[:=]\s*["']([^"'\s,}]{12,})["']
    '''
)
SAFE_VALUE_MARKERS = (
    "${{", "${", "$", "process.env", "os.environ", "redacted",
    "placeholder", "example", "not_configured", "your_", "<", "***",
)


def iter_files(root: Path, requested: list[str]) -> list[Path]:
    paths: set[Path] = set()
    for raw in requested:
        candidate = (root / raw).resolve()
        if not candidate.exists():
            raise FileNotFoundError(raw)
        if candidate.is_dir():
            paths.update(path for path in candidate.rglob("*") if path.is_file())
        else:
            paths.add(candidate)
    return sorted(paths)


def tracked_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True
    )
    return [item.decode("utf-8") for item in completed.stdout.split(b"\0") if item]


def scan_file(path: Path) -> list[tuple[int, str]]:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
        return []
    findings: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_no, line in enumerate(handle, 1):
            for label, pattern in TOKEN_PATTERNS:
                if pattern.search(line):
                    findings.append((line_no, label))
            for match in ASSIGNMENT.finditer(line):
                value = match.group(1).lower()
                if not any(marker.lower() in value for marker in SAFE_VALUE_MARKERS):
                    findings.append((line_no, "credential-assignment"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail closed if likely credentials are present in preservation inputs")
    parser.add_argument("--root", default=".")
    parser.add_argument("--include-tracked", action="store_true")
    parser.add_argument("path", nargs="*")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    requested = list(args.path)
    if args.include_tracked:
        requested.extend(tracked_files(root))
    files = iter_files(root, sorted(set(requested)))
    findings: list[str] = []
    for path in files:
        relative = path.relative_to(root)
        for line_no, label in scan_file(path):
            findings.append(f"{relative}:{line_no}: {label}")

    if findings:
        print("Potential secret material detected; preservation stopped.")
        print("\n".join(findings))
        return 2
    print(f"Secret scan passed for {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
