"""Append-only experience intent, feedback, decisions, and timelines."""
from __future__ import annotations

import uuid

from .common import (
    AdapterError,
    EXPERIENCE_VERSION,
    RECORD_EVENT,
    RECORD_EXPERIENCE,
    actor_id,
    append_json,
    attribution,
    json_records,
    now_utc,
    paths_for_contract,
)
from .git_ops import is_ancestor, resolve_repo, run_git


def linked_experience(repo, paths, commit):
    linked = {
        event_id
        for _, event in json_records(paths["events"], RECORD_EVENT)
        for event_id in event.get("context", {}).get("experience_events", [])
    }
    out = []
    for _, event in json_records(
        paths["experience"], RECORD_EXPERIENCE, EXPERIENCE_VERSION
    ):
        if event["id"] in linked:
            continue
        base = event.get("links", {}).get("base_commit")
        if base and is_ancestor(repo, base, commit):
            out.append(event["id"])
    return sorted(out)


def record_experience(
    repo,
    contract,
    state_root,
    kind,
    statement,
    actor,
    authority,
    flow=None,
    actor_ref=None,
    task_ref=None,
    certainty="explicit",
    supersedes=None,
):
    repo = resolve_repo(repo)
    paths = paths_for_contract(repo, state_root, contract)
    if not statement.strip():
        raise AdapterError("experience statement must not be empty")
    if kind == "decision" and authority != "human":
        raise AdapterError("experience decisions require human authority")
    human_authored = kind in ("intent", "feedback", "decision")
    if certainty == "explicit" and authority != "human" and human_authored:
        raise AdapterError(f"explicit {kind} records require human authority")

    sha = run_git(repo, "rev-parse", "HEAD^{commit}").stdout.strip()
    event_id = str(uuid.uuid4())
    event = {
        "record": RECORD_EXPERIENCE,
        "schema_version": EXPERIENCE_VERSION,
        "id": event_id,
        "created_at": now_utc(),
        "project": (contract.get("project") or {}).get(
            "id", contract["repository"]["id"]
        ),
        "repository": contract["repository"]["id"],
        "kind": kind,
        "statement": statement,
        "certainty": certainty,
        "attribution": attribution(
            [
                {
                    "id": actor_ref or actor_id(authority, actor),
                    "kind": authority,
                    "display_name": actor,
                    "roles": ["author"],
                }
            ]
        ),
        "authority": authority,
        "links": {
            "base_commit": sha,
            "supersedes": list(supersedes or []),
        },
    }
    if flow:
        event["flow"] = flow
    if task_ref:
        event["source"] = {"kind": "codex-task", "reference": task_ref}
    name = f"{event['created_at'][:10]}--{event_id}.json"
    path = append_json(paths["experience"], name, event)
    return path, event


def experience_timeline(repo, contract, state_root, flow=None):
    repo = resolve_repo(repo)
    paths = paths_for_contract(repo, state_root, contract)
    events = [
        item
        for _, item in json_records(
            paths["experience"], RECORD_EXPERIENCE, EXPERIENCE_VERSION
        )
    ]
    superseded = {
        event_id
        for item in events
        for event_id in item.get("links", {}).get("supersedes", [])
    }
    if flow:
        events = [item for item in events if item.get("flow") == flow]
    return [
        {**item, "active": item["id"] not in superseded}
        for item in sorted(
            events, key=lambda item: (item["created_at"], item["id"])
        )
    ]
