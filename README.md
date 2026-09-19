# design-ledger

Design Ledger is a local-first evidence and experience layer for durable product development with Codex. It observes Git commits, classifies changed paths, runs or queues the required checks, preserves human decisions, and reports readiness at delivery checkpoints.

The regular development task remains the working surface. Design Ledger runs in the background and keeps the evidence.

## Current architecture

A local commit is the durable coordination event. The Codex plugin observes adapter-enabled repositories after shell commands and invokes the runtime asynchronously. The runtime:

- Appends a uniquely named commit event.
- Coalesces rapid linear commit chains.
- Invalidates only the proof classes affected by changed paths.
- Reuses accepted evidence when declared inputs have the same content digest.
- Runs deterministic command checks from an archive of the exact commit.
- Queues attributed Codex reviews and human gates.
- Emits an immutable, source-bound receipt.

Ordinary commits continue without waiting. Pre-push, PR readiness, TestFlight, merge, and release tooling can enforce evidence for their exact checkpoint.

## Experience history

Design feedback stays in the regular development conversation. Codex can record explicit intent, feedback, questions, flow observations, and decisions as compact experience events. The next implementing commit links those events to source and verification evidence.

Human intent and decisions require human authority. Agent-derived observations retain agent attribution and an explicit evidence grade.

## Collaboration

Humans, agent instances, Git identities, and services remain distinct actors. Evidence policies can require eligible roles, distinct actors, or quorum. Concurrent disagreement stays visible until a later receipt explicitly supersedes the conflict.

## Repository contract

Each maintained repository supplies `.design-ledger/adapter.json`. The contract declares:

- Logical project and repository IDs.
- Path-based risk and invalidation rules.
- Command, Codex, and human checks.
- Evidence required at each delivery checkpoint.

See [the Git/Codex adapter contract](docs/git-codex-adapter.md) and [the product model](docs/product-model-v0.5.md).

## Local state

Raw events, experience history, receipts, logs, locks, and caches stay outside product repositories:

```text
<design-ledger-home>/
  projects/
    <project-id>/
      experience/
      sources/
        <repository-id>/
          events/
          receipts/
          logs/
          locks/
```

Product repositories carry their compact adapter contract and any receipts selected for explicit promotion.

## Validation

The runtime uses Python 3 standard library modules. Run the deterministic suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

The suite covers concurrent ingestion, commit coalescing, selective invalidation, evidence reuse, multi-agent conflict handling, human authority, experience history, plugin observation, and local installation synchronization.

## Installation

The local Codex plugin lives under `plugins/design-ledger/`. See [Codex installation](docs/codex-installation.md) for the trust and onboarding boundaries. Existing local installations update through:

```sh
python3 scripts/sync_codex_install.py sync --install
```

The command synchronizes the modular runtime and plugin source, verifies file identity, and reinstalls `design-ledger@personal`.

## Evidence status

- v0.1 OpenDesign reference integration shipped on 2026-09-01.
- v0.4 Git/Codex asynchronous verification passed its dated fixture suite on 2026-09-19.
- v0.5 ambient Codex, collaboration, and experience-history behavior passed its dated fixture suite and self-hosted checkpoints on 2026-09-19.
- Hey Minie iOS completed its onboarding baseline at commit `dcfa9310` with a Ready onboarding checkpoint on 2026-09-19.

The dated session records live under `board/facts/`. `ROADMAP.md` separates implemented work, active consolidation, and planned control-panel work.

## Historical OpenDesign reference

The original Evidence Board, OpenDesign manifest schema, genesis examples, and write-path experiment remain in `board/`, `schema/examples/`, `docs/run-manifest.md`, and `docs/write-path.md`. They preserve the evidence behind the v0.1 claims while the current board migrates to project events and receipts.

## License

Apache-2.0.
