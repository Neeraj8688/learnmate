#!/usr/bin/env python3
"""Fail if the tree (or a zip) contains likely secrets or private data files.
Usage:  python scripts/scan_secrets.py [folder-or-zip ...]     (default: the project root)
Heuristic, not a guarantee: it catches Google/OpenAI-style keys, private keys, secret-looking assignments
outside *.example files, and files that must never ship (.env, databases, vector data, logs)."""
import re
import sys
import zipfile
from pathlib import Path

CONTENT = [
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Secret-looking assignment", re.compile(
        r"(?im)^\s*(?:export\s+)?[A-Z_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z_]*\s*=\s*['\"]?(?!replace|your|changeme|<|\$|x{3,}|$)[A-Za-z0-9_\-+/=]{16,}")),
]
BAD_NAMES = re.compile(r"(^|/)(\.env(\.(?!example$)[^/]*)?|\.jwt_secret|\.enc_key|[^/]*\.(db|sqlite3?|log|pem))$|(^|/)(data|chroma|uploads|node_modules|\.venv|\.git)/")
TEXT_EXT = {".py", ".js", ".jsx", ".json", ".md", ".yml", ".yaml", ".txt", ".example", ".toml", ".html", ".css", ".env", ".cfg", ".ini", ""}
SKIP_CONTENT = re.compile(r"(^|/)(package-lock\.json|tests/)")   # test files hold fake sentinel keys on purpose


def scan_text(name, text, problems):
    if SKIP_CONTENT.search(name) or name.endswith(".example"):
        return
    for label, rx in CONTENT:
        m = rx.search(text)
        if m:
            problems.append(f"{name}: {label} ({m.group(0)[:6]}...)")


def scan_dir(root: Path, problems):
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_dir():
            continue
        if BAD_NAMES.search(rel):
            problems.append(f"{rel}: file/folder must not be shipped"); continue
        if p.suffix.lower() in TEXT_EXT and p.stat().st_size < 2_000_000:
            scan_text(rel, p.read_text(errors="ignore"), problems)


def scan_zip(zpath: Path, problems):
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if BAD_NAMES.search(name):
                problems.append(f"{name}: file must not be shipped"); continue
            if Path(name).suffix.lower() in TEXT_EXT and info.file_size < 2_000_000:
                scan_text(name, z.read(info).decode("utf-8", "ignore"), problems)


def main(argv):
    targets = [Path(a) for a in argv] or [Path(__file__).resolve().parent.parent]
    problems = []
    for t in targets:
        (scan_zip if t.suffix == ".zip" else scan_dir)(t, problems)
    if problems:
        print("POSSIBLE SECRETS / PRIVATE FILES FOUND:"); [print("  -", p) for p in problems]; return 1
    print("scan_secrets: clean (" + ", ".join(map(str, targets)) + ")"); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
