#!/usr/bin/env python3
"""Append-only Git/Codex evidence adapter for design-ledger v0.4.

Git commits are durable source events. ``ingest`` records one immutable event
and returns. ``process`` consumes pending linear commit chains, runs safe local
command checks in a temporary archive of the target commit, queues Codex and
human checks, and appends a source-bound receipt. ``checkpoint`` reports the
small landing state for a named delivery gate.

Operational events, logs, locks, and caches live under an explicit state root
outside the product repository. Python 3 standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import fnmatch
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile
import uuid


RECORD_EVENT = "design-ledger/commit-event"
RECORD_RECEIPT = "design-ledger/evidence-receipt"
SCHEMA_VERSION = "0.4"
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class AdapterError(RuntimeError):
    pass


def now_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


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


def run_git(repo, *args, check=True, text=True):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=text, check=False
    )
    if check and result.returncode:
        stderr = result.stderr.strip() if text else result.stderr.decode(errors="replace").strip()
        raise AdapterError(f"git {' '.join(args)} failed: {stderr}")
    return result


def resolve_repo(repo):
    root = run_git(repo, "rev-parse", "--show-toplevel").stdout.strip()
    return pathlib.Path(root).resolve()


def validate_contract(contract):
    errors = []
    if contract.get("adapter") != "design-ledger/git-codex":
        errors.append("adapter must be 'design-ledger/git-codex'")
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    repo_id = (contract.get("repository") or {}).get("id")
    if not isinstance(repo_id, str) or not repo_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in repo_id):
        errors.append("repository.id must be a non-empty portable slug")
    check_ids = set()
    for i, item in enumerate(contract.get("checks", [])):
        cid = item.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"checks[{i}].id is required")
        elif cid.lower() in check_ids:
            errors.append(f"checks[{i}].id duplicates {cid!r}")
        else:
            check_ids.add(cid.lower())
        if item.get("kind") not in ("command", "codex", "human"):
            errors.append(f"checks[{i}].kind must be command, codex, or human")
        if not isinstance(item.get("proof_class"), str):
            errors.append(f"checks[{i}].proof_class is required")
        if not isinstance(item.get("inputs"), list) or not item.get("inputs"):
            errors.append(f"checks[{i}].inputs must be a non-empty array")
        if item.get("kind") == "command":
            command = item.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
                errors.append(f"checks[{i}].command must be a non-empty argv array")
        acceptance = item.get("acceptance", {})
        if acceptance:
            minimum = acceptance.get("minimum", 1)
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
                errors.append(f"checks[{i}].acceptance.minimum must be a positive integer")
            authorities = acceptance.get("authorities", [])
            if not isinstance(authorities, list) or not authorities or not set(authorities) <= {"automatic", "agent", "human"}:
                errors.append(f"checks[{i}].acceptance.authorities must name automatic, agent, or human")
    for i, rule in enumerate(contract.get("risk_rules", [])):
        if rule.get("risk") not in RISK_ORDER:
            errors.append(f"risk_rules[{i}].risk must be low, medium, high, or critical")
        if not isinstance(rule.get("paths"), list) or not rule.get("paths"):
            errors.append(f"risk_rules[{i}].paths must be a non-empty array")
        if not isinstance(rule.get("invalidates"), list) or not rule.get("invalidates"):
            errors.append(f"risk_rules[{i}].invalidates must be a non-empty array")
    if errors:
        raise AdapterError("invalid adapter contract:\n  " + "\n  ".join(errors))
    return contract


def load_contract(path):
    return validate_contract(load_json(path))


def state_paths(repo, state_root, repo_id):
    repo = repo.resolve()
    root = pathlib.Path(state_root).expanduser().resolve()
    if root == repo or repo in root.parents:
        raise AdapterError("state root must be outside the product repository")
    base = root / "repositories" / repo_id
    paths = {
        "root": root,
        "base": base,
        "events": base / "events",
        "receipts": base / "receipts",
        "logs": base / "logs",
        "locks": base / "locks",
    }
    for key in ("events", "receipts", "logs", "locks"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


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


def changed_paths(repo, commit):
    output = run_git(
        repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit
    ).stdout
    return sorted({line for line in output.splitlines() if line})


def ingest(repo, contract, state_root, commit="HEAD"):
    repo = resolve_repo(repo)
    paths = state_paths(repo, state_root, contract["repository"]["id"])
    sha = run_git(repo, "rev-parse", f"{commit}^{{commit}}").stdout.strip()
    parents = run_git(repo, "show", "-s", "--format=%P", sha).stdout.strip().split()
    author_name = run_git(repo, "show", "-s", "--format=%an", sha).stdout.rstrip("\n")
    author_email = run_git(repo, "show", "-s", "--format=%ae", sha).stdout.rstrip("\n")
    committer_name = run_git(repo, "show", "-s", "--format=%cn", sha).stdout.rstrip("\n")
    committer_email = run_git(repo, "show", "-s", "--format=%ce", sha).stdout.rstrip("\n")
    committed_at = run_git(repo, "show", "-s", "--format=%cI", sha).stdout.strip()
    event_id = str(uuid.uuid4())
    event = {
        "record": RECORD_EVENT,
        "schema_version": SCHEMA_VERSION,
        "id": event_id,
        "observed_at": now_utc(),
        "repository": contract["repository"]["id"],
        "contract_digest": digest(contract),
        "contract": contract,
        "source": {
            "commit": sha,
            "parents": parents,
            "committed_at": committed_at,
            "attribution": attribution([
                {
                    "id": "git:sha256:" + hashlib.sha256(author_email.encode()).hexdigest(),
                    "kind": "git-identity", "display_name": author_name,
                    "roles": ["author", "committer"] if author_email == committer_email else ["author"],
                },
                *([] if author_email == committer_email else [{
                    "id": "git:sha256:" + hashlib.sha256(committer_email.encode()).hexdigest(),
                    "kind": "git-identity", "display_name": committer_name, "roles": ["committer"],
                }]),
            ]),
        },
        "changes": changed_paths(repo, sha),
    }
    filename = f"{sha}--{event_id}.json"
    append_json(paths["events"], filename, event)
    return event


def json_records(directory, record_type):
    records = []
    for path in sorted(directory.glob("*.json")):
        try:
            item = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if item.get("record") == record_type and item.get("schema_version") == SCHEMA_VERSION:
            records.append((path, item))
    return records


def is_ancestor(repo, older, newer):
    if older == newer:
        return True
    return run_git(repo, "merge-base", "--is-ancestor", older, newer, check=False).returncode == 0


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


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def classify(contract, changed, baseline=False):
    classes = set()
    rules = set()
    risk = "low"
    for rule in contract.get("risk_rules", []):
        if any(matches(path, rule["paths"]) for path in changed):
            rules.add(rule["id"])
            classes.update(rule["invalidates"])
            if RISK_ORDER[rule["risk"]] > RISK_ORDER[risk]:
                risk = rule["risk"]
    if not rules:
        default = contract.get("default_rule", {"risk": "low", "invalidates": ["source"]})
        rules.add("default")
        classes.update(default.get("invalidates", ["source"]))
        risk = default.get("risk", "low")
    if baseline:
        classes.update(item["proof_class"] for item in contract.get("checks", []))
        rules.add("baseline")
    return {"risk": risk, "rules": sorted(rules), "invalidates": sorted(classes)}


def git_tree(repo, commit):
    output = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", commit, text=False).stdout
    items = []
    for entry in output.split(b"\0"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, sha = meta.decode().split()
        items.append((raw_path.decode(errors="surrogateescape"), mode, kind, sha))
    return items


def input_digest(repo, commit, check, tree=None):
    tree = tree if tree is not None else git_tree(repo, commit)
    selected = [
        {"path": path, "mode": mode, "type": kind, "object": sha}
        for path, mode, kind, sha in tree
        if matches(path, check["inputs"])
    ]
    return digest({"check": check, "inputs": selected})


def accepted_cache(receipts):
    superseded = {rid for _, receipt in receipts for rid in receipt.get("supersedes", [])}
    grouped = {}
    for _, receipt in receipts:
        if receipt.get("id") in superseded:
            continue
        for result in receipt.get("checks", []):
            key = (result.get("id"), result.get("input_digest"))
            grouped.setdefault(key, []).append((receipt, result))
    cache = {}
    for key, entries in grouped.items():
        if any(result.get("status") == "failed" for _, result in entries):
            continue
        accepted = next(((receipt, result) for receipt, result in entries
                         if result.get("accepted") and result.get("status") in ("passed", "reused")), None)
        if accepted:
            receipt, result = accepted
            cache[key] = {"receipt": receipt["id"], "result": result}
    return cache


def archive_commit(repo, commit, destination):
    archive_path = destination.parent / (destination.name + ".tar")
    result = run_git(repo, "archive", "--format=tar", "-o", str(archive_path), commit, check=False)
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
                check["command"], cwd=checkout, env=env, capture_output=True,
                text=True, timeout=timeout, check=False
            )
            output = result.stdout + ("\n" if result.stdout and result.stderr else "") + result.stderr
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(output, encoding="utf-8")
            return result.returncode, None
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "")
            log_path.write_text(str(output) + f"\nTimed out after {timeout}s.\n", encoding="utf-8")
            return None, f"timed out after {timeout}s"


def proof_result(repo, commit, receipt_id, check, key, cache, paths):
    prior = cache.get((check["id"], key))
    if prior:
        return {
            "id": check["id"], "proof_class": check["proof_class"],
            "kind": check["kind"], "input_digest": key, "status": "reused",
            "accepted": True, "reused_from_receipt": prior["receipt"],
        }
    if check["kind"] != "command":
        return {
            "id": check["id"], "proof_class": check["proof_class"],
            "kind": check["kind"], "input_digest": key, "status": "queued",
            "accepted": False,
            "reason": "awaiting an attributed Codex result" if check["kind"] == "codex"
                      else "awaiting an explicit human decision",
        }
    log_name = f"{receipt_id}--{check['id']}.log"
    code, error = run_command_check(repo, commit, check, paths["logs"] / log_name)
    passed = code == 0
    return {
        "id": check["id"], "proof_class": check["proof_class"],
        "kind": "command", "input_digest": key,
        "status": "passed" if passed else "failed", "accepted": passed,
        "exit_code": code, "log": log_name,
        "attribution": attribution([{
            "id": "service:design-ledger-runtime", "kind": "service",
            "display_name": "Design Ledger runtime", "roles": ["verifier"],
        }]),
        "authority": "automatic",
        **({"reason": error} if error else {}),
    }


def receipt_summary(contract, changed, results, risk):
    gate = contract.get("landing_gate", "pre-push")
    required = {
        check["id"] for check in contract.get("checks", [])
        if gate in check.get("required_at", [])
    }
    relevant = {result["id"]: result for result in results if result["id"] in required}
    current = [cid for cid, result in relevant.items() if result["status"] in ("passed", "reused")]
    failed = [cid for cid, result in relevant.items() if result["status"] == "failed"]
    missing = sorted(required - set(current) - set(failed))
    if failed or missing:
        state = "Blocked"
        next_action = (
            f"Resolve failed evidence: {', '.join(failed)}" if failed
            else f"Complete queued evidence: {', '.join(missing)}"
        )
    else:
        state = "Ready"
        next_action = "Continue development; enforce required evidence at the next delivery checkpoint."
    return {
        "state": state,
        "gate": gate,
        "risk": risk,
        "what_changed": changed,
        "current_evidence": current,
        "missing_evidence": missing + failed,
        "next_action": next_action if state == "Blocked" else f"{gate} evidence is current.",
    }


def process(repo, contract, state_root):
    repo = resolve_repo(repo)
    paths = state_paths(repo, state_root, contract["repository"]["id"])
    lock_path = paths["locks"] / "process.lock"
    receipts = json_records(paths["receipts"], RECORD_RECEIPT)
    consumed = {
        event_id
        for _, receipt in receipts
        for event_id in receipt.get("source", {}).get("events", [])
    }
    events = [entry for entry in json_records(paths["events"], RECORD_EVENT) if entry[1]["id"] not in consumed]
    if not events:
        return []
    written = []
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        receipts = json_records(paths["receipts"], RECORD_RECEIPT)
        consumed = {
            event_id for _, receipt in receipts
            for event_id in receipt.get("source", {}).get("events", [])
        }
        events = [entry for entry in json_records(paths["events"], RECORD_EVENT) if entry[1]["id"] not in consumed]
        cache = accepted_cache(receipts)
        for commit, chain in coalesce(repo, events):
            target_events = [
                item for _, item in chain if item["source"]["commit"] == commit
            ]
            latest = max(target_events, key=lambda item: item["observed_at"])
            chain_contract = validate_contract(latest["contract"])
            changed = sorted({path for _, item in chain for path in item.get("changes", [])})
            prior_digests = {r.get("contract_digest") for _, r in receipts}
            baseline = not receipts or latest["contract_digest"] not in prior_digests
            classification = classify(chain_contract, changed, baseline=baseline)
            receipt_id = str(uuid.uuid4())
            tree = git_tree(repo, commit)
            results = []
            for check in chain_contract.get("checks", []):
                key = input_digest(repo, commit, check, tree)
                cached = (check["id"], key) in cache
                invalidated = check["proof_class"] in classification["invalidates"]
                if cached or invalidated:
                    results.append(proof_result(repo, commit, receipt_id, check, key, cache, paths))
            findings = []
            for result in results:
                if result["status"] == "failed":
                    check = next(c for c in chain_contract["checks"] if c["id"] == result["id"])
                    findings.append({
                        "id": "check-" + result["id"],
                        "severity": check.get("failure_severity", "P1"),
                        "statement": f"Required check {result['id']} failed for commit {commit[:12]}.",
                        "proof_class": result["proof_class"],
                    })
            receipt = {
                "record": RECORD_RECEIPT,
                "schema_version": SCHEMA_VERSION,
                "id": receipt_id,
                "created_at": now_utc(),
                "repository": chain_contract["repository"]["id"],
                "contract_digest": latest["contract_digest"],
                "source": {
                    "commit": commit,
                    "events": sorted(item["id"] for _, item in chain),
                    "attribution": latest["source"]["attribution"],
                },
                "changes": changed,
                "classification": classification,
                "checks": results,
                "findings": findings,
            }
            receipt["summary"] = receipt_summary(
                chain_contract, changed, results, classification["risk"]
            )
            name = f"{commit}--{receipt_id}.json"
            path = append_json(paths["receipts"], name, receipt)
            written.append((path, receipt))
            receipts.append((path, receipt))
            cache.update(accepted_cache([(path, receipt)]))
    return written


def record_evidence(repo, contract, state_root, commit, check_id, status, actor, authority, evidence,
                    actor_ref=None, supersedes=None):
    repo = resolve_repo(repo)
    paths = state_paths(repo, state_root, contract["repository"]["id"])
    sha = run_git(repo, "rev-parse", f"{commit}^{{commit}}").stdout.strip()
    check = next((item for item in contract.get("checks", []) if item["id"] == check_id), None)
    if not check:
        raise AdapterError(f"unknown check {check_id!r}")
    if status not in ("passed", "failed"):
        raise AdapterError("recorded evidence status must be passed or failed")
    if check["kind"] == "human" and authority != "human":
        raise AdapterError("human checks require --authority human")
    if check["kind"] == "codex" and authority != "agent":
        raise AdapterError("Codex checks require --authority agent")
    allowed = check.get("acceptance", {}).get(
        "authorities", ["human"] if check["kind"] == "human" else ["agent"]
    )
    if authority not in allowed:
        raise AdapterError(f"{check_id} does not accept {authority!r} authority")
    receipt_id = str(uuid.uuid4())
    key = input_digest(repo, sha, check)
    result = {
        "id": check_id, "proof_class": check["proof_class"], "kind": check["kind"],
        "input_digest": key, "status": status, "accepted": status == "passed",
        "evidence": evidence,
        "attribution": attribution([{
            "id": actor_ref or actor_id(authority, actor),
            "kind": authority, "display_name": actor, "roles": ["reviewer"],
        }]),
        "authority": authority,
    }
    receipt = {
        "record": RECORD_RECEIPT, "schema_version": SCHEMA_VERSION,
        "id": receipt_id, "created_at": now_utc(),
        "repository": contract["repository"]["id"],
        "contract_digest": digest(contract),
        "source": {"commit": sha, "events": []},
        "supersedes": list(supersedes or []),
        "changes": [], "classification": {"risk": "low", "rules": ["evidence-record"], "invalidates": []},
        "checks": [result], "findings": [],
        "summary": {
            "state": "Ready" if status == "passed" else "Blocked", "risk": "low",
            "what_changed": [], "current_evidence": [check_id] if status == "passed" else [],
            "missing_evidence": [] if status == "passed" else [check_id],
            "next_action": "Re-evaluate the delivery checkpoint." if status == "passed" else f"Resolve {check_id}.",
        },
    }
    path = append_json(paths["receipts"], f"{sha}--{receipt_id}.json", receipt)
    return path, receipt


def checkpoint(repo, contract, state_root, gate, commit="HEAD"):
    repo = resolve_repo(repo)
    paths = state_paths(repo, state_root, contract["repository"]["id"])
    sha = run_git(repo, "rev-parse", f"{commit}^{{commit}}").stdout.strip()
    receipts = [item for _, item in json_records(paths["receipts"], RECORD_RECEIPT)]
    current_receipts = [
        item for item in receipts if item.get("source", {}).get("commit") == sha
    ]
    analysis = [item for item in current_receipts if item.get("source", {}).get("events")]
    if not analysis:
        return {
            "state": "Stale", "commit": sha, "gate": gate,
            "what_changed": [], "current_evidence": [], "missing_evidence": [],
            "next_action": "Ingest and process the current commit.",
        }, 3
    required = [item for item in contract.get("checks", []) if gate in item.get("required_at", [])]
    superseded = {rid for receipt in receipts for rid in receipt.get("supersedes", [])}
    evidence = {}
    for receipt in receipts:
        if receipt.get("id") in superseded:
            continue
        for result in receipt.get("checks", []):
            evidence.setdefault((result.get("id"), result.get("input_digest")), []).append(result)
    current = []
    missing = []
    failed = []
    for check in required:
        key = input_digest(repo, sha, check)
        results = evidence.get((check["id"], key), [])
        if any(result.get("status") == "failed" for result in results):
            failed.append(check["id"])
            continue
        acceptance = check.get("acceptance", {})
        minimum = acceptance.get("minimum", 1)
        default_authority = "automatic" if check["kind"] == "command" else check["kind"].replace("codex", "agent")
        authorities = set(acceptance.get("authorities", [default_authority]))
        actor_ids = set()
        for result in results:
            if not result.get("accepted") or result.get("status") not in ("passed", "reused"):
                continue
            if result.get("status") == "reused":
                continue
            if result.get("authority") not in authorities:
                continue
            primary = (result.get("attribution") or {}).get("primary_actor")
            actor_ids.add(primary or f"receipt-result:{id(result)}")
        if len(actor_ids) >= minimum:
            current.append(check["id"])
        else:
            missing.append(check["id"])
    changed = sorted({path for item in analysis for path in item.get("changes", [])})
    state = "Ready" if not missing and not failed else "Blocked"
    next_action = (
        f"Resolve failed evidence: {', '.join(failed)}" if failed else
        f"Complete required evidence: {', '.join(missing)}" if missing else
        f"{gate} evidence is current for {sha[:12]}."
    )
    return {
        "state": state, "commit": sha, "gate": gate,
        "what_changed": changed, "current_evidence": current,
        "missing_evidence": missing + failed, "next_action": next_action,
    }, 0 if state == "Ready" else 2


def hook_script(runtime_path, adapter_path, state_root):
    args = [
        sys.executable, str(pathlib.Path(runtime_path).resolve()), "ingest",
        "--repo", "$(git rev-parse --show-toplevel)",
        "--adapter", str(pathlib.Path(adapter_path).resolve()),
        "--state-root", str(pathlib.Path(state_root).expanduser().resolve()),
        "--commit", "HEAD",
    ]
    # The generated hook uses no shell interpolation except the repository query.
    quoted = " ".join("'" + value.replace("'", "'\\''") + "'" for value in args)
    quoted = quoted.replace("'$(git rev-parse --show-toplevel)'", '"$(git rev-parse --show-toplevel)"')
    return "#!/bin/sh\n" + quoted + " >/dev/null 2>&1 &\nexit 0\n"


def parser():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", required=True)
    common.add_argument("--adapter", required=True)
    common.add_argument("--state-root", required=True)
    ingest_p = sub.add_parser("ingest", parents=[common])
    ingest_p.add_argument("--commit", default="HEAD")
    sub.add_parser("process", parents=[common])
    checkpoint_p = sub.add_parser("checkpoint", parents=[common])
    checkpoint_p.add_argument("--gate", required=True)
    checkpoint_p.add_argument("--commit", default="HEAD")
    record_p = sub.add_parser("record", parents=[common])
    record_p.add_argument("--commit", default="HEAD")
    record_p.add_argument("--check", required=True)
    record_p.add_argument("--status", choices=("passed", "failed"), required=True)
    record_p.add_argument("--actor", required=True)
    record_p.add_argument("--actor-id")
    record_p.add_argument("--authority", choices=("agent", "human"), required=True)
    record_p.add_argument("--evidence", required=True)
    record_p.add_argument("--supersedes", action="append", default=[])
    hook_p = sub.add_parser("print-hook")
    hook_p.add_argument("--adapter", required=True)
    hook_p.add_argument("--state-root", required=True)
    return ap


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "print-hook":
            print(hook_script(__file__, args.adapter, args.state_root), end="")
            return 0
        contract = load_contract(args.adapter)
        if args.command == "ingest":
            event = ingest(args.repo, contract, args.state_root, args.commit)
            print(json.dumps({"event": event["id"], "commit": event["source"]["commit"]}))
            return 0
        if args.command == "process":
            written = process(args.repo, contract, args.state_root)
            print(json.dumps({"receipts": [receipt["id"] for _, receipt in written]}))
            return 0
        if args.command == "record":
            _, receipt = record_evidence(
                args.repo, contract, args.state_root, args.commit, args.check,
                args.status, args.actor, args.authority, args.evidence,
                args.actor_id, args.supersedes
            )
            print(json.dumps({"receipt": receipt["id"], "commit": receipt["source"]["commit"]}))
            return 0
        result, code = checkpoint(args.repo, contract, args.state_root, args.gate, args.commit)
        print(json.dumps(result, indent=2))
        return code
    except AdapterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
