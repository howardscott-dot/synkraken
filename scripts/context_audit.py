#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "audits",
    "cache",
    "data",
    "dist",
    "build",
    ".mypy_cache",
    ".hermes",
}
SKIP_PATH_PREFIXES = {
    ("apps", "console", "node_modules"),
    ("apps", "console", "dist"),
    ("apps", "console", "src-tauri", "target"),
}
SKIP_SUFFIXES = {".pyc", ".sqlite", ".sqlite3", ".db", ".log"}
TEXT_SUFFIXES = {
    ".md", ".py", ".json", ".sh", ".service", ".txt", ".toml", ".yaml", ".yml",
}

BANNED_STRINGS = [
    "Studio Blueprint",
    "howardscott-dot",
    "synkraken-live-test",
    "sb_methodology",
    "Build SynKraken",
    "Howard Scott",
]

ABSOLUTE_USER_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.-])/(home|Users)/([A-Za-z0-9_.-]+)")

EXCEPTIONS = [
    {
        "path": "LICENSE",
        "pattern": "MIT License",
        "reason": "license name",
    },
    {
        "path": "README.md",
        "pattern": "/home/myuser",
        "reason": "generic path example in docs",
    },
    {
        "path": "docs/INSTALL.md",
        "pattern": "/home/myuser",
        "reason": "generic path example in docs",
    },
    {
        "path": "README.md",
        "pattern": "howardscott-dot",
        "reason": "public project repository URL",
    },
    {
        "path": "README.md",
        "pattern": "howard",
        "reason": "public project repository URL",
    },
    {
        "path": "docs/OPERATOR_GUIDE.md",
        "pattern": "howardscott-dot",
        "reason": "public project repository URL",
    },
    {
        "path": "docs/OPERATOR_GUIDE.md",
        "pattern": "howard",
        "reason": "public project repository URL",
    },
    {
        "path": "scripts/install.sh",
        "pattern": "howardscott-dot",
        "reason": "public project repository URL",
    },
    {
        "path": "scripts/install.sh",
        "pattern": "howard",
        "reason": "public project repository URL",
    },
]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_scan(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in SKIP_DIRS for part in relative.parts):
        return False
    if any(relative.parts[:len(prefix)] == prefix for prefix in SKIP_PATH_PREFIXES):
        return False
    if path == Path(__file__).resolve():
        return False
    if path.name in {"config.local.json"}:
        return False
    if path.suffix in SKIP_SUFFIXES:
        return False
    if path.name in {"LICENSE"}:
        return True
    return path.suffix in TEXT_SUFFIXES


def is_exception(path: Path, line: str, token: str) -> str | None:
    relative = rel(path)
    for item in EXCEPTIONS:
        if relative == item["path"] and item["pattern"] in line and item["pattern"] in token:
            return item["reason"]
    return None


def audit() -> tuple[list[dict], list[dict]]:
    findings: list[dict] = []
    exceptions: list[dict] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or not should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for token in BANNED_STRINGS:
                if token not in line:
                    continue
                reason = is_exception(path, line, token)
                item = {
                    "path": rel(path),
                    "line": lineno,
                    "rule": "banned-string",
                    "match": token,
                    "text": line.strip(),
                }
                if reason:
                    item["reason"] = reason
                    exceptions.append(item)
                else:
                    findings.append(item)
            for match in ABSOLUTE_USER_PATH_RE.finditer(line):
                token = match.group(0)
                username = match.group(2)
                if username in {"operator", "runner", "sandbox"}:
                    continue
                reason = is_exception(path, line, token)
                item = {
                    "path": rel(path),
                    "line": lineno,
                    "rule": "absolute-user-path",
                    "match": token,
                    "text": line.strip(),
                }
                if reason:
                    item["reason"] = reason
                    exceptions.append(item)
                else:
                    findings.append(item)
    return findings, exceptions


def main() -> int:
    findings, exceptions = audit()
    print("context audit")
    print(f"findings: {len(findings)}")
    for item in findings:
        print(f"{item['path']}:{item['line']}: {item['rule']} {item['match']!r}: {item['text']}")
    print(f"exceptions: {len(exceptions)}")
    for item in exceptions:
        print(f"{item['path']}:{item['line']}: {item['rule']} {item['match']!r}: {item['reason']}")
    if findings:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
