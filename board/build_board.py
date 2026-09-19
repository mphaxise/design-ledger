#!/usr/bin/env python3
"""Render the evidence board from data.json to a single self-contained HTML file.

The landing answers one question first: what needs a human right now. Open
blocking gates surface at the top with live answer forms; everything else —
per-run findings, checkpoint gates, recommendations, assumptions, limits —
collapses into run cards and folded sections. Native disclosure, no
libraries, no build step.

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
.wrap{max-width:980px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:14px;margin:34px 0 10px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--ink-2)}
.sub{color:var(--ink-2);margin:0 0 6px}
.meta{color:var(--ink-3);font-size:12.5px;font-family:var(--mono)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));
  gap:10px;margin-top:18px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:10px 12px}
.tile .n{font-size:21px;font-weight:650;font-variant-numeric:tabular-nums}
.tile .l{font-size:12px;color:var(--ink-2)}
table{width:100%;border-collapse:collapse;background:var(--surface);
  border:1px solid var(--border);border-radius:8px;overflow:hidden}
th,td{padding:7px 10px;text-align:left;border-top:1px solid var(--border);
  font-size:13.5px;vertical-align:top}
th{border-top:0;font-size:12px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-2)}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:12.5px}
.status{font-size:12.5px;font-weight:600}
.status.ok{color:var(--ok)}.status.open{color:var(--open)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;
  padding:14px 16px;margin:10px 0}
.card.answered{background:var(--ok-bg)}
.card.needs{background:var(--warn-bg);border-color:var(--open)}
.card h3{margin:0 0 4px;font-size:14.5px}
.card .from{font-size:12.5px;color:var(--ink-3);font-family:var(--mono)}
.card ul{margin:8px 0 0;padding-left:18px;color:var(--ink-2);font-size:13.5px}
.answer{margin-top:8px;font-size:13.5px}
.answer b{color:var(--ok)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{background:var(--chip);border:1px solid var(--border);border-radius:99px;
  padding:3px 12px;font-size:12.5px;font-family:var(--mono)}
.honesty{border-left:3px solid var(--open);padding:2px 0 2px 14px;color:var(--ink-2);
  font-size:13.5px}
.honesty p{margin:6px 0}
a{color:var(--accent)}
.foot{margin-top:40px;color:var(--ink-3);font-size:12.5px;font-family:var(--mono)}
details{border:1px solid var(--border);border-radius:8px;background:var(--surface);
  margin:8px 0;padding:0}
details>summary{cursor:pointer;list-style:none;padding:11px 14px;display:flex;
  flex-wrap:wrap;gap:8px 14px;align-items:baseline;font-size:13.5px}
details>summary::before{content:"▸";color:var(--ink-3);font-size:11px}
details[open]>summary::before{content:"▾"}
details>summary:hover{background:var(--chip)}
details>.body{padding:2px 14px 14px;border-top:1px solid var(--border)}
details.plain{border:0;background:none}
details.plain>.body{border-top:0;padding:6px 0 4px}
.run-name{font-weight:650}
.badge{font-size:12px;font-family:var(--mono);color:var(--ink-2);
  background:var(--chip);border-radius:99px;padding:1px 9px}
.badge.warn{color:var(--open)}
h4{font-size:12px;text-transform:uppercase;letter-spacing:.05em;
  color:var(--ink-2);margin:16px 0 6px}
.rec{font-size:13.5px;color:var(--ink-2);margin:6px 0;padding-left:14px;
  border-left:3px solid var(--border)}
.assump{font-size:13.5px;margin:8px 0}
.assump .why{color:var(--ink-3);font-size:13px}
form.decide{margin-top:12px;border-top:1px dashed var(--border);padding-top:10px}
.q{margin:8px 0}
.q-label{margin:0 0 4px;font-size:13.5px;font-weight:600}
label.opt{display:block;font-size:13.5px;color:var(--ink-2);margin:3px 0;cursor:pointer}
.free{width:100%;box-sizing:border-box;background:var(--bg);color:var(--ink);
  border:1px solid var(--border);border-radius:6px;padding:6px 8px;font:inherit;font-size:13.5px}
form.decide button{margin-top:10px;background:var(--accent);color:#fff;border:0;
  border-radius:6px;padding:8px 14px;font:inherit;font-size:13.5px;cursor:pointer}
form.decide button:disabled{opacity:.45;cursor:not-allowed}
.decide-status{min-height:1em}
"""


