# Design Ledger product model v0.5

## Claim

Design Ledger is ambient infrastructure inside Codex for durable product development. The user works in the regular development task. Design Ledger captures compact experience intent, observes commits, coordinates evidence, and reports readiness at delivery checkpoints.

## Activation boundary

Design Ledger activates when work modifies a maintained repository, creates reusable or shippable output, may span commits or sessions, produces claims that need verification, or includes a human decision.

A scratch experiment stays outside the ledger only when every condition holds:

- The work is explicitly disposable.
- It runs in an isolated scratch location.
- It creates no durable commit or maintained artifact.
- Its output will not support a product decision or evidence claim.
- It completes without follow-up development.

An experiment enters the ledger before further development when someone reuses, commits, shares, or cites it. Ambiguous development defaults to ledgered work. Read-only conversation remains outside.

## Inputs

Design Ledger consumes five source types:

1. A durable change event, usually a Git commit.
2. A project contract defining source structure, risk classes, checks, and gates.
3. Machine evidence from builds, tests, schemas, static analysis, and runtime checks.
4. Agent evidence from code, design, accessibility, security, or experience review.
5. Explicit human intent, feedback, decisions, and approvals.

Accepted evidence can be reused when its declared content inputs have the same digest. Raw conversation, private context, and hidden reasoning are excluded.

## Interaction model

Design feedback enters through the regular development task. Codex records a compact experience event when the user states an intent, feedback item, question, decision, or observed flow change that should survive the task.

Three records remain distinct:

- **Experience intent:** the behavior a human wants.
- **Implemented experience:** behavior supported by a commit and its evidence.
- **Decision and evidence:** why the implementation changed and how it was checked.

The distinction prevents a requested experience from being reported as implemented before source-bound evidence exists.

## Local storage

Design Ledger owns a stable project structure outside product repositories:

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
  cache/
```

A logical project can contain several repositories and worktrees. Git commit IDs bind evidence to source. Product repositories carry a small `.design-ledger/adapter.json` contract and any receipts explicitly selected for promotion.

## Collaboration model

Every human, agent instance, Git identity, and service has a stable actor ID. An event can name several participants and one primary producer. Delegation, authority, and identity remain separate.

Evidence policies can require distinct actors, eligible authorities, or quorum. Active disagreement blocks the affected checkpoint. Resolution appends a new receipt that explicitly supersedes the conflicting receipt. Ordering by timestamp never resolves a conflict.

One human can operate several agents. Each agent remains independently attributable, even when all act for the same human principal.

## Quality scope

Design Ledger coordinates evidence across four domains:

- **Experience health:** flows, interaction behavior, accessibility, content, and design fidelity.
- **Code health:** correctness, readability, architecture, maintainability, security, and performance.
- **Delivery readiness:** required evidence for pre-push, PR readiness, TestFlight, merge, and release.
- **Decisions:** human gates, conflicts, exceptions, and their provenance.

Tools and reviewers produce the evidence. Design Ledger stores its source, scope, date, and acceptance state. The control panel presents Ready, Blocked, or Stale with the current evidence, missing evidence, and one next action. It does not collapse distinct claims into a synthetic quality score.

## Automation and authority

The Codex plugin activates implicitly for durable work. Adapter-enabled repositories are observed asynchronously after shell commands. A new commit is ingested once and verified in the background.

Automatic behavior includes commit observation, change classification, evidence reuse, deterministic checks, queued reviews, and checkpoint summaries. Human decisions, permission changes, push, PR creation, merge, deployment, TestFlight, and release remain explicit actions.

## Current implementation boundary

The v0.5 structure implements project-scoped state, multi-actor evidence, explicit conflict supersession, experience events, flow queries, an implicitly discoverable Codex skill, and an asynchronous repository-observation hook.

Automatic onboarding for an unknown repository still requires a one-time contract pass. That pass maps the repository's real structure and existing checks before a checkpoint can be trusted.
