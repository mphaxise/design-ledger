# Hey Minie iOS adoption plan

## Claim

Hey Minie iOS needs one bounded onboarding pass before Design Ledger can operate automatically. The pass should reuse existing checks and evidence, establish a truthful baseline, and leave every release decision with its current human owner.

This document is a handoff plan. No Hey Minie repository state has been changed by this Design Ledger increment.

## One-time onboarding

1. Verify the live Hey Minie repository root, branch, HEAD, upstream, worktrees, instructions, ownership declarations, and dirty state.
2. Inventory existing build, test, Simulator, physical-device, accessibility, privacy, analytics, TestFlight, and release evidence. Reuse authoritative checks and identify gaps without creating duplicate workflows.
3. Create the project contract with one stable project ID and a repository source ID. Map actual paths only after the live source tree is inspected.
4. Define proof classes for source correctness, UI behavior, motion, audio, auth and lifecycle, naming and maps, accessibility, privacy-sensitive analytics, documentation, and release readiness.
5. Seed the experience timeline from current product flows and explicit decisions whose provenance is available. Historical claims without source evidence remain unknown.
6. Run a baseline against one exact commit. Record unavailable device, account, backend, production-log, TestFlight, or human-decision evidence as missing.
7. Enable ambient commit observation after the baseline receipt validates.

## Automatic operation after onboarding

The user continues working in the regular Hey Minie development task. Codex records explicit experience feedback as compact events. Each local commit triggers background classification and the checks invalidated by its changed paths. Accepted evidence with identical inputs is reused.

Ordinary commits continue without waiting. Pre-push, PR readiness, TestFlight, merge, and release checkpoints evaluate the evidence required for that exact commit.

## Evidence distinctions

The adapter must keep these claims separate:

- Source inspection
- Deterministic tests
- Successful build
- Simulator runtime behavior
- Archive validity
- TestFlight state
- Signed-device installation
- Physical interaction, motion, and audio behavior
- Production logs or backend state
- Explicit human approval

Evidence in one class never proves another class.

## Admission test

Automatic use begins after the onboarding pass proves:

- Two rapid commits coalesce without losing either event.
- A change invalidates only its declared proof classes.
- Unchanged content reuses accepted evidence.
- A failed critical check blocks its dependent delivery checkpoint.
- A human gate cannot be satisfied by agent authority.
- A design-feedback event links to the implementing commit and remains queryable by flow.
- Raw logs and local state remain outside the Hey Minie working tree.

## Authority boundary

Design Ledger may observe, classify, verify, queue, and report. It does not push, open a PR, merge, install on a device, upload to TestFlight, release, change backend state, or answer a human gate without separate authorization.
