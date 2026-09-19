#!/usr/bin/env python3
"""Stable CLI and import shim for the modular Design Ledger runtime."""
from design_ledger import *  # noqa: F401,F403
from design_ledger.cli import hook_script, main, parser


if __name__ == "__main__":
    raise SystemExit(main())
