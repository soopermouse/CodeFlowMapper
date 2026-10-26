"""Functional flow of one flow: entry, access check, request input, every form with every field, every dropdown with
each option, decisions with what each case does, calls with their arguments and what they reach (SQL, stored
procedures, middle layer), validation and user messages, output, and the flows it leads to."""
from __future__ import annotations
import re
from collections import defaultdict
from .chart import Chart, N, D
from ..textutil import short, uniq

SRC = {'GET': 'query string', 'POST': 'form post', 'REQUEST': 'query or form', 'COOKIE': 'cookie', 'SESSION': 'session',
       'FILES': 'uploaded file', 'query': 'query string', 'body': 'request body', 'path': 'URL path', 'form': 'form post',
       'header': 'header', 'cookie': 'cookie', 'request': 'request parameter', 'querystring': 'query string'}


def field_line(x):
    bits = [f'{x.name or "(no name)"} ({x.kind})']
    if x.label and x.label != x.name:
        bits.append(f'label "{x.label}"')
    if x.required:
        bits.append('required')
    if x.maxlength:
        bits.append(f'max length {x.maxlength}')
    if x.pattern:
        bits.append(f'pattern {x.pattern}')
    if x.default and x.kind not in ('submit', 'button'):
        bits.append(f'value "{short(x.default, 40)}"')
    return ', '.join(bits)


def _fn_lines(project, key, depth_calls):
    """what a reached function does: its SQL, stored procedures, middle-layer calls and the calls it makes."""
    fn = project.functions.get(key)
    lines = []
    if not fn:
        return lines
    for s in fn.sql[:6]:
        tgt = s.procedure or ', '.join(s.tables)
        lines.append(f'SQL {s.kind} {tgt}: {short(s.text, 150)}')
    for c in depth_calls.get(key, [])[:10]:
        nm, args, k = c
        lines.append(f'{"" if nm.startswith("middle layer") else "calls "}{nm}({short(args, 70)})' + (f' {k}' if k else ''))
    if fn.messages:
        lines.append('messages: ' + '; '.join(f'"{m}"' for m, _ in fn.messages[:3]))
    return lines


