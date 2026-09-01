# Run manifest v0.1

A run finishes by writing `run-manifest.json`: its structured account of the findings, assumptions, gates, decisions, recommendations, and artifacts it produced. The board reads manifests directly. Facts files, the session-recorded stopgap from v0, retire once the board consumes manifests and the six genesis runs are backfilled.

`schema/run-manifest.schema.json` is normative for shapes and enums. This document records the design decisions behind it. Every enum in the schema comes from what the six runs of 2026-08-31 actually emitted; the session record for those runs is the evidence base for this design.

## Every field has one authority

The manifest is the run's own account, and the design trusts it exactly that far.

Objects and their content belong to the run. Findings, assumptions, gates, recommendations, and artifact listings are what the run claims it produced. `run.provenance` says whether the run wrote the manifest itself (`emitted`) or someone reconstructed it later from session records (`backfilled`); the board labels backfilled data as such.

Execution measurements belong to the substrate. Cost, token counts, wall time, and exit codes come from the daemon API and the SSE logs. The manifest omits these fields by design: a run reporting its own cost asserts a number it cannot know. The board joins substrate measurements to a manifest through `run.session_id` or `run.id`.

Gate answers belong to humans. A `decision` records who answered (`by`), what (`answer`), when (`at`), and through which surface (`via`, `channel`). A run records only decisions it actually received. `contract.declared_by` keeps the same line for self-checks: `run` marks the run's own testimony, `session-record` marks checks a person made afterward.

## Objects

**Run** carries identity, substrate, mode, `date`, and `status`. Status has three values. `completed` means the deliverable exists and every blocking gate is answered. `gated` means the run stopped at a blocking gate and withheld the deliverable. `failed` means the run ended without meeting its contract. The date field is required: a claim without a date is unusable under this project's evidence rule.

**Artifact** paths are workspace-relative. The validator rejects absolute paths, home paths, and parent traversal, because manifests travel and machine paths must stay on the machine.

**Finding** requires `statement` and `severity` (`P0` to `P3`). The basis enum `reported | derived | unverified` is the evidence-basis column the design-qa run emitted on 2026-08-31, lowercased. Basis is optional because the ux-review run, same day, emitted findings with fixes and rationale and no basis column; a backfill omits what the run did not label rather than inventing a grade.

**Assumption** requires a `statement` and offers `basis` (what the assumption leans on), `impact_if_wrong`, and a lifecycle `status` (`open | tested | confirmed | refuted`). The shape follows the assumption entries the research-brief run wrote, which pair each assumed number with why it was assumed and how the result should be read if the assumption breaks.

**Gate** and its `questions` mirror the question-form structure OpenDesign rendered: ids, labels, typed inputs, options with values and descriptions, defaults. The genesis runs showed two gate patterns, and `blocking` separates them. A blocking gate withholds the deliverable until answered: the research-brief run held at one. A checkpoint gate rides with a delivered artifact and blocks the next decision instead: the design-qa and ux-review runs completed their deliverables with checkpoint gates open. `blocking` defaults to true, so an unmarked open gate reads as stopped work. A gate is `open` or `answered`, and an answered gate names its `decision`.

**Decision** requires `id`, `gate`, `answer`, `by`, and `at`. `answers` maps question ids to values when they were captured; the recorded genesis decision captured one of three question answers, and the example manifest lists exactly that one.

**Recommendation** is a standing call to a human: text, state (`awaiting-decision | accepted | declined | superseded`), and the artifact it comes from.

**limits** is the successor of the facts files' honesty notes: a list of what this run could not see, verify, or emit. The examples use it for partial backfills and for the substrate-measured stats the manifest deliberately excludes.

**tags** on findings, assumptions, and recommendations carry a run's own vocabulary verbatim, with no normalization.

## The gate round-trip is two manifests

A gated run and its resumption are separate runs linked by `run.resumes`. The gated manifest holds `status: gated`, the open gate, and no deliverable. The resumed manifest holds the answered gate, the decision, and the artifact. The validator enforces the pairing in both directions: `gated` requires an open blocking gate, and `completed` forbids one.

`schema/examples/2026-08-31-research-brief-1.json` and `-2.json` record the genesis round-trip: the run that refused to write before its uncertainty gate, and the resumption that carried Praneet's answer and produced the brief.

## Emission contract for workflow ports

A port adds one block to its SKILL.md, alongside the v0 frontmatter block:

```markdown
## Manifest emission

Before finishing, including when you stop at a gate, write `run-manifest.json`
in the workspace root following design-ledger schema/run-manifest.schema.json,
version 0.1. Emit every finding, assumption, gate, decision, and recommendation
this run produced, using the same ids as the deliverable, and set
run.provenance to "emitted". If a blocking gate is unanswered, set run.status
to "gated", leave the gate "open", and do not write the deliverable. List what
you could not verify under "limits".
```

Port cost for v0 was one frontmatter block per workflow. v0.1 adds this second block. Contract fidelity survived it in live tests across all four workflow ports on 2026-09-01: every run emitted a schema-valid manifest on its first attempt and ran the validator itself before finishing, and the research-brief run held at its uncertainty gate and emitted a `status: gated` manifest with no deliverable — the blocked-work path works end to end. One run also recorded a decision it found already made in the request (`channel: other`) and asked only the genuinely open questions, unprompted by this block. The four emitted manifests ship in `schema/examples/`, unmodified from the workspace originals except for an added `run.log` join hint.

## Validation

```
python3 schema/validate.py schema/examples/*.json
```

`validate.py` is standard-library Python. It interprets the subset of JSON Schema the schema file uses, so the schema file stays the single source of truth for shapes and enums, and then checks what JSON Schema cannot express: id uniqueness, cross-references (gate to decision, decision to gate, object to artifact), the gated-status pairing, self-resume, and artifact path safety.

## Board consumption

Shipped 2026-09-01: `extract.py` reads every manifest in `--manifests-dir`, schema-checks each one and excludes invalid files loudly, joins manifests to log-measured stats through `run.log`, and no longer takes `--facts`. The six genesis runs travel as backfilled manifests, and `board/facts/` is history the board no longer reads.

## Open questions

1. **One evidence vocabulary or three.** The day-one runs graded evidence in three vocabularies: `reported / derived / unverified` (design-qa findings), `strong / partial / assumption` (pmf-review evidence rows), `measured / calculated / assumption` (research-brief numbers). v0.1 standardizes findings' basis, keeps the rest in artifacts and `tags`, and defers unification until more runs show which distinctions carry weight.
2. **Verifying self-declared contract checks.** An emitted manifest's `contract` block is testimony. A checker that reads the deliverable and re-scores the contract items would upgrade it to evidence.
3. **Decisions after emission.** A decision made from the board (roadmap v0.2) lands after the manifest is written. Whether the board appends to the manifest, writes a sibling decision record, or posts a continuation that emits a new manifest is the first design question of v0.2.
4. **Multi-select answers.** Question defaults and answers can be lists (observed in the genesis gate's checkbox question). `decision.answers` accepts them; the board rendering for list answers is undesigned.
