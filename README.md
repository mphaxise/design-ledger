# design-ledger

A local-first practice layer for designers working with AI agents. It records design work as a ledger of runs, findings, gates, and decisions, keeps human judgment as a named step with an owner, and graduates proven one-off tools into maintained shared capability. Generation stays with the substrates designers already use — OpenDesign, Claude Code, Codex, and their peers. This layer owns the evidence those runs leave behind.

## The gap

Agent design tooling ships generation. The discipline around it is the missing half: evidence quality labels, judgment gates that stop a run until a human decides, provenance on every claim, and a path that turns a generated one-off into a tool someone maintains. design-ledger builds that half as a thin, open layer over existing substrates.

## Proven on day one (2026-08-31)

Six live runs inside OpenDesign 0.21.1, driven through its daemon API with Claude Code as the engine:

- Four practice workflows — design-qa, ux-review, pmf-review, research-brief — ran with their contracts fully intact: severity-ranked findings with reproduction paths, evidence labeled `strong` / `partial` / `assumption`, role boundaries respected, every mandatory judgment gate asked.
- Port cost per workflow: one frontmatter block on an existing SKILL.md contract.
- One run refused to write its deliverable until a human answered its scope gate, resumed with the answer, and completed the brief. The judgment loop closed across substrate, agent, and a phone.
- Total model spend for the whole suite: $6.31.

The contract checks, gate answers, findings, and assumptions behind these claims ship as backfilled run manifests (`schema/examples/`), validated against the v0.1 schema. Full run logs stay local to the machine that produced them.

## The Evidence Board (v0.1)

The board renders runs as objects: status, cost, artifacts, findings, assumptions, gates with their answer state, standing recommendations, and a section named "What this board cannot see yet." It is a read-only projection generated from run manifests (`docs/run-manifest.md`) joined with the daemon API and run logs; manifests carry the objects, logs carry what the substrate measured.

```
python3 board/extract.py --logs-dir <dir-with-sse-logs> \
  --artifacts-dir <dir-with-run-artifacts> \
  --manifests-dir schema/examples \
  --decisions-dir board/decisions \
  --out board/out/data.json
python3 board/build_board.py --data board/out/data.json --out board/out/board.html
```

To answer gates from the board, serve it instead of opening the file — open gates gain live answer forms, and a submitted answer becomes a decision record, a posted continuation, and a harvested manifest (`docs/write-path.md`):

```
python3 board/serve.py --manifests-dir schema/examples --logs-dir <dir-with-sse-logs>
```

Python 3 standard library only. The daemon flag defaults to `http://127.0.0.1:7457`; the board renders from logs alone when the daemon is offline.

## Architecture

The layer runs outside the substrate, on the seam OpenDesign documents for external orchestrators: the daemon HTTP API drives runs, and workspace provenance keeps source authority outside the design tool. Practice contracts travel as SKILL.md files the substrate composes into its agent prompts. The board projects what runs leave behind into objects. Nothing here forks or patches a substrate.

## The base-UI hypothesis

Chat is an input method. The home surface for design practice is the ledger: a project view where findings, assumptions, gates, and decisions carry identity, status, and history, where runs create the objects and humans answer them. The board is the first test of that hypothesis; `docs/concept.md` carries the full argument.

## Status

v0.1, shipped 2026-09-01. Real: the board, the four workflow ports, the substrate evidence above, the run-manifest schema with six backfilled genesis manifests, a board that renders from manifests, and live emission proven across all four workflow ports on 2026-09-01 — every run emitted a schema-valid manifest on its first attempt, and the research-brief run held at its gate and emitted a gated manifest with no deliverable (the four emitted manifests are in `schema/examples/`). Planned: a write path from board to substrate, the graduation loop, more substrates. `ROADMAP.md` carries the sequence and is explicit about which is which.

## License

Apache-2.0.
