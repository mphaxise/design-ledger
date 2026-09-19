#!/usr/bin/env python3
"""Serve the evidence board with the write path live (docs/write-path.md).

GET  /         the board, regenerated at startup and after each decision
POST /decide   {run, gate, answer, answers, by} — validates against the
               loaded manifests, writes a decision record, posts the
               continuation to the substrate, harvests the resumed run's
               manifest when it lands, and regenerates the board.

The server binds loopback only and trusts the machine, like the daemon it
fronts. Decision records are written even when the continuation cannot be
posted; unblocking work must not depend on a daemon being up.

Python 3 standard library only. Part of design-ledger. Apache-2.0.
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BOARD = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(BOARD)
sys.path.insert(0, os.path.join(REPO, 'schema'))
import validate as manifest_validator  # noqa: E402

A = None  # parsed args, set in main()


def load_manifests():
    out = {}
    for path in sorted(glob.glob(os.path.join(A.manifests_dir, '*.json'))):
        try:
            m = json.load(open(path, encoding='utf-8'))
        except Exception:
            continue
        if m.get('manifest') == 'design-ledger/run-manifest':
            out[m['run']['id']] = m
    return out


def record_path(run_id, gate_id):
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', f'{run_id}--{gate_id}')
    return os.path.join(A.decisions_dir, f'{safe}.json')


def conversation_for(project_id):
    """Read-only lookup in the daemon's local store. No HTTP endpoint exposes
    the project-to-conversation mapping (seam request, docs/write-path.md)."""
    db = os.path.join(A.od_root, '.od', 'app.sqlite')
    try:
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True, timeout=3)
        row = con.execute(
            'SELECT id FROM conversations WHERE project_id = ? ORDER BY created_at LIMIT 1',
            (project_id,)).fetchone()
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def regen():
    data = os.path.join(BOARD, 'out', 'data.json')
    html = os.path.join(BOARD, 'out', 'board.html')
    cmd = [sys.executable, os.path.join(BOARD, 'extract.py'),
           '--daemon', A.daemon, '--logs-dir', A.logs_dir,
           '--manifests-dir', A.manifests_dir, '--decisions-dir', A.decisions_dir,
           '--out', data]
    if A.artifacts_dir:
        cmd += ['--artifacts-dir', A.artifacts_dir]
    subprocess.run(cmd, check=True)
    subprocess.run([sys.executable, os.path.join(BOARD, 'build_board.py'),
                    '--data', data, '--out', html], check=True)


def continuation_message(manifest, gate, dec):
    lines = [
        f"Praneet-side decision for gate '{gate['id']}' ({gate.get('title', '')}), "
        f"answered by {dec['by']} on {dec['at']} via the evidence board:",
        f"  {dec['answer']}",
    ]
    for qid, val in (dec.get('answers') or {}).items():
        lines.append(f'  {qid} = {json.dumps(val)}')
    lines += [
        '',
        'Resume the gated run with this answer. The workspace holds the gated',
        "run's run-manifest.json — read it, treat this gate as answered by the",
        'decision above, archive that manifest per your emission contract, and',
        'complete the deliverable and your own manifest.',
    ]
    return '\n'.join(lines)


def post_continuation(manifest, gate, dec, rec_file):
    run_id = manifest['run']['id']
    project = manifest['run'].get('project')
    conv = conversation_for(project) if project else None
    dec['continuation'] = {k: v for k, v in
                           {'project': project, 'conversation': conv,
                            'state': 'not-posted'}.items() if v is not None}
    if not project or not conv or A.no_continue:
        json.dump(dec, open(rec_file, 'w'), indent=2, ensure_ascii=False)
        return ('Decision recorded. Continuation not posted'
                + (' (--no-continue).' if A.no_continue else
                   ': no substrate project/conversation resolvable for this run.'))

    body = json.dumps({
        'agentId': A.agent, 'projectId': project, 'conversationId': conv,
        'skillId': manifest['run'].get('skill_id'), 'sessionMode': 'design',
        'message': continuation_message(manifest, gate, dec),
    }).encode()
    log_name = f'{time.strftime("%Y-%m-%d")}-resume-{re.sub(r"[^A-Za-z0-9._-]", "_", run_id)}-run.log'
    log_path = os.path.join(A.logs_dir, log_name)
    dec['continuation'].update({'state': 'posted', 'log': log_name,
                                 'posted_at': time.strftime('%Y-%m-%dT%H:%M:%S')})
    json.dump(dec, open(rec_file, 'w'), indent=2, ensure_ascii=False)

    def stream_and_harvest():
        try:
            req = urllib.request.Request(A.daemon + '/api/chat', data=body,
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=1800) as r, open(log_path, 'wb') as f:
                for chunk in iter(lambda: r.read(8192), b''):
                    f.write(chunk)
        except Exception as e:
            print(f'[serve] continuation stream ended abnormally: {e}', file=sys.stderr)
        ws_manifest = os.path.join(A.od_root, '.od', 'projects', project, 'run-manifest.json')
        try:
            schema = json.load(open(manifest_validator.SCHEMA_PATH, encoding='utf-8'))
            errors = manifest_validator.validate_file(ws_manifest, schema)
            if errors:
                print(f'[serve] harvested manifest invalid, not copied: {errors[0]}', file=sys.stderr)
            else:
                m = json.load(open(ws_manifest, encoding='utf-8'))
                if m['run']['id'] == run_id:
                    print('[serve] workspace manifest is still the gated one; nothing new to harvest', file=sys.stderr)
                else:
                    newrun = {}
                    for k, v in m['run'].items():
                        newrun[k] = v
                        if k == 'provenance':
                            newrun['log'] = log_name
                    m['run'] = newrun
                    dest = os.path.join(A.manifests_dir, re.sub(r'[^A-Za-z0-9._-]', '_', m['run']['id']) + '.json')
                    json.dump(m, open(dest, 'w'), indent=2, ensure_ascii=False)
                    open(dest, 'a').write('\n')
                    print(f'[serve] harvested {os.path.basename(dest)}')
        except FileNotFoundError:
            print('[serve] no run-manifest.json in the workspace after the run', file=sys.stderr)
        except Exception as e:
            print(f'[serve] harvest failed: {e}', file=sys.stderr)
        try:
            regen()
            print('[serve] board regenerated after continuation')
        except Exception as e:
            print(f'[serve] regen failed: {e}', file=sys.stderr)

    threading.Thread(target=stream_and_harvest, daemon=True).start()
    return ('Decision recorded and continuation posted — the resumed run is '
            'working now. Reload in a few minutes to see its manifest.')


def decide(payload):
    for key in ('run', 'gate', 'answer', 'by'):
        if not str(payload.get(key, '')).strip():
            return 400, f'Missing {key}.', False
    manifests = load_manifests()
    m = manifests.get(payload['run'])
    if not m:
        return 404, f"No manifest for run {payload['run']!r}.", False
    gate = next((g for g in m.get('gates', []) if g['id'] == payload['gate']), None)
    if not gate:
        return 404, f"Run has no gate {payload['gate']!r}.", False
    if gate.get('state') != 'open':
        return 409, 'That gate is already answered in the manifest.', False
    rec_file = record_path(payload['run'], payload['gate'])
    if os.path.exists(rec_file):
        return 409, 'A decision record for this gate already exists; a wrong answer is corrected by a new record, not from the UI.', False

    dec = {
        'record': 'design-ledger/decision-record', 'schema_version': '0.1',
        'run': payload['run'], 'gate': payload['gate'],
        'answer': str(payload['answer']),
        'answers': payload.get('answers') or {},
        'by': str(payload['by']), 'at': time.strftime('%Y-%m-%d'),
        'via': 'evidence-board', 'channel': 'board',
    }
    os.makedirs(A.decisions_dir, exist_ok=True)
    json.dump(dec, open(rec_file, 'w'), indent=2, ensure_ascii=False)
    schema = json.load(open(manifest_validator.SCHEMA_PATH, encoding='utf-8'))
    errors = manifest_validator.validate_file(rec_file, schema)
    if errors:
        os.remove(rec_file)
        return 500, f'Refused to keep an invalid decision record: {errors[0]}', False
    message = post_continuation(m, gate, dec, rec_file)
    try:
        regen()
    except Exception as e:
        message += f' (Board regen failed: {e})'
    return 200, message, True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f'[serve] {self.address_string()} {fmt % args}')

    def _send(self, code, body, ctype='text/html; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = {'/': 'board.html', '/data.json': 'data.json'}.get(self.path.split('?')[0])
        if self.path == '/health':
            return self._send(200, b'{"ok": true}', 'application/json')
        if not path:
            return self._send(404, b'not found', 'text/plain')
        full = os.path.join(BOARD, 'out', path)
        if not os.path.exists(full):
            return self._send(503, b'board not generated yet', 'text/plain')
        ctype = 'application/json' if path.endswith('.json') else 'text/html; charset=utf-8'
        self._send(200, open(full, 'rb').read(), ctype)

    def do_POST(self):
        if self.path != '/decide':
            return self._send(404, b'{}', 'application/json')
        try:
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        except Exception:
            return self._send(400, json.dumps({'message': 'Bad JSON.'}).encode(), 'application/json')
        code, message, reload_ = decide(payload)
        self._send(code, json.dumps({'message': message, 'reload': reload_}).encode(),
                   'application/json')


def main():
    global A
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifests-dir', required=True)
    ap.add_argument('--decisions-dir', default=os.path.join(BOARD, 'decisions'))
    ap.add_argument('--logs-dir', default=os.path.join(BOARD, 'out'))
    ap.add_argument('--artifacts-dir', default=None)
    ap.add_argument('--daemon', default='http://127.0.0.1:7457')
    ap.add_argument('--od-root', default=os.path.expanduser('~/src/open-design'))
    ap.add_argument('--agent', default='claude')
    ap.add_argument('--port', type=int, default=7461)
    ap.add_argument('--no-continue', action='store_true',
                    help='record decisions without posting continuations')
    A = ap.parse_args()
    for d in (A.manifests_dir, A.logs_dir):
        if not os.path.isdir(d):
            sys.exit(f'not a directory: {d}')
    regen()
    srv = ThreadingHTTPServer(('127.0.0.1', A.port), Handler)
    print(f'[serve] board live at http://127.0.0.1:{A.port} — write path armed'
          + (' (--no-continue)' if A.no_continue else ''))
    srv.serve_forever()


if __name__ == '__main__':
    main()
