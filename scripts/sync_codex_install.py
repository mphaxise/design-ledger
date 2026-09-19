#!/usr/bin/env python3
"""Synchronize and verify the local Codex installation from this checkout."""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
SOURCE_RUNTIME = REPO / "runtime"
SOURCE_PLUGIN = REPO / "plugins" / "design-ledger"


def _copytree(source, destination):
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def sync(runtime_home, plugin_home):
    runtime_home.mkdir(parents=True, exist_ok=True)
    plugin_home.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_RUNTIME / "git_codex_adapter.py", runtime_home)
    _copytree(SOURCE_RUNTIME / "design_ledger", runtime_home / "design_ledger")
    _copytree(SOURCE_PLUGIN, plugin_home)


def _files(root):
    return sorted(
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and path.name != ".DS_Store"
    )


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_tree(source, destination):
    errors = []
    for relative in _files(source):
        installed = destination / relative
        if not installed.is_file():
            errors.append(f"missing {installed}")
        elif _sha(source / relative) != _sha(installed):
            errors.append(f"content differs: {installed}")
    return errors


def verify(runtime_home, plugin_home):
    errors = []
    wrapper = SOURCE_RUNTIME / "git_codex_adapter.py"
    installed_wrapper = runtime_home / "git_codex_adapter.py"
    if not installed_wrapper.is_file():
        errors.append(f"missing {installed_wrapper}")
    elif _sha(wrapper) != _sha(installed_wrapper):
        errors.append(f"content differs: {installed_wrapper}")
    errors.extend(
        verify_tree(
            SOURCE_RUNTIME / "design_ledger", runtime_home / "design_ledger"
        )
    )
    errors.extend(verify_tree(SOURCE_PLUGIN, plugin_home))
    return errors


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("sync", "verify"))
    ap.add_argument(
        "--runtime-home",
        default=str(pathlib.Path.home() / ".codex" / "design-ledger" / "bin"),
    )
    ap.add_argument(
        "--plugin-home",
        default=str(pathlib.Path.home() / "plugins" / "design-ledger"),
    )
    ap.add_argument(
        "--install",
        action="store_true",
        help="Reinstall design-ledger@personal after a successful sync.",
    )
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    runtime_home = pathlib.Path(args.runtime_home).expanduser().resolve()
    plugin_home = pathlib.Path(args.plugin_home).expanduser().resolve()
    if args.mode == "sync":
        sync(runtime_home, plugin_home)
    errors = verify(runtime_home, plugin_home)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    print(f"OK runtime {runtime_home}")
    print(f"OK plugin {plugin_home}")
    if args.install:
        result = subprocess.run(
            ["codex", "plugin", "add", "design-ledger@personal"],
            check=False,
        )
        return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
