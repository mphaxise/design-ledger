# Roadmap

The aim: an open, local-first standard for evidence-driven design practice with agents.

- **v0 — shipped 2026-08-31.** Evidence Board read-only projection. Four workflow ports to OpenDesign. Genesis evidence in `board/facts/`.
- **v0.1 — shipped 2026-09-01.** Run-manifest schema (`schema/run-manifest.schema.json`) with a stdlib validator; findings, assumptions, gates, and decisions emitted as JSON by the run itself. The board reads manifests; facts files retired. Emission proven live across all four workflow ports on 2026-09-01, the gated path included; the four emitted manifests ship in `schema/examples/` beside the six backfilled genesis manifests.
- **v0.2 — write path, in progress (built 2026-09-01).** Answer a gate from the board: the board records the Decision as a human-owned sibling file, posts the continuation to the substrate, and harvests the resumed run's manifest (`docs/write-path.md`, `board/serve.py`). The loop is fixture-tested end to end; it ships when a human answers a real gate from the board and the round-trip lands.
- **v0.3 — graduation loop v1.** Usage tracking for generated tools, a promotion checklist (provenance manifest, license, tests, maintainer sign-off), a registry format designed for upstream submission.
- **v0.4 — second substrate.** Plain Claude Code / Codex project adapter.
- **v0.5 — practice workspace.** The board becomes the home surface, with chat scoped to a composer inside objects.

Each step ships with its evidence. Claims about what works carry dates and run records.
