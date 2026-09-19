# Git/Codex development adapter v0.4

## Contract

A Git commit is the durable coordination event. The post-commit hook appends a small event and exits. A separate local worker coalesces pending commit chains, classifies changed paths, reuses accepted evidence with identical declared inputs, runs safe command checks, queues Codex or human checks, and appends a source-bound receipt.

The adapter has no OpenDesign dependency. The OpenDesign integration remains prior evidence and an optional adapter.

Codex sessions consume queued checks. Commit creation never starts a Codex session. Ordinary local commits do not wait for the ledger.

## Portable contract

Each product repository supplies a versioned adapter file matching `schema/git-adapter.schema.json`. `adapters/git-codex/v0.4/example-adapter.json` shows the complete shape.

Risk rules map changed paths to proof classes. Checks declare their inputs, executor, and delivery gates:

- `command` checks run against a temporary `git archive` of the exact commit.
- `codex` checks remain queued until an attributed agent result is recorded.
- `human` checks remain queued until a named human explicitly records a decision.

`landing_gate` selects the checkpoint summarized by each receipt and defaults to `pre-push`. Checks required only at later gates stay visible in the detailed receipt without making an ordinary local commit look blocked.

The runtime refuses to store operational state inside the product repository.

## Local runtime boundary

The state root contains append-only source events and receipts, plus raw logs and a processing lock:

```text
<state-root>/repositories/<repository-id>/
  events/<commit>--<event-uuid>.json
  receipts/<commit>--<receipt-uuid>.json
  logs/<receipt-uuid>--<check-id>.log
  locks/process.lock
```

Every event and receipt is atomically published under a unique name. Processing records consumed event IDs in a receipt and leaves the source events intact. A crash can therefore be retried without reconstructing lost testimony. Concurrent ingestion never writes a shared current file.

Attribution names every participating actor and identifies the primary producer. Check acceptance can require a minimum number of distinct actors by authority. Concurrent disagreements remain active conflicts; a later receipt must explicitly supersede the conflicting receipt before the checkpoint can pass.

The schemas for the portable objects are:

- `schema/commit-event.schema.json`
- `schema/evidence-receipt.schema.json`

Raw events, logs, caches, repository paths, and private context stay in the external state root. A compact receipt can be promoted into a product repository through a separate explicit review action. The runtime never promotes one automatically.

## Hook and worker

Generate a non-blocking post-commit hook from the runtime:

```sh
python3 /path/to/design-ledger/runtime/git_codex_adapter.py print-hook \
  --adapter /path/to/product/.design-ledger/adapter.json \
  --state-root "$XDG_STATE_HOME/design-ledger"
```

The generated hook backgrounds `ingest`, suppresses its output, and returns immediately. A local scheduler or long-lived development task calls the worker independently:

```sh
python3 /path/to/design-ledger/runtime/git_codex_adapter.py process \
  --repo /path/to/product \
  --adapter /path/to/product/.design-ledger/adapter.json \
  --state-root "$XDG_STATE_HOME/design-ledger"
```

The worker uses an exclusive local processing lock. It can run repeatedly; a call with no pending events is a no-op.

## Codex and human results

A Codex consumer checks out the receipt's exact source commit, performs the queued check, and appends its attributed result:

```sh
python3 /path/to/design-ledger/runtime/git_codex_adapter.py record \
  --repo /path/to/product \
  --adapter /path/to/product/.design-ledger/adapter.json \
  --state-root "$XDG_STATE_HOME/design-ledger" \
  --check ui-review --status passed \
  --authority agent --actor codex \
  --evidence 'runtime review receipt reference'
```

Human checks require `--authority human`. The runtime rejects an agent-authority result for a human check. It records the supplied attribution and never selects an answer.

## Checkpoints and landing state

`checkpoint` evaluates current evidence for one named delivery gate:

```sh
python3 /path/to/design-ledger/runtime/git_codex_adapter.py checkpoint \
  --repo /path/to/product \
  --adapter /path/to/product/.design-ledger/adapter.json \
  --state-root "$XDG_STATE_HOME/design-ledger" \
  --gate pre-push
```

Exit codes are `0` for Ready, `2` for Blocked, and `3` for Stale. The JSON response contains only the landing view: state, changed paths, current evidence, missing evidence, and one next action. Receipts and raw logs hold the detail one level deeper.

Pre-push, PR readiness, TestFlight, merge, and release tooling may enforce this command. Local commit creation does not.

## Safety boundary

The runtime reads Git objects, writes only below the external state root, and runs declared command checks in a temporary archive. It never amends commits, rewrites source, installs hooks, pushes, uploads, merges, releases, or answers a human gate. Hook installation, receipt promotion, and every delivery action remain explicit owner decisions.

## Hey Minie integration handoff

Hey Minie integration is a separate repository-owned change. Its minimum handoff is:

1. Add `.design-ledger/adapter.json` using schema version `0.4`.
2. Map UI, auth/lifecycle, naming/maps, docs, and release paths to their proof classes.
3. Declare existing build and test commands as `command` checks.
4. Declare runtime UI and device review as `codex` checks with exact source inputs.
5. Declare TestFlight, merge, and release approvals as `human` checks.
6. Install the generated post-commit hook locally and schedule `process` outside the repository.
7. Prove one rapid two-commit chain, one content-addressed reuse, one failed required check, and one explicit human gate before enabling a blocking delivery checkpoint.

That integration must preserve Hey Minie's repository instructions, device-evidence distinctions, and release authority. This repository does not choose its commands, paths, or gate answers.

## Validation

Run the deterministic suite from this repository root:

```sh
python3 -m unittest discover -s tests -v
```

The suite covers concurrent ingestion, rapid-chain coalescing, selective invalidation, content-addressed reuse, external state enforcement, schema/example loading, and explicit human evidence.

## Self-hosting

This repository uses `.design-ledger/adapter.json` as its own product contract. Its pre-push landing gate requires the deterministic adapter suite. Codex review of the adapter, documentation, and Evidence Board remains queued for PR readiness when those proof classes change. Release approval stays human-owned.

The self-hosting receipt remains in the external state root. Recording or promoting that receipt is a separate explicit action, so verification cannot create a recursive commit chain.
