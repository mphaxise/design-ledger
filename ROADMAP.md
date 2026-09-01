# Roadmap

The aim: an open, local-first standard for evidence-driven design practice with agents.

- **v0 — shipped 2026-08-31.** Evidence Board read-only projection. Four workflow ports to OpenDesign. Genesis evidence in `board/facts/`.
- **v0.1 — shipped 2026-09-01.** Run-manifest schema (`schema/run-manifest.schema.json`) with a stdlib validator; findings, assumptions, gates, and decisions emitted as JSON by the run itself. The board reads manifests; facts files retired. Emission proven live: a pk-ux-review run wrote a schema-valid manifest and ran the validator itself before finishing ($1.39, 4m54s, first attempt; the emitted manifest is `schema/examples/2026-09-01-ux-review-freshfold-pause.json`).
- **v0.2 — write path.** Answer a gate from the board. The board posts the continuation to the substrate and records the Decision.
- **v0.3 — graduation loop v1.** Usage tracking for generated tools, a promotion checklist (provenance manifest, license, tests, maintainer sign-off), a registry format designed for upstream submission.
- **v0.4 — second substrate.** Plain Claude Code / Codex project adapter.
- **v0.5 — practice workspace.** The board becomes the home surface, with chat scoped to a composer inside objects.

Each step ships with its evidence. Claims about what works carry dates and run records.
