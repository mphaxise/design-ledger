# Write path v0.2

Answering a gate happens on the board. The board records the Decision as a file a human owns, posts the continuation to the substrate, and harvests the resumed run's manifest when it lands. Manifests stay immutable: a human's answer is never written into a run's testimony.

`board/serve.py` implements the path. `docs/run-manifest.md` open question 3 is resolved by this document: decisions live as sibling records, and a resumed run's own manifest re-records the decision it received; the board dedupes.

## What resume actually is (measured 2026-09-01)

Three probe exchanges against the live daemon established the mechanics, and they correct an assumption the genesis record invited:

1. `POST /api/chat` with only `projectId` starts a fresh agent with no memory of the conversation. Each project has exactly one conversation (verified in the daemon's store), but posting into the project does not replay it.
2. Posting with the correct `conversationId` still reports `no_recoverable_session` / `captured_not_resumed`: a fresh agent session.
3. The genesis resumption of 2026-08-31 ran the same way — its log carries the same fresh-session diagnostics. The "resumed" run was a new agent that received the answer in its message and the prior run's files in its workspace, and re-derived the rest.

So resume is a fresh agent reading the workspace. The gated run's manifest is the memory. That has two design consequences: the continuation message must carry the decision explicitly, and the predecessor manifest must be archived, never overwritten — the emission contract's archive rule exists for this.

## Decision records

`board/decisions/<run-id>--<gate-id>.json`, written by `serve.py` when a human submits an answer:

```json
{
  "record": "design-ledger/decision-record",
  "schema_version": "0.1",
  "run": "research-brief-lumen-2026-09-01",
  "gate": "gate-uncertainty-scope-posture",
  "answer": "Option A — confidence, narrow scope",
  "answers": { "scope_bet": "confidence_narrow" },
  "by": "Praneet",
  "at": "2026-09-02",
  "via": "evidence-board",
  "channel": "board",
  "continuation": {
    "project": "proj-emission-test-2026-09-01-brief",
    "conversation": "2c82fb22-…",
    "posted_at": "2026-09-02T09:14:03",
    "state": "posted"
  }
}
```

The record is authoritative for who answered, what, and when. The `continuation` block is operational provenance: whether the answer reached the substrate, not whether it is valid. A decision record is written even when the continuation fails; blocked work becoming unblocked must not depend on a daemon being up.

`schema/validate.py` validates decision records alongside manifests (it dispatches on the `record` marker).

## Board rendering

`extract.py` takes `--decisions-dir`. Gate state resolves in order: a manifest that records the gate `answered` wins; otherwise a decision record for that run and gate marks it answered with the record's fields and provenance `board`; otherwise the gate is open. When a resumed run's manifest later re-records the same decision, the two agree or the board shows the disagreement in the honesty section rather than hiding it.

`build_board.py` renders an answer form on every open gate, built from the gate's own emitted questions: radio, checkbox, and textarea inputs, a name field, and a submit that posts to `/decide`. On a static file open the forms are inert with a one-line instruction to serve the board; over `serve.py` they are live.

## The serve loop

```
python3 board/serve.py --manifests-dir schema/examples --decisions-dir board/decisions \
  --logs-dir <dir-for-continuation-logs> --port 7461
```

`POST /decide` validates the submission against the loaded manifests (the gate must exist and be open), writes the decision record, resolves the continuation target, posts `POST /api/chat` with `agentId`, `projectId`, `conversationId`, the run's `skillId`, `sessionMode: design`, and a message carrying the decision, then streams the SSE to a log file in `--logs-dir`. When the run terminates, `serve.py` validates and harvests the new `run-manifest.json` from the workspace into `--manifests-dir` with a `run.log` join hint, and regenerates the board.

Continuation targeting: the manifest's optional `run.project` names the substrate project (the emission contract asks runs to record it). The conversation id comes from the daemon's local SQLite store, read-only, because no HTTP endpoint exposes the project-to-conversation mapping — a seam request for upstream, recorded here so the dependency is explicit. If either lookup fails, the decision record is written with `continuation.state: "not-posted"` and the message to send by hand.

## What this does not do

- No authentication: the server binds loopback and trusts the machine, like the daemon it fronts.
- No editing or reversal of decision records from the UI. A wrong answer is corrected by a new record; history stays.
- No answering on anyone's behalf: the form's name field defaults to nothing and the record stores what was typed. The agent side of this project never submits the form.
