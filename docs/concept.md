# Concept: design work as a ledger

## Claim

Design practice with agents produces objects: a finding with a severity and an evidence basis, an assumption with a quality label, a gate with an owner and an answer, a tool with a provenance manifest and a usage count. Objects carry identity, status, and lifecycle. A chat transcript stores them as prose and loses all three. The layer's job is to keep the objects.

## What the first six runs showed (2026-08-31)

Two channels appeared unprompted across every run. Artifacts carried the evidence: reports with stable finding IDs, evidence-basis columns, assumption labels. Question forms carried the judgment: taste gates, tradeoff gates, stop-ship calls, rendered as interactive forms the substrate already supports. The chat text between them was narration. One run held at its gate until a human answered and resumed with the answer. The base surface that fits this behavior is a board of objects, with chat as one way to create them.

## Object model (v0)

Run, Artifact, Finding, Assumption, Gate, Decision, Recommendation, Tool.

The board renders Run, Artifact, Gate, Decision, and Recommendation today. Finding and Assumption arrive with structured emission. Tool arrives with the graduation loop.

## Substrate stance

Substrates own generation, models, rendering, and their own maintenance burden. The layer consumes their documented seams. OpenDesign's externally-prepared-workspace contract and daemon API are the reference integration; plain agent-CLI projects are next. The layer never forks a substrate and never competes with one on generation.

## The graduation loop

A generated one-off proves repetitive, then graduates: provenance manifest, license check, tests, a named maintainer, a registry entry. Upstream maintainers who accept AI-origin work ask for provenance, human accountability, and volume control; the loop is designed to satisfy those three.

## Human judgment stays load-bearing

Every workflow contract carries mandatory gates. A run that reaches one stops, and the object records who answered, what, and when. The layer treats an unanswered gate as blocked work and shows it that way.
