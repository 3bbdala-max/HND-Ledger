#!/usr/bin/env python3
"""Create or verify a deterministic SHA-256 manifest for a committed Git tree.

The manifest is derived from Git objects, never from mutable working-tree bytes.
Verification also requires a clean checkout, except for the manifest itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

MANIFEST_RELATIVE_PATH = "evidence/SHA256-MANIFEST.json"
FORMAT = "HND-SHA256-MANIFEST-V2"


class ManifestError(RuntimeError):
    """The Git checkout cannot be represented or verified safely."""


def git_bytes(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError("git " + " ".join(args) + " failed: " + detail)
    return result.stdout


def git_text(*args: str) -> str:
    return git_bytes(*args).decode("utf-8").strip()


def manifest_repo_path(path: Path | None) -> str | None:
    if path is None:
        return None
    root = Path(git_text("rev-parse", "--show-toplevel")).resolve()
    candidate = path.resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        return None
    if relative != MANIFEST_RELATIVE_PATH:
        raise ManifestError(
            "a manifest stored inside the repository must use "
            + MANIFEST_RELATIVE_PATH
        )
    return relative


def ensure_clean_checkout() -> None:
    exclusion = ":(exclude)" + MANIFEST_RELATIVE_PATH
    result = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", ".", exclusion],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 1:
        raise ManifestError(
            "tracked files differ from HEAD; use a clean checkout before "
            "creating or verifying the manifest"
        )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError("could not verify tracked checkout state: " + detail)

    untracked = git_bytes("ls-files", "--others", "--exclude-standard", "-z")
    paths = [
        item.decode("utf-8", errors="strict")
        for item in untracked.split(b"\x00")
        if item
    ]
    unexpected = [path for path in paths if path != MANIFEST_RELATIVE_PATH]
    if unexpected:
        raise ManifestError(
            "untracked files are present: " + ", ".join(sorted(unexpected))
        )


def committed_files() -> list[dict[str, object]]:
    raw = git_bytes("ls-tree", "-r", "-z", "--full-tree", "HEAD")
    entries: list[dict[str, object]] = []
    for record in raw.split(b"\x00"):
        if not record:
            continue
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            mode_bytes, type_bytes, object_bytes = metadata.split(b" ", 2)
            path = path_bytes.decode("utf-8", errors="strict")
            mode = mode_bytes.decode("ascii")
            object_type = type_bytes.decode("ascii")
            object_id = object_bytes.decode("ascii")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ManifestError("Git tree contains an unsupported path or entry") from exc

        if path == MANIFEST_RELATIVE_PATH:
            continue

        if object_type == "blob":
            content = git_bytes("cat-file", "blob", object_id)
            entries.append({
                "path": path,
                "mode": mode,
                "type": "blob",
                "git_object": object_id,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        elif mode == "160000" and object_type == "commit":
            entries.append({
                "path": path,
                "mode": mode,
                "type": "gitlink",
                "git_object": object_id,
                "size": None,
                "sha256": None,
            })
        else:
            raise ManifestError(
                "unsupported Git tree entry at " + path + ": " + object_type
            )

    return sorted(entries, key=lambda item: str(item["path"]))


def build_manifest() -> dict[str, object]:
    ensure_clean_checkout()
    commit = git_text("rev-parse", "HEAD")
    tree = git_text("rev-parse", "HEAD^{tree}")
    parent_line = git_text("rev-list", "--parents", "-n", "1", "HEAD").split()
    parents = parent_line[1:] if len(parent_line) > 1 else []
    committed_at = git_text("show", "-s", "--format=%cI", "HEAD")
    object_format = git_text("rev-parse", "--show-object-format")
    return {
        "format": FORMAT,
        "object_format": object_format,
        "commit": commit,
        "tree": tree,
        "parents": parents,
        "committed_at": committed_at,
        "files": committed_files(),
    }


def verify_manifest(path: Path) -> bool:
    expected = json.loads(path.read_text(encoding="utf-8"))
    return expected == build_manifest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write manifest JSON to this path")
    parser.add_argument("--verify", type=Path, help="verify an existing manifest against this checkout")
    args = parser.parse_args()

    if args.output and args.verify:
        parser.error("--output and --verify cannot be used together")

    try:
        selected_path = args.output or args.verify
        manifest_repo_path(selected_path)
        if args.verify:
            passed = verify_manifest(args.verify)
            print("MANIFEST_OK" if passed else "MANIFEST_MISMATCH")
            return 0 if passed else 1

        rendered = json.dumps(build_manifest(), indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
            print("WROTE " + str(args.output))
        else:
            sys.stdout.write(rendered)
        return 0
    except (ManifestError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("MANIFEST_ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
