#!/usr/bin/env python3
"""Extract evidence objects from run manifests, the daemon API, and SSE logs.

v0.1: run manifests (schema/run-manifest.schema.json) are the primary source
for findings, assumptions, gates, decisions, recommendations, and contract
checks. SSE logs stay authoritative for what the substrate measured: status,
cost, tokens, wall time. The two are joined by the manifest's run.log hint
(backfills) or run.session_id (emitted manifests). Facts files are retired;
the session records that fed them now travel as backfilled manifests.

Every manifest is checked against the schema before use; an invalid manifest
is excluded and reported rather than rendered.

Python 3 standard library only. The board renders from logs and manifests
alone when the daemon is offline.

Part of design-ledger. Apache-2.0.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, 'schema'))
import validate as manifest_validator  # noqa: E402

# Fallback mapping for logs that have no manifest. Generic fallback: the
# basename itself. Emission from runs replaces this entirely.
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
    """Substrate-measured facts plus raw question-forms from one SSE log."""
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
        'substrate_status': (end or {}).get('status'),
        'artifacts': (end or {}).get('artifactPaths') or [],
        'duration_ms': (usage or {}).get('durationMs'),
        'out_tokens': u.get('output_tokens'),
        'cost': (usage or {}).get('costUsd'),
        'forms': forms,
    }


def load_manifests(mdir, notes):
    """Load, schema-check, and index manifests by log hint."""
    schema = json.load(open(manifest_validator.SCHEMA_PATH, encoding='utf-8'))
    manifests, rejected = [], 0
    for path in sorted(glob.glob(os.path.join(mdir, '*.json'))):
        try:
            m = json.load(open(path, encoding='utf-8'))
        except Exception:
            continue
        if m.get('manifest') != 'design-ledger/run-manifest':
            continue
        errors = manifest_validator.validate_file(path, schema)
        if errors:
            rejected += 1
            print(f'REJECTED {os.path.basename(path)}: {errors[0]}', file=sys.stderr)
            continue
        manifests.append(m)
    if rejected:
        notes.append(f'{rejected} manifest file(s) failed schema validation and are excluded from this board.')
    return manifests


def load_decision_records(ddir, notes):
    """Human decision records from the write path (docs/write-path.md)."""
    schema = json.load(open(manifest_validator.SCHEMA_PATH, encoding='utf-8'))
    records, rejected = [], 0
    for path in sorted(glob.glob(os.path.join(ddir, '*.json'))):
        try:
            r = json.load(open(path, encoding='utf-8'))
        except Exception:
            continue
        if r.get('record') != 'design-ledger/decision-record':
            continue
        errors = manifest_validator.validate_file(path, schema)
        if errors:
            rejected += 1
            print(f'REJECTED {os.path.basename(path)}: {errors[0]}', file=sys.stderr)
            continue
        records.append(r)
    if rejected:
        notes.append(f'{rejected} decision record(s) failed validation and are excluded from this board.')
    return records


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
    ap.add_argument('--manifests-dir', default=None)
    ap.add_argument('--decisions-dir', default=None)
    ap.add_argument('--artifacts-dir', default=None)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    notes = []
    health = fetch(a.daemon + '/api/health')
    manifests = load_manifests(a.manifests_dir, notes) if a.manifests_dir else []
    records = load_decision_records(a.decisions_dir, notes) if a.decisions_dir else []
    by_log = {m['run'].get('log'): m for m in manifests if m['run'].get('log')}

    # Runs: one row per log, joined to its manifest when one names it.
    runs, unmatched_logs = [], 0
    seen_manifests = set()
    for path in sorted(glob.glob(os.path.join(a.logs_dir, '*run*.log'))):
        base = os.path.basename(path)
        r = parse_log(path)
        r['log'] = base
        m = by_log.get(base)
        if m:
            seen_manifests.add(m['run']['id'])
            r.update({
                'run_id': m['run']['id'],
                'workflow': m['run']['workflow'],
                'mode': m['run'].get('mode', '?'),
                'status': m['run']['status'],
                'provenance': m['run']['provenance'],
                'resumes': m['run'].get('resumes'),
            })
            if m.get('artifacts'):
                r['artifacts'] = [art['path'] for art in m['artifacts']]
        else:
            unmatched_logs += 1
            suffix = next((s for s in WORKFLOW_BY_SUFFIX if base.endswith(s)), None)
            wf, mode = WORKFLOW_BY_SUFFIX.get(suffix, (base, '?'))
            r.update({'run_id': None, 'workflow': wf, 'mode': mode,
                      'status': r['substrate_status'], 'provenance': None})
        runs.append(r)
    # Manifests whose log is absent still describe runs.
    for m in manifests:
        if m['run']['id'] in seen_manifests:
            continue
        runs.append({
            'log': m['run'].get('log'), 'run_id': m['run']['id'],
            'workflow': m['run']['workflow'], 'mode': m['run'].get('mode', '?'),
            'status': m['run']['status'], 'provenance': m['run']['provenance'],
            'resumes': m['run'].get('resumes'), 'substrate_status': None,
            'artifacts': [art['path'] for art in m.get('artifacts', [])],
            'duration_ms': None, 'out_tokens': None, 'cost': None, 'forms': [],
        })
    if unmatched_logs:
        notes.append(f'{unmatched_logs} log(s) have no manifest; their rows carry substrate stats only and workflow names guessed from filenames.')

    # Objects, flattened with run identity and provenance.
    findings, assumptions, gates, decisions, recs, checks = [], [], [], [], [], []
    for m in manifests:
        rid, prov = m['run']['id'], m['run']['provenance']
        decisions_by_id = {d['id']: d for d in m.get('decisions', [])}
        for f in m.get('findings', []):
            findings.append({**f, 'run': rid, 'provenance': prov})
        for s in m.get('assumptions', []):
            assumptions.append({**s, 'run': rid, 'provenance': prov})
        for g in m.get('gates', []):
            row = {
                'gate_id': g['id'], 'title': g['title'], 'kind': g.get('kind'),
                'blocking': g.get('blocking', True), 'state': g['state'],
                'questions': g.get('questions', []),
                'run': rid, 'provenance': prov,
            }
            d = decisions_by_id.get(g.get('decision'))
            if d:
                row.update({'answer': d['answer'], 'by': d['by'],
                            'on': d['at'], 'via': d.get('via')})
            gates.append(row)
        for d in m.get('decisions', []):
            decisions.append({**d, 'run': rid, 'provenance': prov})
        for rec in m.get('recommendations', []):
            recs.append({'run': rid, 'text': rec['text'],
                         'state': rec.get('state', 'awaiting-decision'),
                         'source': rec.get('artifact'), 'provenance': prov})
        c = m.get('contract')
        if c:
            held_all = all(i.get('held') for i in c.get('items', []))
            checks.append({'run': rid, 'held': held_all,
                           'declared_by': c['declared_by'],
                           'items': c.get('items', [])})
        for lim in m.get('limits', []):
            notes.append(f'{rid}: {lim}')

    # Human decision records answer open gates without touching manifests.
    # A manifest that already records the gate answered wins; a disagreement
    # between the two surfaces in the honesty section rather than hiding.
    by_run_gate = {(r['run'], r['gate']): r for r in records}
    for g in gates:
        rec = by_run_gate.get((g['run'], g['gate_id']))
        if not rec:
            continue
        if g['state'] == 'open':
            g.update({'state': 'answered', 'answer': rec['answer'],
                      'by': rec['by'], 'on': rec['at'], 'via': rec.get('via'),
                      'answered_by': 'decision-record'})
        elif g.get('answer') and g['answer'] != rec['answer']:
            notes.append(f"{g['run']} / {g['gate_id']}: the run's manifest and a decision record disagree on the answer; showing the manifest's.")
    for rec in records:
        decisions.append({'id': f"record:{rec['run']}--{rec['gate']}",
                          'gate': rec['gate'], 'answer': rec['answer'],
                          'by': rec['by'], 'at': rec['at'], 'via': rec.get('via'),
                          'channel': rec.get('channel', 'board'),
                          'run': rec['run'], 'provenance': 'decision-record'})

    # A gate answered by a resumed run supersedes its open instance from the
    # gated run. Both stay on the board as history; the open one is marked.
    answered_ids = {g['gate_id'] for g in gates if g['state'] == 'answered'}
    for g in gates:
        if g['state'] == 'open' and g['gate_id'] in answered_ids:
            g['superseded'] = True

    # Gates parsed from logs for runs without manifests, so nothing hides.
    manifest_gate_keys = {(g['run'], g['gate_id']) for g in gates}
    for r in runs:
        if r.get('run_id'):
            continue
        for f in r.get('forms', []):
            if (None, f['form_id']) in manifest_gate_keys:
                continue
            gates.append({'gate_id': f['form_id'], 'title': f['title'],
                          'kind': None, 'blocking': True, 'state': 'open',
                          'questions': f['questions'], 'run': r['workflow'],
                          'provenance': None})

    tallies = {}
    if a.artifacts_dir:
        pmf = os.path.join(a.artifacts_dir, 'designer-layer-substrate-test-2026-08-31-pmf-review.html')
        qa = os.path.join(a.artifacts_dir, 'designer-layer-substrate-test-2026-08-31-artifact.html')
        tallies['pmf-review evidence labels'] = count_markers(pmf, ['strong', 'partial', 'assumption'])
        tallies['design-qa basis labels'] = count_markers(qa, ['Reported', 'Derived', 'Unverified'])
        notes.append('Marker tallies are case-insensitive string counts over artifact files; the schema-backed objects above are the parsed data.')

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
        'findings': findings,
        'assumptions': assumptions,
        'gates': gates,
        'decisions': decisions,
        'recommendations': recs,
        'contract_checks': checks,
        'tallies': tallies,
        'honesty': notes,
    }
    json.dump(data, open(a.out, 'w'), indent=1)
    print('WROTE', a.out, '| runs', len(runs), '| manifests', len(manifests),
          '| findings', len(findings), '| gates', len(gates))


if __name__ == '__main__':
    main()
