#!/usr/bin/env python3
"""Extract evidence objects from OpenDesign runs and saved SSE logs.

v0: best-effort read of the local daemon API plus the SSE logs a run left
behind; emits data.json for build_board.py. The board renders only what this
file can honestly extract; everything session-recorded arrives via --facts
and is labeled as such on the board.

Part of design-ledger. Apache-2.0.
"""
import argparse
import glob
import json
import os
import re
import time
import urllib.request

# v0 mapping from log-name suffix to (workflow, mode). Generic fallback: the
# basename itself. Structured emission from runs replaces this in v1.
WORKFLOW_BY_SUFFIX = {
    'run.log': ('design-qa', 'chat'),
    'run-fs.log': ('design-qa', 'project'),
    'run-ux.log': ('ux-review', 'project'),
    'run-pmf.log': ('pmf-review', 'project'),
    'run-brief.log': ('research-brief', 'project'),
    'run-brief2.log': ('research-brief (resume)', 'project'),
}

FORM_RE = re.compile(
    r'<question-form[^>]*id="([^"]+)"[^>]*title="([^"]+)"[^>]*>(.*?)</question-form>',
    re.S,
)


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.load(r)
    except Exception:
        return None


def parse_log(path):
    text, usage, end = [], None, None
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if not line.startswith('data: '):
            continue
        try:
            d = json.loads(line[6:])
        except Exception:
            continue
        t = d.get('type')
        if t == 'text_delta':
            text.append(d.get('delta', ''))
        elif t == 'usage':
            usage = d
        if 'status' in d and 'terminalAt' in d:
            end = d
    full = ''.join(text)
    forms = []
    for m in FORM_RE.finditer(full):
        labels = []
        try:
            j = json.loads(m.group(3))
            labels = [q.get('label', '') for q in j.get('questions', [])]
        except Exception:
            pass
        forms.append({'form_id': m.group(1), 'title': m.group(2), 'questions': labels})
    u = (usage or {}).get('usage', {})
    return {
        'status': (end or {}).get('status'),
        'artifacts': (end or {}).get('artifactPaths') or [],
        'duration_ms': (usage or {}).get('durationMs'),
        'out_tokens': u.get('output_tokens'),
        'cost': (usage or {}).get('costUsd'),
        'forms': forms,
    }


def count_markers(path, markers):
    try:
        t = open(path, encoding='utf-8', errors='replace').read().lower()
    except Exception:
        return {}
    return {m: t.count(m.lower()) for m in markers}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--daemon', default='http://127.0.0.1:7457')
    ap.add_argument('--logs-dir', required=True)
    ap.add_argument('--artifacts-dir', default=None)
    ap.add_argument('--facts', default=None)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    facts = json.load(open(a.facts)) if a.facts and os.path.exists(a.facts) else {}
    health = fetch(a.daemon + '/api/health')

    runs = []
    for path in sorted(glob.glob(os.path.join(a.logs_dir, '*run*.log'))):
        base = os.path.basename(path)
        suffix = next((s for s in WORKFLOW_BY_SUFFIX if base.endswith(s)), None)
        wf, mode = WORKFLOW_BY_SUFFIX.get(suffix, (base, '?'))
        r = parse_log(path)
        r.update({'workflow': wf, 'mode': mode, 'log': base})
        runs.append(r)

    gates = []
    for r in runs:
        for f in r['forms']:
            g = dict(f)
            g['run'] = r['workflow']
            ans = (facts.get('gate_answers') or {}).get(f['form_id'])
            if ans:
                g['state'] = 'answered'
                g.update(ans)
            else:
                g['state'] = 'open'
            gates.append(g)

    tallies = {}
    if a.artifacts_dir:
        pmf = os.path.join(a.artifacts_dir, 'designer-layer-substrate-test-2026-08-31-pmf-review.html')
        qa = os.path.join(a.artifacts_dir, 'designer-layer-substrate-test-2026-08-31-artifact.html')
        tallies['pmf-review evidence labels'] = count_markers(pmf, ['strong', 'partial', 'assumption'])
        tallies['design-qa basis labels'] = count_markers(qa, ['Reported', 'Derived', 'Unverified'])

    totals = {
        'runs': len(runs),
        'cost': round(sum(r['cost'] or 0 for r in runs), 2),
        'out_tokens': sum(r['out_tokens'] or 0 for r in runs),
        'wall_ms': sum(r['duration_ms'] or 0 for r in runs),
    }
    data = {
        'generated': time.strftime('%Y-%m-%d %H:%M %Z'),
        'daemon': {'ok': bool(health and health.get('ok')), 'version': (health or {}).get('version')},
        'totals': totals,
        'runs': runs,
        'gates': gates,
        'recommendations': facts.get('recommendations', []),
        'contract_checks': facts.get('contract_checks', []),
        'tallies': tallies,
        'honesty': facts.get('honesty', []),
    }
    json.dump(data, open(a.out, 'w'), indent=1)
    print('WROTE', a.out, '| runs', len(runs), '| gates', len(gates))


if __name__ == '__main__':
    main()
