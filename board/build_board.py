#!/usr/bin/env python3
"""Render the evidence board from data.json to a single self-contained HTML file.

The board is the v0 test of the project's base-UI hypothesis: work as objects
(runs, gates, decisions, evidence) rather than transcript. Read-only.

Part of design-ledger. Apache-2.0.
"""
import argparse
import html
import json


def esc(x):
    return html.escape(str(x if x is not None else '—'))


def fmt_ms(ms):
    if not ms:
        return '—'
    s = int(ms / 1000)
    return f'{s // 60}m{s % 60:02d}s' if s >= 60 else f'{s}s'


CSS = """
:root{
  --bg:#faf9f7;--surface:#ffffff;--ink:#1a1a1a;--ink-2:#555;--ink-3:#8a8a8a;
  --border:#e3e0da;--accent:#1a6b4a;--ok:#1a6b4a;--open:#8a5a00;--warn-bg:#fdf6e3;
  --ok-bg:#eef6f1;--chip:#f0eeea;--mono:ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#141414;--surface:#1d1d1d;--ink:#ececec;--ink-2:#b3b3b3;--ink-3:#7d7d7d;
  --border:#333;--accent:#5dbd94;--ok:#5dbd94;--open:#d9a441;--warn-bg:#2a2313;
  --ok-bg:#16241d;--chip:#262626;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:15px;margin:36px 0 10px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink-2)}
.sub{color:var(--ink-2);margin:0 0 6px}
.meta{color:var(--ink-3);font-size:13px;font-family:var(--mono)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:10px;margin-top:20px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:12px 14px}
.tile .n{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums}
.tile .l{font-size:12.5px;color:var(--ink-2)}
table{width:100%;border-collapse:collapse;background:var(--surface);
  border:1px solid var(--border);border-radius:8px;overflow:hidden}
th,td{padding:8px 12px;text-align:left;border-top:1px solid var(--border);
  font-size:14px;vertical-align:top}
th{border-top:0;font-size:12.5px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-2)}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:13px}
.status{font-size:12.5px;font-weight:600}
.status.ok{color:var(--ok)}.status.open{color:var(--open)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:14px 16px}
.card.answered{background:var(--ok-bg)}
.card.open{background:var(--warn-bg)}
.card h3{margin:0 0 4px;font-size:14.5px}
.card .from{font-size:12.5px;color:var(--ink-3);font-family:var(--mono)}
.card ul{margin:8px 0 0;padding-left:18px;color:var(--ink-2);font-size:13.5px}
.answer{margin-top:8px;font-size:13.5px}
.answer b{color:var(--ok)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{background:var(--chip);border:1px solid var(--border);border-radius:99px;
  padding:3px 12px;font-size:13px;font-family:var(--mono)}
.honesty{border-left:3px solid var(--open);padding:2px 0 2px 14px;color:var(--ink-2);
  font-size:13.5px}
.honesty p{margin:6px 0}
a{color:var(--accent)}
.foot{margin-top:40px;color:var(--ink-3);font-size:12.5px;font-family:var(--mono)}
"""


def tiles(d):
    t = d['totals']
    distinct = {}
    for g in d['gates']:
        if distinct.get(g['gate_id']) != 'answered':
            distinct[g['gate_id']] = g['state']
    gates = list(distinct.values())
    answered = sum(1 for s in gates if s == 'answered')
    held = sum(1 for c in d['contract_checks'] if c.get('held'))
    cells = [
        (t['runs'], 'runs'),
        (f"${t['cost']}", 'model spend'),
        (f"{t['out_tokens']:,}", 'output tokens'),
        (fmt_ms(t['wall_ms']), 'agent wall time'),
        (f"{answered}/{len(gates)}", 'gates answered'),
        (f"{held}/{len(d['contract_checks'])}", 'contracts held'),
        (len(d.get('findings', [])), 'findings on record'),
        (len(d.get('assumptions', [])), 'assumptions on record'),
    ]
    inner = ''.join(f'<div class="tile"><div class="n">{esc(n)}</div>'
                    f'<div class="l">{esc(l)}</div></div>' for n, l in cells)
    return f'<div class="tiles">{inner}</div>'


def runs_table(d):
    rows = []
    for r in d['runs']:
        ok = r['status'] in ('succeeded', 'completed')
        icon = '✓ ' if ok else '◌ '
        st = f'<span class="status {"ok" if ok else "open"}">{icon}{esc(r["status"])}</span>'
        art = ', '.join(esc(a) for a in r['artifacts']) or \
              '<span class="meta">gates / text</span>'
        prov = esc(r.get('provenance') or 'no manifest')
        rows.append(
            f'<tr><td>{esc(r["workflow"])}</td><td>{esc(r["mode"])}</td>'
            f'<td>{st}</td><td class="num">{fmt_ms(r["duration_ms"])}</td>'
            f'<td class="num">{r["out_tokens"] or "—"}</td>'
            f'<td class="num">${round(r["cost"], 2) if r["cost"] else "—"}</td>'
            f'<td>{art}</td><td class="num">{prov}</td></tr>')
    return ('<table><tr><th>workflow</th><th>mode</th><th>status</th><th>time</th>'
            '<th>out tok</th><th>cost</th><th>deliverable</th><th>manifest</th></tr>'
            + ''.join(rows) + '</table>')