def root_of(run_id, resumes_map):
    seen = set()
    while run_id in resumes_map and run_id not in seen:
        seen.add(run_id)
        run_id = resumes_map[run_id]
    return run_id


def gate_identity_states(d):
    """Distinct gates: same gate id counts once across a resume chain, and
    separately across unrelated runs that reused an id."""
    resumes = {r['run_id']: r['resumes'] for r in d['runs']
               if r.get('run_id') and r.get('resumes')}
    distinct = {}
    for g in d['gates']:
        key = (root_of(g['run'], resumes), g['gate_id'])
        if distinct.get(key) != 'answered':
            distinct[key] = g['state']
    return list(distinct.values())


def tiles(d):
    t = d['totals']
    states = gate_identity_states(d)
    answered = sum(1 for s in states if s == 'answered')
    held = sum(1 for c in d['contract_checks']
               if c.get('status', 'held' if c.get('held') else 'broke') == 'held')
    cells = [
        (t['runs'], 'runs'),
        (f"${t['cost']}", 'model spend'),
        (f'{answered}/{len(states)}', 'gates answered'),
        (f"{held}/{len(d['contract_checks'])}", 'contracts held'),
        (len(d.get('findings', [])), 'findings'),
        (len(d.get('assumptions', [])), 'assumptions'),
    ]
    inner = ''.join(f'<div class="tile"><div class="n">{esc(n)}</div>'
                    f'<div class="l">{esc(l)}</div></div>' for n, l in cells)
    return f'<div class="tiles">{inner}</div>'


def answer_form(g):
    qs = [q for q in g['questions'] if isinstance(q, dict)]
    if not qs:
        return ''
    rows = []
    for q in qs:
        qid = esc(q.get('id', ''))
        rows.append(f'<div class="q" data-qid="{qid}"><p class="q-label">{esc(q.get("label"))}</p>')
        qtype = q.get('type', 'radio')
        if q.get('options'):
            itype = 'checkbox' if qtype == 'checkbox' else 'radio'
            for o in q['options']:
                val, lab = esc(o.get('value', '')), esc(o.get('label', ''))
                dflt = q.get('default')
                checked = ' checked' if (val == dflt or (isinstance(dflt, list) and o.get('value') in dflt)) else ''
                rows.append(f'<label class="opt"><input type="{itype}" name="{qid}" value="{val}" data-label="{lab}"{checked}> {lab}</label>')
        elif qtype == 'textarea':
            rows.append(f'<textarea rows="2" class="free" name="{qid}"></textarea>')
        else:
            rows.append(f'<input type="text" class="free" name="{qid}">')
        rows.append('</div>')
    return (f'<form class="decide" data-run="{esc(g["run"])}" data-gate="{esc(g["gate_id"])}">'
            + ''.join(rows) +
            '<div class="q"><p class="q-label">Answered by</p>'
            '<input type="text" class="free" name="__by" placeholder="your name"></div>'
            '<button type="submit" disabled>Record decision &amp; resume the run</button>'
            '<p class="meta serve-hint">forms are live only when served: python3 board/serve.py</p>'
            '<p class="meta decide-status"></p></form>')