def build(project, flow, path, cfg):
    e = flow.entry
    title = f'{flow.id}  {flow.name}'
    sub = f'Functional flow  |  {flow.functionality}'
    ch = Chart(path, title, sub, cfg.get('author', ''), f'{cfg.get("project", "")}  |  {flow.id} functional flow (as is)')
    ids = {f.id: f for f in project.flows}
    # 1 entry
    where = e.route if e.kind != 'page' else e.file
    lines = [f'{e.kind.replace("_", " ")}: {where}']
    if e.method:
        lines.append(f'HTTP method: {e.method}')
    if e.file != where:
        lines.append(f'file: {e.file}')
    if e.handler and e.handler in project.functions:
        fn = project.functions[e.handler]
        lines.append(f'handler: {fn.key.split("@")[0]}({short(fn.params, 90)})  line {fn.line}')
    if flow.case:
        lines.append(f'case "{flow.case[1]}" of switch ({flow.case[0]})')
    if flow.upstream:
        lines.append('reached from: ' + ', '.join(f'{u} {ids[u].name}' for u in flow.upstream[:6]))
    ch.add(N('start', 'Entry', lines))
    # 2 access
    if flow.roles:
        ch.add(N('access', 'Access check', [f'role / right: {r}' for r in flow.roles[:12]]))
    # 3 input
    if flow.params:
        by = defaultdict(list)
        for src, name in flow.params:
            by[SRC.get(src, src)].append(name)
        ch.add(N('input', 'Request input', [f'{k}: {", ".join(uniq(v))}' for k, v in by.items()]))
    # 4 forms and dropdowns
    for fm in flow.forms:
        head = f'Form {fm.name}' + (f'  ({fm.method} -> {fm.action})' if fm.action or fm.method else '')
        lines = [field_line(x) for x in fm.fields]
        ch.add(N('form', head, lines + ([f'source: {fm.file}'] if fm.file else [])))
        for x in fm.fields:
            if x.kind == 'select' or x.options:
                ol = []
                for o in x.options:
                    ol.append(f'"{o.label}"  (value {o.value or "empty"})' + ('  selected by default' if o.selected else ''))
                if x.options_source:
                    ol.append(f'options filled by the code: {x.options_source}')
                if not ol:
                    ol.append('no options in the markup')
                ch.add(N('dropdown', f'Dropdown {x.name}' + (f' "{x.label}"' if x.label else ''), ol))
    # 5 decisions
    depth_calls = defaultdict(list)
    for d, c, k in flow.calls:
        pass
    # calls made by each reached function (one level, for the boxes)
    for k in flow.functions:
        fn = project.functions.get(k)
        if fn:
            ml = {(c.name, c.line) for c in fn.calls if c.kind == 'middle_layer'}
            for c in fn.calls:
                if re.search(r'Exception\b', c.name) or (c.kind != 'middle_layer' and (c.name, c.line) in ml):
                    continue
                t = c.target or ''
                if c.kind == 'middle_layer':
                    depth_calls[k].append((f'middle layer {c.name}', c.args, f"'{t}'" if t else ''))
                elif t or (('::' in c.name or '.' in c.name) and c.kind not in ('local',) and not c.name.startswith('$')):
                    depth_calls[k].append((t.split('@')[0] if t else c.name, c.args, ''))
            depth_calls[k] = uniq(depth_calls[k])
    for b in flow.branch_detail:
        lanes = []
        for cs in b['cases']:
            items = []
            seen_ml = set()
            for nm, args, k in cs['calls']:
                if re.search(r'Exception\b', nm):
                    continue
                lines = _fn_lines(project, k, depth_calls) if k else []
                title = (k.split('@')[0] if k else nm)
                items.append(N('middle' if re.search(r'requestML|RPC::|KML::|soap|rpc', nm, re.I) else 'call', f'{title}({short(args, 60)})', lines))
            for kind, tables, proc in cs['sql']:
                items.append(N('data', f'SQL {kind}', [proc or ', '.join(tables)]))
            for m in cs['messages']:
                items.append(N('message', 'Message', [f'"{m}"']))
            for u in cs['links']:
                items.append(N('link', 'Goes to', [u]))
            if not items:
                items.append(N('note', 'No call in this case', []))
            lanes.append((cs['label'], items))
        if lanes:
            q = f'{"switch" if b["kind"] == "switch" else "if"} ({b["subject"]})'
            ch.add(D(q, lanes))
    # 6 calls (top level, outside the decisions already drawn)
    shown = {x for b in flow.branch_detail for cs in b['cases'] for nm, _, k in cs['calls'] for x in (nm, k) if x}
    for d, c, k in flow.calls:
        if d != 0 or c.name in shown or (k and k in shown) or re.search(r'Exception\b', c.name):
            continue
        shown.add(c.name)
        if c.kind == 'middle_layer':
            ch.add(N('middle', f'Middle layer: {c.name}', [f'target: {c.target}' if c.target else '', f'arguments: {short(c.args, 160)}']))
            continue
        lines = [f'arguments: {short(c.args, 160)}'] if c.args else []
        if k and k != c.name:
            fn = project.functions.get(k)
            lines.append(f'resolved to {k.split("@")[0]}' + (f' ({fn.file}, line {fn.line})' if fn else ''))
        lines += _fn_lines(project, k, depth_calls) if k else ['library / framework call']
        ch.add(N('call', f'Call {c.name}', [l for l in lines if l]))
    # 7 data
    for s in flow.sql:
        tgt = s.procedure or ', '.join(s.tables) or '-'
        lines = [f'{"stored procedure" if s.procedure else "tables"}: {tgt}']
        if s.params:
            lines.append('parameters: ' + ', '.join(s.params[:12]))
        lines.append(f'statement: {short(s.text, 300)}')
        lines.append(f'in {s.function or s.file}' + (f', line {s.line}' if s.line else ''))
        ch.add(N('data', f'Database {s.kind}', lines))
    for c in flow.middle_layer:
        if c.name in shown:
            continue
        shown.add(c.name)
        ch.add(N('middle', f'Middle layer: {c.name}', [x for x in (f'target: {c.target}' if c.target else '', f'arguments: {short(c.args, 160)}', f'{c.file}, line {c.line}') if x]))
    if flow.connections:
        ch.add(N('data', 'Connections', flow.connections[:10]))
    # 8 messages
    if flow.messages:
        ch.add(N('message', 'Validation and user messages', [f'"{m}"' for m in flow.messages[:30]]))
    # 9 output
    outs = []
    for kind, name, line in flow.outputs:
        outs.append({'template': f'renders template {name}', 'json': 'returns JSON', 'download': f'sends a file ({name})', 'html': 'returns the HTML page'}.get(kind, f'{kind} {name}'))
    for t in flow.templates:
        if not any(t in o for o in outs):
            outs.append(f'template file {t}')
    if outs:
        ch.add(N('output', 'Output', uniq(outs)))
    # 10 next
    nxt = []
    for u, kind, line in flow.links[:20]:
        nxt.append(f'{kind}: {u}')
    if flow.downstream:
        nxt.append('flows reached: ' + ', '.join(f'{d} {ids[d].name}' for d in flow.downstream[:8]))
    if nxt:
        ch.add(N('link', 'Next', nxt))
    ch.add(N('end', 'End', []))
    return ch.save()