def findings_table(d):
    if not d.get('findings'):
        return '<p class="sub">No findings on record yet.</p>'
    rows = []
    for f in sorted(d['findings'], key=lambda x: x.get('severity', 'P9')):
        rows.append(
            f'<tr><td class="num">{esc(f.get("severity"))}</td>'
            f'<td><b>{esc(f.get("title") or f["id"])}</b><br>'
            f'<span class="sub">{esc(f["statement"])}</span></td>'
            f'<td class="num">{esc(f.get("basis") or "—")}</td>'
            f'<td class="num">{esc(f.get("status", "open"))}</td>'
            f'<td class="num">{esc(f["run"])}</td></tr>')
    return ('<table><tr><th>sev</th><th>finding</th><th>basis</th><th>status</th>'
            '<th>run</th></tr>' + ''.join(rows) + '</table>')


def assumptions_cards(d):
    if not d.get('assumptions'):
        return '<p class="sub">No assumptions on record yet.</p>'
    cards = []
    for s in d['assumptions']:
        extra = ''
        if s.get('basis'):
            extra += f'<p class="answer"><b>Basis:</b> {esc(s["basis"])}</p>'
        if s.get('impact_if_wrong'):
            extra += f'<p class="answer"><b>If wrong:</b> {esc(s["impact_if_wrong"])}</p>'
        cards.append(
            f'<div class="card open"><h3>{esc(s["statement"])}</h3>'
            f'<div class="from">assumption · {esc(s["run"])} · {esc(s.get("status", "open"))}</div>'
            f'{extra}</div>')
    return f'<div class="cards">{"".join(cards)}</div>'


def gate_cards(d):
    cards = []
    for g in d['gates']:
        qs = ''.join(f'<li>{esc(q)}</li>' for q in g['questions'])
        if g['state'] == 'answered':
            tail = (f'<p class="answer"><b>Answered:</b> {esc(g.get("answer"))} '
                    f'<span class="meta">— {esc(g.get("by"))}, {esc(g.get("on"))}, '
                    f'{esc(g.get("via"))}</span></p>')
        elif g.get('superseded'):
            tail = '<p class="answer">◌ open at emission — the resumed run carries the answer</p>'
        elif g.get('blocking', True):
            tail = '<p class="answer status open">◌ open — work blocked on a human decision</p>'
        else:
            tail = '<p class="answer status open">◌ open checkpoint — deliverable exists, next step awaits a human</p>'
        kind = f' · {esc(g["kind"])}' if g.get('kind') else ''
        cards.append(
            f'<div class="card {g["state"]}"><h3>{esc(g["title"])}</h3>'
            f'<div class="from">gate{kind} · {esc(g["run"])}</div><ul>{qs}</ul>{tail}</div>')
    for rec in d['recommendations']:
        src = f' · {esc(rec["source"])}' if rec.get('source') else ''
        cards.append(
            f'<div class="card open"><h3>Recommendation</h3>'
            f'<div class="from">verdict · {esc(rec["run"])}{src}</div>'
            f'<p class="answer">“{esc(rec["text"])}”</p>'
            f'<p class="answer status open">◌ {esc(rec.get("state", "awaiting-decision"))}</p></div>')
    return f'<div class="cards">{"".join(cards)}</div>'


def tally_chips(d):
    out = []
    for name, counts in d['tallies'].items():
        chips = ''.join(f'<span class="chip">{esc(k)} · {v}</span>'
                        for k, v in counts.items())
        out.append(f'<p class="sub">{esc(name)}</p><div class="chips">{chips}</div>')
    return ''.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    d = json.load(open(a.data))
    daemon = d['daemon']
    daemon_line = (f'daemon {esc(daemon["version"])} live' if daemon['ok']
                   else 'daemon offline — log evidence only')
    honesty = ''.join(f'<p>{esc(h)}</p>' for h in d['honesty'])
    checks = ''.join(
        f'<span class="chip">{esc(c["run"])} · {"held ✓" if c.get("held") else "broke ✗"}'
        f'{" · " + esc(c["declared_by"]) if c.get("declared_by") else ""}</span>'
        for c in d['contract_checks'])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence Board — design-ledger</title><style>{CSS}</style></head><body>
<div class="wrap">
<h1>Evidence Board</h1>
<p class="sub">Design work as a ledger of runs, gates, decisions, and evidence —
the transcript is upstream, this is the state.</p>
<p class="meta">generated {esc(d['generated'])} · {daemon_line} · read-only projection v0.1</p>
{tiles(d)}
<h2>Runs</h2>{runs_table(d)}
<h2>Findings</h2>{findings_table(d)}
<h2>Gates &amp; decisions</h2>{gate_cards(d)}
<h2>Assumptions</h2>{assumptions_cards(d)}
<h2>Contract fidelity</h2><div class="chips">{checks}</div>
<h2>Evidence label tallies</h2>{tally_chips(d)}
<h2>What this board cannot see yet</h2><div class="honesty">{honesty}</div>
<p class="foot">design-ledger · board v0.1 · data: {esc(a.data)}</p>
</div></body></html>"""
    open(a.out, 'w').write(page)
    print('WROTE', a.out, len(page), 'bytes')


if __name__ == '__main__':
    main()
