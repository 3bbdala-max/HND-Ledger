#!/usr/bin/env python3
"""Create or verify a deterministic SHA-256 manifest for the Git checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

MANIFEST_RELATIVE_PATH = "evidence/SHA256-MANIFEST.json"


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], stderr=subprocess.PIPE
    ).decode("utf-8").strip()


def tracked_files() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    paths = [item.decode("utf-8") for item in raw.split(b"\x00") if item]
    return sorted(path for path in paths if path != MANIFEST_RELATIVE_PATH)


def build_manifest() -> dict[str, object]:
    commit = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    parent_line = git("rev-list", "--parents", "-n", "1", "HEAD").split()
    parent = parent_line[1:] if len(parent_line) > 1 else []
    committed_at = git("show", "-s", "--format=%cI", "HEAD")
    files = []
    for relative in tracked_files():
        content = Path(relative).read_bytes()
        files.append({
            "path": relative,
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    return {
        "format": "HND-SHA256-MANIFEST-V1",
        "commit": commit,
        "tree": tree,
        "parents": parent,
        "committed_at": committed_at,
        "files": files,
    }


def verify_manifest(path: Path) -> bool:
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = build_manifest()
    return expected == actual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write manifest JSON to this path")
    parser.add_argument("--verify", type=Path, help="verify an existing manifest against this checkout")
    args = parser.parse_args()

    if args.verify:
        passed = verify_manifest(args.verify)
        print("MANIFEST_OK" if passed else "MANIFEST_MISMATCH")
        return 0 if passed else 1

    rendered = json.dumps(build_manifest(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"WROTE {args.output}")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
