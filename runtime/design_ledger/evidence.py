"""Commit ingestion, verification, evidence recording, and checkpoints."""
from __future__ import annotations

import fcntl
import hashlib
import uuid

from .common import (
    AdapterError,
    RECORD_EVENT,
    RECORD_RECEIPT,
    RISK_ORDER,
    SCHEMA_VERSION,
    actor_id,
    append_json,
    attribution,
    digest,
    json_records,
    matches,
    now_utc,
    paths_for_contract,
    validate_contract,
)
from .experience import linked_experience
from .git_ops import (
    changed_paths,
    coalesce,
    git_tree,
    input_digest,
    resolve_repo,
    run_command_check,
    run_git,
)


def ingest(repo, contract, state_root, commit="HEAD"):
    repo = resolve_repo(repo)
    paths = paths_for_contract(repo, state_root, contract)
    sha = run_git(repo, "rev-parse", f"{commit}^{{commit}}").stdout.strip()
    parents = run_git(repo, "show", "-s", "--format=%P", sha).stdout.strip().split()
    author_name = run_git(repo, "show", "-s", "--format=%an", sha).stdout.rstrip(
        "\n"
    )
    author_email = run_git(repo, "show", "-s", "--format=%ae", sha).stdout.rstrip(
        "\n"
    )
    committer_name = run_git(
        repo, "show", "-s", "--format=%cn", sha
    ).stdout.rstrip("\n")
    committer_email = run_git(
        repo, "show", "-s", "--format=%ce", sha
    ).stdout.rstrip("\n")
    committed_at = run_git(repo, "show", "-s", "--format=%cI", sha).stdout.strip()

    author = {
        "id": "git:sha256:" + hashlib.sha256(author_email.encode()).hexdigest(),
        "kind": "git-identity",
        "display_name": author_name,
        "roles": (
            ["author", "committer"]
            if author_email == committer_email
            else ["author"]
        ),
    }
    actors = [author]
    if author_email != committer_email:
        actors.append(
            {
                "id": "git:sha256:"
                + hashlib.sha256(committer_email.encode()).hexdigest(),
                "kind": "git-identity",
                "display_name": committer_name,
                "roles": ["committer"],
            }
        )

    event_id = str(uuid.uuid4())
    event = {
        "record": RECORD_EVENT,
        "schema_version": SCHEMA_VERSION,
        "id": event_id,
        "observed_at": now_utc(),
        "project": (contract.get("project") or {}).get(
            "id", contract["repository"]["id"]
        ),
        "repository": contract["repository"]["id"],
        "contract_digest": digest(contract),
        "contract": contract,
        "source": {
            "commit": sha,
            "parents": parents,
            "committed_at": committed_at,
            "attribution": attribution(actors),
        },
        "changes": changed_paths(repo, sha),
    }
    linked = linked_experience(repo, paths, sha)
    if linked:
        event["context"] = {"experience_events": linked}
    append_json(paths["events"], f"{sha}--{event_id}.json", event)
    return event


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
        default = contract.get(
            "default_rule", {"risk": "low", "invalidates": ["source"]}
        )
        rules.add("default")
        classes.update(default.get("invalidates", ["source"]))
        risk = default.get("risk", "low")
    if baseline:
        classes.update(
            item["proof_class"] for item in contract.get("checks", [])
        )
        rules.add("baseline")
    return {
        "risk": risk,
        "rules": sorted(rules),
        "invalidates": sorted(classes),
    }


def accepted_cache(receipts):
    superseded = {
        receipt_id
        for _, receipt in receipts
        for receipt_id in receipt.get("supersedes", [])
    }
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
        accepted = next(
            (
                (receipt, result)
                for receipt, result in entries
                if result.get("accepted")
                and result.get("status") in ("passed", "reused")
            ),
            None,
        )
        if accepted:
            receipt, result = accepted
            cache[key] = {"receipt": receipt["id"], "result": result}
    return cache


