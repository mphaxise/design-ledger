"""Read-only Git operations and isolated command-check execution."""
from __future__ import annotations

import os
import pathlib
import subprocess
import tarfile
import tempfile

from .common import AdapterError, digest, matches


def run_git(repo, *args, check=True, text=True):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=text,
        check=False,
    )
    if check and result.returncode:
        stderr = (
            result.stderr.strip()
            if text
            else result.stderr.decode(errors="replace").strip()
        )
        raise AdapterError(f"git {' '.join(args)} failed: {stderr}")
    return result


def resolve_repo(repo):
    root = run_git(repo, "rev-parse", "--show-toplevel").stdout.strip()
    return pathlib.Path(root).resolve()


def changed_paths(repo, commit):
    output = run_git(
        repo,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        commit,
    ).stdout
    return sorted({line for line in output.splitlines() if line})


def is_ancestor(repo, older, newer):
    if older == newer:
        return True
    return (
        run_git(
            repo, "merge-base", "--is-ancestor", older, newer, check=False
        ).returncode
        == 0
    )


def coalesce(repo, pending):
    """Return maximal ancestry-compatible chains, preserving every event id."""
    groups = []
    remaining = list(pending)
    while remaining:
        chain = [remaining.pop(0)]
        target = chain[0][1]["source"]["commit"]
        keep = []
        for entry in remaining:
            commit = entry[1]["source"]["commit"]
            if is_ancestor(repo, target, commit):
                chain.append(entry)
                target = commit
            elif is_ancestor(repo, commit, target):
                chain.append(entry)
            else:
                keep.append(entry)
        groups.append((target, chain))
        remaining = keep
    return groups


def git_tree(repo, commit):
    output = run_git(
        repo, "ls-tree", "-r", "-z", "--full-tree", commit, text=False
    ).stdout
    items = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        items.append(
            (raw_path.decode(errors="surrogateescape"), mode, kind, sha)
        )
    return items


def input_digest(repo, commit, check, tree=None):
    tree = tree if tree is not None else git_tree(repo, commit)
    selected = [
        {"path": path, "mode": mode, "type": kind, "object": sha}
        for path, mode, kind, sha in tree
        if matches(path, check["inputs"])
    ]
    return digest({"check": check, "inputs": selected})


def archive_commit(repo, commit, destination):
    archive_path = destination.parent / (destination.name + ".tar")
    result = run_git(
        repo,
        "archive",
        "--format=tar",
        "-o",
        str(archive_path),
        commit,
        check=False,
    )
    if result.returncode:
        raise AdapterError(f"git archive failed: {result.stderr.strip()}")
    destination.mkdir()
    with tarfile.open(archive_path) as archive:
        root = destination.resolve()
        for member in archive.getmembers():
            resolved = (destination / member.name).resolve()
            if root != resolved and root not in resolved.parents:
                raise AdapterError(f"unsafe archive member: {member.name}")
        archive.extractall(destination, filter="data")
    archive_path.unlink()


def run_command_check(repo, commit, check, log_path):
    timeout = int(check.get("timeout_seconds", 900))
    with tempfile.TemporaryDirectory(prefix="design-ledger-check-") as tmp:
        checkout = pathlib.Path(tmp) / "source"
        archive_commit(repo, commit, checkout)
        env = os.environ.copy()
        env["DESIGN_LEDGER_COMMIT"] = commit
        try:
            result = subprocess.run(
                check["command"],
                cwd=checkout,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            separator = "\n" if result.stdout and result.stderr else ""
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                result.stdout + separator + result.stderr, encoding="utf-8"
            )
            return result.returncode, None
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            log_path.write_text(
                str(output) + f"\nTimed out after {timeout}s.\n",
                encoding="utf-8",
            )
            return None, f"timed out after {timeout}s"
