#!/usr/bin/env python3
"""Validate run manifests against schema/run-manifest.schema.json.

Two passes. Pass one interprets the subset of JSON Schema the schema file
actually uses (type, required, properties, items, enum, const, pattern,
minimum, $ref into $defs), so the schema file stays the single source of
truth for shapes and enums. Pass two checks what JSON Schema cannot say:
id uniqueness, cross-references, gate/decision agreement, run-status
consistency, and artifact path safety.

Python 3 standard library only. Exit 0 when every file passes.

Usage: python3 schema/validate.py schema/examples/*.json
Part of design-ledger. Apache-2.0.
"""
import json
import os
import re
import sys

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'run-manifest.schema.json')

TYPES = {
    'object': dict, 'array': list, 'string': str,
    'boolean': bool, 'integer': int,
}


class Checker:
    def __init__(self, schema):
        self.schema = schema
        self.defs = schema.get('$defs', {})
        self.errors = []

    def err(self, path, msg):
        self.errors.append(f'{path}: {msg}')

    def resolve(self, node):
        while '$ref' in node:
            name = node['$ref'].rsplit('/', 1)[-1]
            node = self.defs[name]
        return node

    def check(self, node, value, path):
        node = self.resolve(node)
        if 'const' in node:
            if value != node['const']:
                self.err(path, f'must be {node["const"]!r}, got {value!r}')
            return
        if 'enum' in node:
            if value not in node['enum']:
                self.err(path, f'{value!r} not in {node["enum"]}')
            return
        t = node.get('type')
        if t:
            py = TYPES[t]
            if not isinstance(value, py) or (py is int and isinstance(value, bool)):
                self.err(path, f'expected {t}, got {type(value).__name__}')
                return
        if t == 'string':
            pat = node.get('pattern')
            if pat and not re.search(pat, value):
                self.err(path, f'{value!r} does not match {pat!r}')
        if t == 'integer' and 'minimum' in node and value < node['minimum']:
            self.err(path, f'{value} below minimum {node["minimum"]}')
        if t == 'object':
            for req in node.get('required', []):
                if req not in value:
                    self.err(path, f'missing required key {req!r}')
            for key, sub in node.get('properties', {}).items():
                if key in value:
                    self.check(sub, value[key], f'{path}.{key}')
        if t == 'array' and 'items' in node:
            for i, item in enumerate(value):
                self.check(node['items'], item, f'{path}[{i}]')


def consistency(m, err):
    """Rules the schema cannot express."""
    ids = {}
    for coll in ('artifacts', 'findings', 'assumptions', 'gates',
                 'decisions', 'recommendations'):
        seen = set()
        for i, obj in enumerate(m.get(coll, [])):
            oid = obj.get('id')
            if not isinstance(oid, str):
                continue
            if oid.lower() in seen:
                err(f'{coll}[{i}]', f'duplicate id {oid!r}')
            seen.add(oid.lower())
        ids[coll] = seen

    def ref(coll, i, field, target):
        val = m.get(coll, [])[i].get(field)
        if isinstance(val, str) and val.lower() not in ids[target]:
            err(f'{coll}[{i}].{field}', f'{val!r} not found in {target}')

    for coll in ('findings', 'assumptions', 'recommendations'):
        for i, obj in enumerate(m.get(coll, [])):
            if 'artifact' in obj:
                ref(coll, i, 'artifact', 'artifacts')

    for i, gate in enumerate(m.get('gates', [])):
        state = gate.get('state')
        if state == 'answered':
            if 'decision' not in gate:
                err(f'gates[{i}]', 'answered gate has no decision id')
            else:
                ref('gates', i, 'decision', 'decisions')
        if state == 'open' and 'decision' in gate:
            err(f'gates[{i}]', 'open gate carries a decision id')

    gate_states = {g.get('id'): g.get('state') for g in m.get('gates', [])}
    for i, d in enumerate(m.get('decisions', [])):
        ref('decisions', i, 'gate', 'gates')
        if gate_states.get(d.get('gate')) == 'open':
            err(f'decisions[{i}]', 'decides a gate still marked open')

    run = m.get('run', {})
    blocking_open = [
        g.get('id') for g in m.get('gates', [])
        if g.get('state') == 'open' and g.get('blocking', True)
    ]
    if run.get('status') == 'gated' and not blocking_open:
        err('run.status', 'gated but no blocking gate is open')
    if run.get('status') == 'completed' and blocking_open:
        err('run.status', f'completed with blocking gates open: {blocking_open}')
    if run.get('resumes') == run.get('id'):
        err('run.resumes', 'run cannot resume itself')

    for i, a in enumerate(m.get('artifacts', [])):
        p = a.get('path', '')
        if isinstance(p, str) and ('..' in p or p.startswith(('/', '~'))):
            err(f'artifacts[{i}].path', f'{p!r} must be workspace-relative')


def validate_file(path, schema):
    c = Checker(schema)
    try:
        m = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return [f'$: not valid JSON ({e})']
    c.check(schema, m, '$')
    if isinstance(m, dict):
        consistency(m, lambda p, msg: c.err(p, msg))
    return c.errors


def main():
    files = sys.argv[1:]
    if not files:
        print(__doc__.strip().splitlines()[0])
        print('usage: python3 schema/validate.py <manifest.json> [...]')
        return 2
    schema = json.load(open(SCHEMA_PATH, encoding='utf-8'))
    failed = 0
    for path in files:
        errors = validate_file(path, schema)
        if errors:
            failed += 1
            print(f'FAIL {path}')
            for e in errors:
                print(f'  {e}')
        else:
            print(f'OK   {path}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