def gate_card(g, needs=False):
    if g['state'] == 'answered':
        src = ' · via decision record' if g.get('answered_by') == 'decision-record' else ''
        tail = (f'<p class="answer"><b>Answered:</b> {esc(g.get("answer"))} '
                f'<span class="meta">— {esc(g.get("by"))}, {esc(g.get("on"))}, '
                f'{esc(g.get("via"))}{src}</span></p>')
        form = ''
    elif g.get('superseded'):
        tail = '<p class="answer">◌ open at emission — the resumed run carries the answer</p>'
        form = ''
    else:
        blocked = g.get('blocking', True)
        tail = ('<p class="answer status open">◌ open — work blocked on this decision</p>' if blocked
                else '<p class="answer status open">◌ open checkpoint — deliverable exists, next step awaits a human</p>')
        form = answer_form(g)
        if not form and blocked:
            tail += '<p class="meta">This gate carries no structured questions; answer it in the substrate conversation.</p>'
    kind = f' · {esc(g["kind"])}' if g.get('kind') else ''
    desc = f'<p class="answer">{esc(g["description"])}</p>' if g.get('description') else ''
    cls = 'needs' if needs else g['state']
    return (f'<div class="card {cls}"><h3>{esc(g["title"])}</h3>'
            f'<div class="from">gate{kind} · {esc(g["run"])}</div>{desc}{tail}{form}</div>')


def needs_decision(d):
    open_blocking = [g for g in d['gates']
                     if g['state'] == 'open' and g.get('blocking', True)
                     and not g.get('superseded')]
    checkpoints = sum(1 for g in d['gates'] if g['state'] == 'open'
                      and not g.get('blocking', True))
    recs = sum(1 for r in d['recommendations']
               if r.get('state', 'awaiting-decision') == 'awaiting-decision')
    if open_blocking:
        cards = ''.join(gate_card(g, needs=True) for g in open_blocking)
        head = (f'<p class="sub">{len(open_blocking)} gate(s) hold work stopped '
                'until a human answers.</p>')
    else:
        cards = ''
        head = '<p class="sub">Nothing is blocked. Runs completed their deliverables.</p>'
    tallies = (f'<p class="meta">also open, inside the run cards below: '
               f'{checkpoints} checkpoint gate(s) · {recs} recommendation(s) awaiting a decision</p>')
    return head + cards + tallies


def finding_rows(fs):
    rows = []
    for f in sorted(fs, key=lambda x: x.get('severity', 'P9')):
        rows.append(
            f'<tr><td class="num">{esc(f.get("severity"))}</td>'
            f'<td><b>{esc(f.get("title") or f["id"])}</b><br>'
            f'<span class="sub">{esc(f["statement"])}</span></td>'
            f'<td class="num">{esc(f.get("basis") or "—")}</td>'
            f'<td class="num">{esc(f.get("status", "open"))}</td></tr>')
    return ('<table><tr><th>sev</th><th>finding</th><th>basis</th><th>status</th></tr>'
            + ''.join(rows) + '</table>')


def sev_counts(fs):
    out = {}
    for f in fs:
        out[f.get('severity', '?')] = out.get(f.get('severity', '?'), 0) + 1
    return ' · '.join(f'{n} {s}' for s, n in sorted(out.items()))


