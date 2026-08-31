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

The contract checks and gate answers behind these claims ship as the board's facts file (`board/facts/`). Full run logs stay local to the machine that produced them.

## The Evidence Board (v0)

The board renders runs as objects: status, cost, artifacts, gates with their answer state, standing recommendations, evidence tallies, and a section named "What this board cannot see yet." It is a read-only projection generated from the daemon API plus run logs.

```
python3 board/extract.py --logs-dir <dir-with-sse-logs> \
  --artifacts-dir <dir-with-run-artifacts> \
  --facts board/facts/2026-08-31-substrate-test.json \
  --out board/out/data.json
python3 board/build_board.py --data board/out/data.json --out board/out/board.html
```

Python 3 standard library only. The daemon flag defaults to `http://127.0.0.1:7457`; the board renders from logs alone when the daemon is offline.

## Architecture

The layer runs outside the substrate, on the seam OpenDesign documents for external orchestrators: the daemon HTTP API drives runs, and workspace provenance keeps source authority outside the design tool. Practice contracts travel as SKILL.md files the substrate composes into its agent prompts. The board projects what runs leave behind into objects. Nothing here forks or patches a substrate.

## The base-UI hypothesis

Chat is an input method. The home surface for design practice is the ledger: a project view where findings, assumptions, gates, and decisions carry identity, status, and history, where runs create the objects and humans answer them. The board is the first test of that hypothesis; `docs/concept.md` carries the full argument.

## Status

v0, day one. Real: the board, the four workflow ports, the substrate evidence above. Planned: structured emission from runs, a write path from board to substrate, the graduation loop, more substrates. `ROADMAP.md` carries the sequence and is explicit about which is which.

## License

Apache-2.0.
