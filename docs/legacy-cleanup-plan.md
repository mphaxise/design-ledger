# Legacy cleanup plan

## Claim

The Git/Codex path should become the maintained runtime after it proves parity with every retained Design Ledger capability. Historical evidence remains available throughout cleanup.

## Phases

1. Inventory the OpenDesign daemon integration, board write path, manifests, fixtures, and documentation by current caller and evidence value.
2. Mark each item `retain`, `migrate`, `archive`, or `remove-candidate` with a source-backed reason.
3. Migrate capabilities still required by the Codex path and prove equivalent behavior with deterministic tests or dated run evidence.
4. Move historical-only material into a clearly labeled reference area without rewriting run testimony.
5. Remove a dead path only after no maintained caller, schema, test, document, or receipt depends on it.
6. Rebuild the board against the new project, experience, event, and receipt model.

## Current inventory

| Area | Disposition | Basis |
| --- | --- | --- |
| `runtime/` | Maintain | Current Git/Codex, experience, evidence, and checkpoint runtime. |
| `plugins/design-ledger/` | Maintain | Installed Codex skill and background observation hook. |
| `board/build_board.py` | Migrate | Contains the current board presentation but reads the legacy extracted model. |
| `board/extract.py` | Replace after parity | Joins OpenDesign manifests, daemon data, and logs. The current runtime emits project events and receipts directly. |
| `board/serve.py` | Archive after parity | Implements the OpenDesign gate-continuation write path and daemon coupling. |
| `schema/run-manifest.schema.json` and `schema/examples/` | Retain as historical evidence | Support the dated v0.1 claims and provenance. |
| `docs/run-manifest.md` and `docs/write-path.md` | Retain as historical documentation | Explain the original evidence and gate experiments. |
| `board/facts/` | Retain | Dated session records remain evidence and are never rewritten during cleanup. |

The active cleanup tranche changes runtime organization, installation, and documentation. Board migration and legacy-path removal remain separate changes with their own parity evidence.

## Stop conditions

Cleanup stops when ownership is unclear, evidence would be lost, a current caller remains, parity is unproven, or deletion scope expands beyond the named paths. Every deletion requires a separate reviewed change.