def run_card(r, by_run):
    rid = r.get('run_id')
    fs = by_run['findings'].get(rid, [])
    gs = by_run['gates'].get(rid, [])
    recs = by_run['recs'].get(rid, [])
    asps = by_run['assumps'].get(rid, [])
    ok = r['status'] in ('succeeded', 'completed')
    icon = '✓' if ok else '◌'
    stat = f'<span class="status {"ok" if ok else "open"}">{icon} {esc(r["status"])}</span>'
    art = ', '.join(esc(a) for a in r.get('artifacts', [])) or 'gates / text'
    badges = []
    if fs:
        badges.append(f'<span class="badge">{len(fs)} findings · {sev_counts(fs)}</span>')
    open_gates = sum(1 for g in gs if g['state'] == 'open' and not g.get('superseded'))
    if gs:
        cls = ' warn' if open_gates else ''
        badges.append(f'<span class="badge{cls}">{len(gs)} gate(s), {open_gates} open</span>')
    if recs:
        badges.append(f'<span class="badge">{len(recs)} recommendations</span>')
    if asps:
        badges.append(f'<span class="badge">{len(asps)} assumptions</span>')
    summary = (f'<span class="run-name">{esc(r["workflow"])}</span>'
               f'<span class="meta">{esc(r["mode"])} · {esc(r.get("date") or "")}</span>'
               f'{stat}'
               f'<span class="num meta">{fmt_ms(r["duration_ms"])} · '
               f'${round(r["cost"], 2) if r["cost"] else "—"} · '
               f'{esc(r.get("provenance") or "no manifest")}</span>'
               + ''.join(badges))
    body = [f'<p class="meta">deliverable: {art} · run id: {esc(rid or r.get("log"))}</p>']
    if fs:
        body.append('<h4>Findings</h4>' + finding_rows(fs))
    if gs:
        body.append('<h4>Gates</h4>' + ''.join(gate_card(g) for g in gs))
    if recs:
        body.append('<h4>Recommendations</h4>')
        for rec in recs:
            body.append(f'<p class="rec">“{esc(rec["text"])}” '
                        f'<span class="meta">◌ {esc(rec.get("state", "awaiting-decision"))}</span></p>')
    if asps:
        body.append('<h4>Assumptions</h4>')
        for s in asps:
            why = s.get('basis') or ''
            iw = s.get('impact_if_wrong')
            extra = f'<div class="why">{esc(why)}</div>' if why else ''
            if iw:
                extra += f'<div class="why"><b>If wrong:</b> {esc(iw)}</div>'
            body.append(f'<div class="assump">{esc(s["statement"])} '
                        f'<span class="meta">· {esc(s.get("status", "open"))}</span>{extra}</div>')
    lims = r.get('limits', [])
    if lims:
        body.append('<h4>What this run could not see</h4><div class="honesty">'
                    + ''.join(f'<p>{esc(x)}</p>' for x in lims) + '</div>')
    return f'<details><summary>{summary}</summary><div class="body">{"".join(body)}</div></details>'


def runs_section(d, by_run):
    order = {'gated': 0, 'failed': 1}
    runs = sorted(d['runs'], key=lambda r: (order.get(r['status'], 2),
                                            str(r.get('date') or ''),
                                            str(r.get('workflow'))))
    return ''.join(run_card(r, by_run) for r in runs)


def folded_findings(d):
    fs = d.get('findings', [])
    if not fs:
        return ''
    return (f'<details class="plain"><summary><span class="run-name">All findings across runs</span>'
            f'<span class="badge">{len(fs)} total · {sev_counts(fs)}</span></summary>'
            f'<div class="body">{finding_rows_with_run(fs)}</div></details>')


def finding_rows_with_run(fs):
    rows = []
    for f in sorted(fs, key=lambda x: (x.get('severity', 'P9'), x.get('run', ''))):
        rows.append(
            f'<tr><td class="num">{esc(f.get("severity"))}</td>'
            f'<td><b>{esc(f.get("title") or f["id"])}</b><br>'
            f'<span class="sub">{esc(f["statement"])}</span></td>'
            f'<td class="num">{esc(f.get("basis") or "—")}</td>'
            f'<td class="num">{esc(f["run"])}</td></tr>')
    return ('<table><tr><th>sev</th><th>finding</th><th>basis</th><th>run</th></tr>'
            + ''.join(rows) + '</table>')


def check_label(c):
    st = c.get('status', 'held' if c.get('held') else 'broke')
    if st == 'held':
        return 'held ✓'
    if st == 'gated-partial':
        return f'{c.get("held_n")}/{c.get("total")} held · rest withheld at the gate'
    return 'broke ✗'


def folded_notes(d):
    checks = ''.join(
        f'<span class="chip">{esc(c["run"])} · {check_label(c)}'
        f'{" · " + esc(c["declared_by"]) if c.get("declared_by") else ""}</span>'
        for c in d['contract_checks'])
    tallies = []
    for name, counts in d.get('tallies', {}).items():
        chips = ''.join(f'<span class="chip">{esc(k)} · {v}</span>'
                        for k, v in counts.items())
        tallies.append(f'<p class="sub">{esc(name)}</p><div class="chips">{chips}</div>')
    honesty = ''.join(f'<p>{esc(h)}</p>' for h in d['honesty'])
    body = (f'<h4>Contract fidelity</h4><div class="chips">{checks}</div>'
            + (f'<h4>Evidence label tallies</h4>{"".join(tallies)}' if tallies else '')
            + (f'<h4>Board-level notes</h4><div class="honesty">{honesty}</div>' if honesty else ''))
    n = len(d['contract_checks'])
    return (f'<details class="plain"><summary><span class="run-name">Fidelity, tallies &amp; board notes</span>'
            f'<span class="badge">{n} contract check(s)</span></summary>'
            f'<div class="body">{body}</div></details>')