def proof_result(repo, commit, receipt_id, check, key, cache, paths):
    prior = cache.get((check["id"], key))
    if prior:
        return {
            "id": check["id"],
            "proof_class": check["proof_class"],
            "kind": check["kind"],
            "input_digest": key,
            "status": "reused",
            "accepted": True,
            "reused_from_receipt": prior["receipt"],
        }
    if check["kind"] != "command":
        reason = (
            "awaiting an attributed Codex result"
            if check["kind"] == "codex"
            else "awaiting an explicit human decision"
        )
        return {
            "id": check["id"],
            "proof_class": check["proof_class"],
            "kind": check["kind"],
            "input_digest": key,
            "status": "queued",
            "accepted": False,
            "reason": reason,
        }

    log_name = f"{receipt_id}--{check['id']}.log"
    code, error = run_command_check(
        repo, commit, check, paths["logs"] / log_name
    )
    passed = code == 0
    result = {
        "id": check["id"],
        "proof_class": check["proof_class"],
        "kind": "command",
        "input_digest": key,
        "status": "passed" if passed else "failed",
        "accepted": passed,
        "exit_code": code,
        "log": log_name,
        "attribution": attribution(
            [
                {
                    "id": "service:design-ledger-runtime",
                    "kind": "service",
                    "display_name": "Design Ledger runtime",
                    "roles": ["verifier"],
                }
            ]
        ),
        "authority": "automatic",
    }
    if error:
        result["reason"] = error
    return result


def receipt_summary(contract, changed, results, risk):
    gate = contract.get("landing_gate", "pre-push")
    required = {
        check["id"]
        for check in contract.get("checks", [])
        if gate in check.get("required_at", [])
    }
    relevant = {
        result["id"]: result for result in results if result["id"] in required
    }
    current = [
        check_id
        for check_id, result in relevant.items()
        if result["status"] in ("passed", "reused")
    ]
    failed = [
        check_id
        for check_id, result in relevant.items()
        if result["status"] == "failed"
    ]
    missing = sorted(required - set(current) - set(failed))
    if failed:
        state = "Blocked"
        next_action = f"Resolve failed evidence: {', '.join(failed)}"
    elif missing:
        state = "Blocked"
        next_action = f"Complete queued evidence: {', '.join(missing)}"
    else:
        state = "Ready"
        next_action = f"{gate} evidence is current."
    return {
        "state": state,
        "gate": gate,
        "risk": risk,
        "what_changed": changed,
        "current_evidence": current,
        "missing_evidence": missing + failed,
        "next_action": next_action,
    }


def _pending(paths, receipts):
    consumed = {
        event_id
        for _, receipt in receipts
        for event_id in receipt.get("source", {}).get("events", [])
    }
    return [
        entry
        for entry in json_records(paths["events"], RECORD_EVENT)
        if entry[1]["id"] not in consumed
    ]


