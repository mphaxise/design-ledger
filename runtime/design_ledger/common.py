"""Shared records, validation, attribution, and append-only storage."""
from __future__ import annotations

import datetime as dt
import fnmatch
import hashlib
import json
import os
import pathlib
import uuid


RECORD_EVENT = "design-ledger/commit-event"
RECORD_RECEIPT = "design-ledger/evidence-receipt"
RECORD_EXPERIENCE = "design-ledger/experience-event"
SCHEMA_VERSION = "0.4"
EXPERIENCE_VERSION = "0.5"
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
PORTABLE_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)


class AdapterError(RuntimeError):
    pass


def now_utc():
    return (
        dt.datetime.now(dt.timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def digest(value):
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def actor_id(kind, name):
    token = hashlib.sha256(f"{kind}\0{name}".encode()).hexdigest()
    return f"{kind}:sha256:{token}"


def attribution(actor_specs):
    actors = []
    for spec in actor_specs:
        item = dict(spec)
        item.setdefault("id", actor_id(item["kind"], item["display_name"]))
        actors.append(item)
    return {"primary_actor": actors[0]["id"], "actors": actors}


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _portable_id(value):
    return (
        isinstance(value, str)
        and bool(value)
        and all(char in PORTABLE_ID_CHARS for char in value)
    )


def validate_contract(contract):
    errors = []
    if contract.get("adapter") != "design-ledger/git-codex":
        errors.append("adapter must be 'design-ledger/git-codex'")
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    repo_id = (contract.get("repository") or {}).get("id")
    if not _portable_id(repo_id):
        errors.append("repository.id must be a non-empty portable slug")
    project_id = (contract.get("project") or {}).get("id", repo_id)
    if not _portable_id(project_id):
        errors.append("project.id must be a non-empty portable slug")

    check_ids = set()
    for index, item in enumerate(contract.get("checks", [])):
        check_id = item.get("id")
        if not isinstance(check_id, str) or not check_id:
            errors.append(f"checks[{index}].id is required")
        elif check_id.lower() in check_ids:
            errors.append(f"checks[{index}].id duplicates {check_id!r}")
        else:
            check_ids.add(check_id.lower())
        if item.get("kind") not in ("command", "codex", "human"):
            errors.append(f"checks[{index}].kind must be command, codex, or human")
        if not isinstance(item.get("proof_class"), str):
            errors.append(f"checks[{index}].proof_class is required")
        if not isinstance(item.get("inputs"), list) or not item.get("inputs"):
            errors.append(f"checks[{index}].inputs must be a non-empty array")
        if item.get("kind") == "command":
            command = item.get("command")
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(arg, str) and arg for arg in command)
            ):
                errors.append(
                    f"checks[{index}].command must be a non-empty argv array"
                )
        acceptance = item.get("acceptance", {})
        if acceptance:
            minimum = acceptance.get("minimum", 1)
            if (
                not isinstance(minimum, int)
                or isinstance(minimum, bool)
                or minimum < 1
            ):
                errors.append(
                    f"checks[{index}].acceptance.minimum must be a positive integer"
                )
            authorities = acceptance.get("authorities", [])
            allowed = {"automatic", "agent", "human"}
            if (
                not isinstance(authorities, list)
                or not authorities
                or not set(authorities) <= allowed
            ):
                errors.append(
                    f"checks[{index}].acceptance.authorities must name "
                    "automatic, agent, or human"
                )

    for index, rule in enumerate(contract.get("risk_rules", [])):
        if rule.get("risk") not in RISK_ORDER:
            errors.append(
                f"risk_rules[{index}].risk must be low, medium, high, or critical"
            )
        if not isinstance(rule.get("paths"), list) or not rule.get("paths"):
            errors.append(f"risk_rules[{index}].paths must be a non-empty array")
        if (
            not isinstance(rule.get("invalidates"), list)
            or not rule.get("invalidates")
        ):
            errors.append(
                f"risk_rules[{index}].invalidates must be a non-empty array"
            )
    if errors:
        raise AdapterError("invalid adapter contract:\n  " + "\n  ".join(errors))
    return contract


def load_contract(path):
    return validate_contract(load_json(path))


def state_paths(repo, state_root, repo_id, project_id=None):
    repo = repo.resolve()
    root = pathlib.Path(state_root).expanduser().resolve()
    if root == repo or repo in root.parents:
        raise AdapterError("state root must be outside the product repository")
    project_id = project_id or repo_id
    project = root / "projects" / project_id
    base = project / "sources" / repo_id
    paths = {
        "root": root,
        "project": project,
        "base": base,
        "experience": project / "experience",
        "events": base / "events",
        "receipts": base / "receipts",
        "logs": base / "logs",
        "locks": base / "locks",
    }
    for key in ("experience", "events", "receipts", "logs", "locks"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def paths_for_contract(repo, state_root, contract):
    repo_id = contract["repository"]["id"]
    project_id = (contract.get("project") or {}).get("id", repo_id)
    return state_paths(repo, state_root, repo_id, project_id)


def append_json(directory, filename, value):
    """Publish a new JSON object atomically without replacing an existing one."""
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / filename
    tmp = directory / (".tmp-" + uuid.uuid4().hex)
    payload = json.dumps(value, indent=2, ensure_ascii=False).encode() + b"\n"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(tmp, final)
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return final


def json_records(directory, record_type, schema_version=SCHEMA_VERSION):
    records = []
    for path in sorted(directory.glob("*.json")):
        try:
            item = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if (
            item.get("record") == record_type
            and item.get("schema_version") == schema_version
        ):
            records.append((path, item))
    return records


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
