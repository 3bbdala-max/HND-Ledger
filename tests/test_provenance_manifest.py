import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "create_provenance_manifest.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True
    ).strip()


@pytest.fixture
def clean_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "HND test")
    git(repo, "config", "user.email", "hnd-test@example.invalid")
    (repo / "tracked.txt").write_bytes(b"committed bytes\n")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", "fixture")
    return repo


def run_manifest(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_manifest_hashes_committed_git_blob(clean_repo):
    result = run_manifest(clean_repo)
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    entry = next(item for item in manifest["files"] if item["path"] == "tracked.txt")
    assert entry["sha256"] == hashlib.sha256(b"committed bytes\n").hexdigest()
    assert entry["size"] == len(b"committed bytes\n")
    assert entry["type"] == "blob"
    assert entry["git_object"] == git(clean_repo, "rev-parse", "HEAD:tracked.txt")


def test_dirty_tracked_file_is_rejected(clean_repo):
    (clean_repo / "tracked.txt").write_bytes(b"modified local bytes\n")
    result = run_manifest(clean_repo)
    assert result.returncode == 2
    assert "tracked files differ from HEAD" in result.stderr


def test_untracked_file_is_rejected(clean_repo):
    (clean_repo / "extra.txt").write_text("not committed", encoding="utf-8")
    result = run_manifest(clean_repo)
    assert result.returncode == 2
    assert "untracked files are present" in result.stderr


def test_manifest_can_be_written_and_verified(clean_repo):
    evidence = clean_repo / "evidence"
    evidence.mkdir()
    manifest_path = evidence / "SHA256-MANIFEST.json"
    written = run_manifest(clean_repo, "--output", "evidence/SHA256-MANIFEST.json")
    assert written.returncode == 0, written.stderr
    verified = run_manifest(clean_repo, "--verify", "evidence/SHA256-MANIFEST.json")
    assert verified.returncode == 0
    assert verified.stdout.strip() == "MANIFEST_OK"


def test_staged_change_is_rejected(clean_repo):
    (clean_repo / "tracked.txt").write_text("staged change\n", encoding="utf-8")
    git(clean_repo, "add", "tracked.txt")
    result = run_manifest(clean_repo)
    assert result.returncode == 2
    assert "tracked files differ from HEAD" in result.stderr


def test_manifest_path_inside_repo_is_fixed(clean_repo):
    result = run_manifest(clean_repo, "--output", "other-manifest.json")
    assert result.returncode == 2
    assert "must use evidence/SHA256-MANIFEST.json" in result.stderr


def test_manifest_mismatch_is_reported_after_tampering(clean_repo):
    evidence = clean_repo / "evidence"
    evidence.mkdir()
    manifest_path = evidence / "SHA256-MANIFEST.json"
    written = run_manifest(clean_repo, "--output", "evidence/SHA256-MANIFEST.json")
    assert written.returncode == 0, written.stderr

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tree"] = "0" * len(manifest["tree"])
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    verified = run_manifest(clean_repo, "--verify", "evidence/SHA256-MANIFEST.json")
    assert verified.returncode == 1
    assert verified.stdout.strip() == "MANIFEST_MISMATCH"