def process(repo, contract, state_root):
    repo = resolve_repo(repo)
    paths = paths_for_contract(repo, state_root, contract)
    lock_path = paths["locks"] / "process.lock"
    receipts = json_records(paths["receipts"], RECORD_RECEIPT)
    if not _pending(paths, receipts):
        return []

    written = []
    with open(lock_path, "a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        receipts = json_records(paths["receipts"], RECORD_RECEIPT)
        events = _pending(paths, receipts)
        cache = accepted_cache(receipts)
        for commit, chain in coalesce(repo, events):
            target_events = [
                item for _, item in chain if item["source"]["commit"] == commit
            ]
            latest = max(target_events, key=lambda item: item["observed_at"])
            chain_contract = validate_contract(latest["contract"])
            changed = sorted(
                {
                    path
                    for _, item in chain
                    for path in item.get("changes", [])
                }
            )
            prior_digests = {
                receipt.get("contract_digest") for _, receipt in receipts
            }
            baseline = (
                not receipts or latest["contract_digest"] not in prior_digests
            )
            classification = classify(
                chain_contract, changed, baseline=baseline
            )
            receipt_id = str(uuid.uuid4())
            tree = git_tree(repo, commit)
            results = []
            for check in chain_contract.get("checks", []):
                key = input_digest(repo, commit, check, tree)
                cached = (check["id"], key) in cache
                invalidated = (
                    check["proof_class"] in classification["invalidates"]
                )
                if cached or invalidated:
                    results.append(
                        proof_result(
                            repo,
                            commit,
                            receipt_id,
                            check,
                            key,
                            cache,
                            paths,
                        )
                    )

            findings = []
            checks_by_id = {
                check["id"]: check for check in chain_contract["checks"]
            }
            for result in results:
                if result["status"] != "failed":
                    continue
                check = checks_by_id[result["id"]]
                findings.append(
                    {
                        "id": "check-" + result["id"],
                        "severity": check.get("failure_severity", "P1"),
                        "statement": (
                            f"Required check {result['id']} failed for commit "
                            f"{commit[:12]}."
                        ),
                        "proof_class": result["proof_class"],
                    }
                )

            receipt = {
                "record": RECORD_RECEIPT,
                "schema_version": SCHEMA_VERSION,
                "id": receipt_id,
                "created_at": now_utc(),
                "project": (chain_contract.get("project") or {}).get(
                    "id", chain_contract["repository"]["id"]
                ),
                "repository": chain_contract["repository"]["id"],
                "contract_digest": latest["contract_digest"],
                "source": {
                    "commit": commit,
                    "events": sorted(item["id"] for _, item in chain),
                    "experience_events": sorted(
                        {
                            event_id
                            for _, item in chain
                            for event_id in item.get("context", {}).get(
                                "experience_events", []
                            )
                        }
                    ),
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
            path = append_json(
                paths["receipts"], f"{commit}--{receipt_id}.json", receipt
            )
            written.append((path, receipt))
            receipts.append((path, receipt))
            cache.update(accepted_cache([(path, receipt)]))
    return written


def observe(repo, contract, state_root, commit="HEAD"):
    repo = resolve_repo(repo)
    paths = paths_for_contract(repo, state_root, contract)
    sha = run_git(repo, "rev-parse", f"{commit}^{{commit}}").stdout.strip()
    existing = list(paths["events"].glob(f"{sha}--*.json"))
    event = None if existing else ingest(repo, contract, state_root, sha)
    return event, process(repo, contract, state_root)


def record_evidence(
    repo,
    contract,
    state_root,
    commit,
    check_id,
    status,
    actor,
    authority,
    evidence,
    actor_ref=None,
    supersedes=None,
):
    repo = resolve_repo(repo)
    paths = paths_for_contract(repo, state_root, contract)
    sha = run_git(repo, "rev-parse", f"{commit}^{{commit}}").stdout.strip()
    check = next(
        (item for item in contract.get("checks", []) if item["id"] == check_id),
        None,
    )
    if not check:
        raise AdapterError(f"unknown check {check_id!r}")
    if status not in ("passed", "failed"):
        raise AdapterError("recorded evidence status must be passed or failed")
    if check["kind"] == "human" and authority != "human":
        raise AdapterError("human checks require --authority human")
    if check["kind"] == "codex" and authority != "agent":
        raise AdapterError("Codex checks require --authority agent")
    allowed = check.get("acceptance", {}).get(
        "authorities",
        ["human"] if check["kind"] == "human" else ["agent"],
    )
    if authority not in allowed:
        raise AdapterError(f"{check_id} does not accept {authority!r} authority")

    receipt_id = str(uuid.uuid4())
    key = input_digest(repo, sha, check)
    result = {
        "id": check_id,
        "proof_class": check["proof_class"],
        "kind": check["kind"],
        "input_digest": key,
        "status": status,
        "accepted": status == "passed",
        "evidence": evidence,
        "attribution": attribution(
            [
                {
                    "id": actor_ref or actor_id(authority, actor),
                    "kind": authority,
                    "display_name": actor,
                    "roles": ["reviewer"],
                }
            ]
        ),
        "authority": authority,
    }
    passed = status == "passed"
    receipt = {
        "record": RECORD_RECEIPT,
        "schema_version": SCHEMA_VERSION,
        "id": receipt_id,
        "created_at": now_utc(),
        "project": (contract.get("project") or {}).get(
            "id", contract["repository"]["id"]
        ),
        "repository": contract["repository"]["id"],
        "contract_digest": digest(contract),
        "source": {"commit": sha, "events": []},
        "supersedes": list(supersedes or []),
        "changes": [],
        "classification": {
            "risk": "low",
            "rules": ["evidence-record"],
            "invalidates": [],
        },
        "checks": [result],
        "findings": [],
        "summary": {
            "state": "Ready" if passed else "Blocked",
            "risk": "low",
            "what_changed": [],
            "current_evidence": [check_id] if passed else [],
            "missing_evidence": [] if passed else [check_id],
            "next_action": (
                "Re-evaluate the delivery checkpoint."
                if passed
                else f"Resolve {check_id}."
            ),
        },
    }
    path = append_json(
        paths["receipts"], f"{sha}--{receipt_id}.json", receipt
    )
    return path, receipt


def checkpoint(repo, contract, state_root, gate, commit="HEAD"):
    repo = resolve_repo(repo)
    paths = paths_for_contract(repo, state_root, contract)
    sha = run_git(repo, "rev-parse", f"{commit}^{{commit}}").stdout.strip()
    receipts = [
        item for _, item in json_records(paths["receipts"], RECORD_RECEIPT)
    ]
    current_receipts = [
        item
        for item in receipts
        if item.get("source", {}).get("commit") == sha
    ]
    analysis = [
        item for item in current_receipts if item.get("source", {}).get("events")
    ]
    if not analysis:
        return {
            "state": "Stale",
            "commit": sha,
            "gate": gate,
            "what_changed": [],
            "current_evidence": [],
            "missing_evidence": [],
            "next_action": "Ingest and process the current commit.",
        }, 3

    required = [
        item
        for item in contract.get("checks", [])
        if gate in item.get("required_at", [])
    ]
    superseded = {
        receipt_id
        for receipt in receipts
        for receipt_id in receipt.get("supersedes", [])
    }
    evidence = {}
    for receipt in receipts:
        if receipt.get("id") in superseded:
            continue
        for result in receipt.get("checks", []):
            key = (result.get("id"), result.get("input_digest"))
            evidence.setdefault(key, []).append(result)

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
        default_authority = (
            "automatic"
            if check["kind"] == "command"
            else check["kind"].replace("codex", "agent")
        )
        authorities = set(
            acceptance.get("authorities", [default_authority])
        )
        actor_ids = set()
        for result in results:
            if (
                not result.get("accepted")
                or result.get("status") not in ("passed", "reused")
                or result.get("status") == "reused"
                or result.get("authority") not in authorities
            ):
                continue
            primary = (result.get("attribution") or {}).get("primary_actor")
            actor_ids.add(primary or f"receipt-result:{id(result)}")
        if len(actor_ids) >= minimum:
            current.append(check["id"])
        else:
            missing.append(check["id"])

    changed = sorted(
        {
            path
            for item in analysis
            for path in item.get("changes", [])
        }
    )
    state = "Ready" if not missing and not failed else "Blocked"
    if failed:
        next_action = f"Resolve failed evidence: {', '.join(failed)}"
    elif missing:
        next_action = f"Complete required evidence: {', '.join(missing)}"
    else:
        next_action = f"{gate} evidence is current for {sha[:12]}."
    return {
        "state": state,
        "commit": sha,
        "gate": gate,
        "what_changed": changed,
        "current_evidence": current,
        "missing_evidence": missing + failed,
        "next_action": next_action,
    }, 0 if state == "Ready" else 2
