#!/usr/bin/env python3
"""Install this skill into every agent harness on this machine.

Run from anywhere:

  python3 scripts/install.py            install into harnesses present on this machine
  python3 scripts/install.py --all      also create dirs for harnesses not installed yet
  python3 scripts/install.py --check    report missing or stale copies, change nothing

The folder holding SKILL.md is the source. Every harness copy is output, so never
edit a copy: re-run this script instead.

Exit codes: 0 clean, 1 drift found (--check only), 2 source missing.
"""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

HOME = Path.home()
SOURCE_DIR = Path(__file__).resolve().parent.parent
SOURCE = SOURCE_DIR / "SKILL.md"
NAME = SOURCE_DIR.name

ROOTS = [
    ("source", None, True),
    ("agents-std", HOME / ".agents/skills", True),
    ("hermes", HOME / ".hermes/skills/marketing", False),
    ("claude", HOME / ".claude/skills", False),
    ("codex", HOME / ".codex/skills", False),
    ("opencode", HOME / ".config/opencode/skills", False),
    ("kilo", HOME / ".kilo/skills", False),
    ("gemini", HOME / ".gemini/skills", False),
    ("cursor", HOME / ".cursor/skills", False),
    ("devin", HOME / ".codeium/windsurf/skills", False),
    ("continue", HOME / ".continue/skills", False),
    ("dsh", HOME / ".dsh/skills", False),
]


def files_in(root: Path) -> dict:
    return {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def sync(src: Path, dest: Path, write: bool) -> str:
    if not dest.exists():
        if not write:
            return "missing"
        shutil.copytree(src, dest)
        return "installed"
    if files_in(src) == files_in(dest):
        return "same"
    if not write:
        return "stale"
    shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return "installed"


def main() -> int:
    if not SOURCE.exists():
        print(f"source missing: {SOURCE}", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="create dirs for absent harnesses")
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = parser.parse_args()
    write = not args.check
    drift = 0

    for harness, root, always in ROOTS:
        if root is None:
            print(f"{harness:14} source        {SOURCE_DIR}")
            continue
        dest = root / NAME
        if root.exists():
            state = sync(SOURCE_DIR, dest, write)
        elif args.all:
            state = sync(SOURCE_DIR, dest, write)
        else:
            print(f"{harness:14} skipped       harness not installed")
            continue
        if state in ("stale", "missing"):
            drift += 1
        print(f"{harness:14} {state:13} {dest}")

    if args.check:
        print(f"\n{drift} cop{'y' if drift == 1 else 'ies'} need the installer")
        return 1 if drift else 0
    print(f"\ndone: {NAME} copied to every installed harness")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
