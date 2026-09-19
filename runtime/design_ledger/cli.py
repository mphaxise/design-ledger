"""Stable command-line interface for the Design Ledger runtime."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .common import AdapterError, load_contract
from .evidence import (
    checkpoint,
    ingest,
    observe,
    process,
    record_evidence,
)
from .experience import experience_timeline, record_experience


def hook_script(runtime_path, adapter_path, state_root):
    args = [
        sys.executable,
        str(pathlib.Path(runtime_path).resolve()),
        "ingest",
        "--repo",
        "$(git rev-parse --show-toplevel)",
        "--adapter",
        str(pathlib.Path(adapter_path).resolve()),
        "--state-root",
        str(pathlib.Path(state_root).expanduser().resolve()),
        "--commit",
        "HEAD",
    ]
    quoted = " ".join(
        "'" + value.replace("'", "'\\''") + "'" for value in args
    )
    quoted = quoted.replace(
        "'$(git rev-parse --show-toplevel)'",
        '"$(git rev-parse --show-toplevel)"',
    )
    return "#!/bin/sh\n" + quoted + " >/dev/null 2>&1 &\nexit 0\n"


def parser():
    ap = argparse.ArgumentParser(
        description="Append-only Git/Codex evidence adapter for Design Ledger."
    )
    sub = ap.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", required=True)
    common.add_argument("--adapter", required=True)
    common.add_argument("--state-root", required=True)

    ingest_p = sub.add_parser("ingest", parents=[common])
    ingest_p.add_argument("--commit", default="HEAD")
    observe_p = sub.add_parser("observe", parents=[common])
    observe_p.add_argument("--commit", default="HEAD")
    sub.add_parser("process", parents=[common])
    checkpoint_p = sub.add_parser("checkpoint", parents=[common])
    checkpoint_p.add_argument("--gate", required=True)
    checkpoint_p.add_argument("--commit", default="HEAD")

    record_p = sub.add_parser("record", parents=[common])
    record_p.add_argument("--commit", default="HEAD")
    record_p.add_argument("--check", required=True)
    record_p.add_argument(
        "--status", choices=("passed", "failed"), required=True
    )
    record_p.add_argument("--actor", required=True)
    record_p.add_argument("--actor-id")
    record_p.add_argument(
        "--authority", choices=("agent", "human"), required=True
    )
    record_p.add_argument("--evidence", required=True)
    record_p.add_argument("--supersedes", action="append", default=[])

    note_p = sub.add_parser("note", parents=[common])
    note_p.add_argument(
        "--kind",
        choices=(
            "intent",
            "feedback",
            "flow-observation",
            "decision",
            "question",
        ),
        required=True,
    )
    note_p.add_argument("--statement", required=True)
    note_p.add_argument("--flow")
    note_p.add_argument("--actor", required=True)
    note_p.add_argument("--actor-id")
    note_p.add_argument(
        "--authority", choices=("agent", "human"), required=True
    )
    note_p.add_argument(
        "--certainty", choices=("explicit", "derived"), default="explicit"
    )
    note_p.add_argument("--task-ref")
    note_p.add_argument("--supersedes", action="append", default=[])

    timeline_p = sub.add_parser("experience", parents=[common])
    timeline_p.add_argument("--flow")
    hook_p = sub.add_parser("print-hook")
    hook_p.add_argument("--adapter", required=True)
    hook_p.add_argument("--state-root", required=True)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "print-hook":
            wrapper = pathlib.Path(__file__).resolve().parents[1] / "git_codex_adapter.py"
            print(hook_script(wrapper, args.adapter, args.state_root), end="")
            return 0
        contract = load_contract(args.adapter)
        if args.command == "ingest":
            event = ingest(args.repo, contract, args.state_root, args.commit)
            print(
                json.dumps(
                    {"event": event["id"], "commit": event["source"]["commit"]}
                )
            )
            return 0
        if args.command == "observe":
            event, written = observe(
                args.repo, contract, args.state_root, args.commit
            )
            print(
                json.dumps(
                    {
                        "event": event["id"] if event else None,
                        "receipts": [
                            receipt["id"] for _, receipt in written
                        ],
                    }
                )
            )
            return 0
        if args.command == "process":
            written = process(args.repo, contract, args.state_root)
            print(
                json.dumps(
                    {
                        "receipts": [
                            receipt["id"] for _, receipt in written
                        ]
                    }
                )
            )
            return 0
        if args.command == "record":
            _, receipt = record_evidence(
                args.repo,
                contract,
                args.state_root,
                args.commit,
                args.check,
                args.status,
                args.actor,
                args.authority,
                args.evidence,
                args.actor_id,
                args.supersedes,
            )
            print(
                json.dumps(
                    {
                        "receipt": receipt["id"],
                        "commit": receipt["source"]["commit"],
                    }
                )
            )
            return 0
        if args.command == "note":
            _, event = record_experience(
                args.repo,
                contract,
                args.state_root,
                args.kind,
                args.statement,
                args.actor,
                args.authority,
                args.flow,
                args.actor_id,
                args.task_ref,
                args.certainty,
                args.supersedes,
            )
            print(
                json.dumps(
                    {
                        "experience_event": event["id"],
                        "base_commit": event["links"]["base_commit"],
                    }
                )
            )
            return 0
        if args.command == "experience":
            print(
                json.dumps(
                    experience_timeline(
                        args.repo, contract, args.state_root, args.flow
                    ),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        result, code = checkpoint(
            args.repo, contract, args.state_root, args.gate, args.commit
        )
        print(json.dumps(result, indent=2))
        return code
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
