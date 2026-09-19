---
name: design-ledger
description: Activate and operate Design Ledger for durable Codex development. Use when work modifies a maintained repository, creates reusable or shippable code, spans commits or sessions, produces evidence claims, or includes experience decisions. Skip read-only conversation and explicitly disposable one-session scratch experiments.
---

# Design Ledger

Design Ledger is the ambient evidence layer for durable development. Keep the user's regular Codex task as the primary workspace.

## Activation boundary

Treat work as durable when it modifies a maintained product or repository, may be reused or shipped, spans commits or agents, creates claims that need verification, or includes a human decision. A scratch experiment stays outside only when it is isolated, disposable, uncommitted, unused as evidence, and complete within the current session. Ambiguous development defaults to durable.

For durable work:

1. Resolve the Git root and read repository instructions.
2. Look for `.design-ledger/adapter.json`.
3. If the adapter is absent, perform one-time onboarding inside the current development task: inspect existing checks and project structure, create the smallest accurate contract, and run a baseline before relying on any checkpoint.
4. Preserve repository ownership, dirty work, and human gates. Design Ledger does not authorize commit, push, PR, merge, deployment, TestFlight, or release actions.

## Experience capture

Design feedback stays in the regular development conversation. Record a compact experience event when the user explicitly states an intent, feedback item, decision, question, or flow observation that should survive the task.

Use the installed runtime at `~/.codex/design-ledger/bin/git_codex_adapter.py` with the project adapter and state root `~/.codex/design-ledger/state`. Store the concise statement, flow name when known, actor attribution, and authority. Keep raw chat, hidden reasoning, credentials, and unrelated personal context out of the ledger.

Human intent, feedback, and decisions require human authority. Agent-derived observations use `certainty=derived`. Never promote an ambiguous statement into a human decision.

## Commit verification

The plugin hook observes adapter-enabled repositories after Codex shell commands. A new commit is ingested once, processed asynchronously, and bound to any pending experience events. Ordinary local development continues.

If the hook is unavailable, call `observe` directly after a local commit. Use `checkpoint` before a delivery action. A Ready result applies only to the named commit and gate.

## Collaboration

Keep each human, agent instance, and service as a distinct actor. Record delegation separately from identity. Active conflicting evidence blocks its affected checkpoint until an append-only receipt explicitly supersedes the conflict. Human checks accept only eligible human authority.

## Output boundary

Raw events, logs, caches, and private context remain in the local Design Ledger home. Product repositories carry compact adapter contracts and explicitly promoted receipts only.