JS = """
<script>
(function () {
  var served = location.protocol === 'http:' || location.protocol === 'https:';
  document.querySelectorAll('form.decide').forEach(function (f) {
    var btn = f.querySelector('button'), hint = f.querySelector('.serve-hint'),
        status = f.querySelector('.decide-status');
    if (served) { btn.disabled = false; hint.hidden = true; }
    f.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var answers = {}, parts = [];
      f.querySelectorAll('.q').forEach(function (q) {
        var qid = q.dataset.qid; if (!qid) return;
        var picked = q.querySelectorAll('input:checked');
        if (picked.length) {
          var vals = [], labs = [];
          picked.forEach(function (i) { vals.push(i.value); labs.push(i.dataset.label || i.value); });
          answers[qid] = vals.length > 1 ? vals : vals[0];
          parts.push(labs.join(', '));
        } else {
          var free = q.querySelector('.free');
          if (free && free.value.trim()) { answers[qid] = free.value.trim(); parts.push(free.value.trim()); }
        }
      });
      var by = (f.querySelector('[name="__by"]').value || '').trim();
      if (!by) { status.textContent = 'Name required — the record stores who answered.'; return; }
      if (!parts.length) { status.textContent = 'Pick or write an answer first.'; return; }
      btn.disabled = true; status.textContent = 'Recording decision and posting the continuation…';
      fetch('/decide', { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ run: f.dataset.run, gate: f.dataset.gate,
          answer: parts.join(' · '), answers: answers, by: by }) })
        .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); })
        .then(function (res) {
          status.textContent = res.j.message || (res.ok ? 'Recorded.' : 'Refused.');
          if (res.ok && res.j.reload) setTimeout(function () { location.reload(); }, 1500);
          else btn.disabled = false;
        })
        .catch(function (e) { status.textContent = 'Failed: ' + e; btn.disabled = false; });
    });
  });
})();
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    d = json.load(open(a.data))

    by_run = {'findings': {}, 'gates': {}, 'recs': {}, 'assumps': {}}
    for f in d.get('findings', []):
        by_run['findings'].setdefault(f['run'], []).append(f)
    for g in d.get('gates', []):
        by_run['gates'].setdefault(g['run'], []).append(g)
    for r in d.get('recommendations', []):
        by_run['recs'].setdefault(r['run'], []).append(r)
    for s in d.get('assumptions', []):
        by_run['assumps'].setdefault(s['run'], []).append(s)

    daemon = d['daemon']
    daemon_line = (f'daemon {esc(daemon["version"])} live' if daemon['ok']
                   else 'daemon offline — log evidence only')
    t = d['totals']
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence Board — design-ledger</title><style>{CSS}</style></head><body>
<div class="wrap">
<h1>Evidence Board</h1>
<p class="sub">Design work as a ledger of runs, gates, decisions, and evidence —
the transcript is upstream, this is the state.</p>
<p class="meta">generated {esc(d['generated'])} · {daemon_line} ·
{t['out_tokens']:,} output tokens · {fmt_ms(t['wall_ms'])} agent wall time ·
read-only except the gates · v0.1</p>
{tiles(d)}
<h2>Needs a decision</h2>{needs_decision(d)}
<h2>Runs</h2>{runs_section(d, by_run)}
<h2>Across runs</h2>{folded_findings(d)}{folded_notes(d)}
<p class="foot">design-ledger · board v0.1 · data: {esc(a.data)}</p>
</div>
{JS}
</body></html>"""
    open(a.out, 'w').write(page)
    print('WROTE', a.out, len(page), 'bytes')


if __name__ == '__main__':
    main()
