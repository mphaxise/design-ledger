#!/usr/bin/env python3
"""Asynchronously observe the current adapter-enabled repository."""
import json
import os
import pathlib
import subprocess
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    cwd = pathlib.Path(payload.get("cwd") or os.getcwd())
    root_result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False,
    )
    if root_result.returncode:
        return 0
    repo = pathlib.Path(root_result.stdout.strip())
    contract = repo / ".design-ledger" / "adapter.json"
    if not contract.is_file():
        return 0
    runtime = pathlib.Path(os.environ.get(
        "DESIGN_LEDGER_RUNTIME",
        pathlib.Path.home() / ".codex" / "design-ledger" / "bin" / "git_codex_adapter.py",
    ))
    state_root = pathlib.Path(os.environ.get(
        "DESIGN_LEDGER_STATE_ROOT",
        pathlib.Path.home() / ".codex" / "design-ledger" / "state",
    ))
    if not runtime.is_file():
        return 0
    subprocess.run(
        [sys.executable, str(runtime), "observe", "--repo", str(repo),
         "--adapter", str(contract), "--state-root", str(state_root)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
