"""Cover sheets: archive, module, functionality and flow. Landscape, the same palette as the flows."""
from __future__ import annotations
import datetime
from collections import defaultdict, Counter
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from . import theme as TH
from ..textutil import short, uniq

ST_T = ParagraphStyle('t', fontName=TH.BOLD, fontSize=17, leading=21, textColor=TH.INK, spaceAfter=3)
ST_S = ParagraphStyle('s', fontName=TH.FONT, fontSize=8, leading=10.5, textColor=TH.MUTED, spaceAfter=6)
ST_H = ParagraphStyle('h', fontName=TH.BOLD, fontSize=10.5, leading=13, textColor=TH.ACCENT, spaceBefore=9, spaceAfter=4)
ST_P = ParagraphStyle('p', fontName=TH.FONT, fontSize=8.2, leading=11, textColor=TH.INK, spaceAfter=4)
ST_C = ParagraphStyle('c', fontName=TH.FONT, fontSize=7.2, leading=9, textColor=TH.INK)
ST_CB = ParagraphStyle('cb', parent=ST_C, fontName=TH.BOLD)
ST_CH = ParagraphStyle('ch', parent=ST_C, fontName=TH.BOLD, textColor=TH.hexc('#FFFFFF'))


def P(t, st=ST_C):
    return Paragraph(escape(str(t if t not in (None, '') else '-')).replace('\n', '<br/>'), st)


def table(rows, widths, header=True, key_col=False):
    W = TH.PAGE[0] - 2 * TH.MARGIN
    tot = sum(widths)
    widths = [w * W / tot for w in widths]
    data = []
    for i, r in enumerate(rows):
        st = ST_CH if (header and i == 0) else None
        data.append([P(v, st or (ST_CB if key_col and j == 0 else ST_C)) for j, v in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [('GRID', (0, 0), (-1, -1), 0.4, TH.RULE), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
             ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4),
             ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5)]
    if header:
        style.append(('BACKGROUND', (0, 0), (-1, 0), TH.HEAD))
    for i in range(1 if header else 0, len(rows)):
        if i % 2 == 0:
            style.append(('BACKGROUND', (0, i), (-1, i), TH.ZEBRA))
    if key_col:
        style.append(('BACKGROUND', (0, 1 if header else 0), (0, -1), TH.hexc('#EEF2F7')))
    t.setStyle(TableStyle(style))
    return t


def _doc(path, title, author, footer):
    def on_page(c, d):
        W, H = TH.PAGE
        c.saveState()
        c.setFillColor(TH.ACCENT)
        c.rect(0, H - 10, W, 10, stroke=0, fill=1)
        c.setFillColor(TH.MUTED)
        c.setFont(TH.FONT, 6.8)
        c.drawString(TH.MARGIN, 14, footer[:180])
        c.drawRightString(W - TH.MARGIN, 14, f'Page {d.page}')
        c.restoreState()
    doc = SimpleDocTemplate(path, pagesize=TH.PAGE, leftMargin=TH.MARGIN, rightMargin=TH.MARGIN, topMargin=26, bottomMargin=30,
                            title=title, author=author, creator=author, producer=author, subject=title)
    return doc, on_page


def _flow_ref(f):
    return f'{f.id} {f.name}'


def _write(path, title, sub, story, cfg, footer):
    doc, op = _doc(path, title, cfg.get('author', ''), footer)
    head = [Paragraph(escape(title), ST_T), Paragraph(escape(sub), ST_S)]
    doc.build(head + story, onFirstPage=op, onLaterPages=op)


def _rw(flow):
    rw = defaultdict(set)
    for s in flow.sql:
        w = s.kind not in ('SELECT', 'WITH', 'SQL')
        for t in s.tables:
            rw[t].add('write' if w else 'read')
    return rw


def nature(flow):
    writes = any(s.kind not in ('SELECT', 'WITH', 'SQL') for s in flow.sql) or flow.entry.method in ('POST', 'PUT', 'DELETE', 'PATCH') \
        or any(c.name for c in flow.middle_layer if any(w in (c.target or c.name).lower() for w in ('add', 'set', 'upd', 'del', 'ins', 'cancel', 'create', 'save', 'remove')))
    return 'Includes operations' if writes else 'Display only'


# ------------------------------------------------------------------ flow
def flow_cover(project, flow, path, cfg):
    ids = {f.id: f for f in project.flows}
    tools = {t.id: t for t in project.tools}
    e = flow.entry
    rw = _rw(flow)
    rows = [['Item', 'Value'],
            ['Flow', f'{flow.id}  {flow.name}'], ['Business name', flow.business or '-'], ['Functionality', flow.functionality],
            ['Module', flow.module], ['Submodule', flow.submodule], ['Entry point', f'{e.kind.replace("_", " ")}: {e.route if e.kind != "page" else e.file}'],
            ['HTTP method', e.method or '-'], ['File', e.file], ['Handler', e.handler.split('@')[0] if e.handler else '-'],
            ['Nature', nature(flow)],
            ['Access (roles / rights)', ', '.join(flow.roles) or '-'],
            ['Request input', ', '.join(f'{n} ({s})' for s, n in flow.params) or '-'],
            ['Forms', '; '.join(f'{fm.name}: {len(fm.fields)} fields' for fm in flow.forms) or '-'],
            ['Templates', ', '.join(flow.templates) or '-'],
            ['Files (includes, classes, templates)', ', '.join(flow.files[1:]) or '-'],
            ['Functions reached', ', '.join(k.split('@')[0] for k in flow.functions[:40]) + (f' (+{len(flow.functions) - 40})' if len(flow.functions) > 40 else '') or '-'],
            ['Tables', ', '.join(f'{t} ({"/".join(sorted(v))})' for t, v in rw.items()) or '-'],
            ['Stored procedures', ', '.join(flow.procedures) or '-'],
            ['Middle-layer calls', ', '.join(uniq(c.name + (f" '{c.target}'" if c.target else '') for c in flow.middle_layer)) or '-'],
            ['Connections', ', '.join(flow.connections) or '-'],
            ['Tools', ', '.join(f'{t} {tools[t].name}' for t in flow.tools if t in tools) or '-'],
            ['Dependencies', ', '.join(f'{t} {tools[t].name}' for t in flow.dependencies if t in tools) or '-'],
            ['Upstream dependencies (flows it depends on)', ', '.join(_flow_ref(ids[u]) for u in flow.upstream) or 'None'],
            ['Downstream dependencies (flows that depend on it)', ', '.join(_flow_ref(ids[d]) for d in flow.downstream) or 'None'],
            ['Outputs', ', '.join(f'template {n}' if k == 'template' else {'html': 'HTML page', 'json': 'JSON response'}.get(k, f'{k} {n}') for k, n, _ in flow.outputs) or '-'],
            ['Source', {'code': 'code', 'ocr': 'photos of the code', 'sonar': 'SonarQube'}.get(flow.origin, flow.origin)]]
    if flow.issues:
        cnt = Counter(i.get('severity', '') for i in flow.issues)
        rows.append(['SonarQube issues', ', '.join(f'{v} {k.lower() or "unrated"}' for k, v in cnt.most_common())])
    story = [Paragraph('Flow facts', ST_H), table(rows, [150, 560], key_col=True)]
    dep = [['Direction', 'Flow', 'Name', 'How', 'Through']]
    for a, b, kind, via in project.edges:
        if b == flow.id:
            dep.append(['Upstream', a, ids[a].name, kind, via])
        elif a == flow.id:
            dep.append(['Downstream', b, ids[b].name, kind, via])
    if len(dep) == 1:
        dep.append(['-', 'None', '', '', ''])
    story += [Paragraph('Upstream and downstream dependencies', ST_H), table(dep, [70, 60, 230, 80, 270])]
    calls = [['Level', 'Call', 'Arguments', 'Resolved to', 'Where']]
    for d, c, k in flow.calls[:150]:
        fn = project.functions.get(k)
        calls.append([str(d), c.name, short(c.args, 120), (k.split('@')[0] if k else 'library / framework'),
                      f'{fn.file}:{fn.line}' if fn else (f'{c.file}:{c.line}' if c.line else c.file)])
    if len(calls) > 1:
        story += [Paragraph('Calls with their arguments', ST_H), table(calls, [36, 170, 220, 150, 150])]
    if flow.sql:
        sq = [['Statement', 'Tables / procedure', 'Parameters', 'SQL', 'Function']]
        for s in flow.sql:
            sq.append([s.kind, s.procedure or ', '.join(s.tables), ', '.join(s.params[:10]), short(s.text, 380), s.function or s.file])
        story += [Paragraph('Database access', ST_H), table(sq, [55, 130, 90, 330, 120])]
    if flow.forms:
        ff = [['Form', 'Field', 'Type', 'Label', 'Rules', 'Options']]
        for fm in flow.forms:
            for x in fm.fields:
                rules = ', '.join(r for r in ('required' if x.required else '', f'max {x.maxlength}' if x.maxlength else '', f'pattern {x.pattern}' if x.pattern else '') if r)
                opts = '; '.join(f'{o.value}={o.label}' for o in x.options)
                if x.options_source:
                    opts = (opts + '; ' if opts else '') + f'from code: {x.options_source}'
                ff.append([fm.name, x.name, x.kind, x.label, rules, opts])
        story += [Paragraph('Fields and dropdowns', ST_H), table(ff, [80, 90, 50, 120, 90, 280])]
    if flow.messages:
        story += [Paragraph('Validation and user messages', ST_H), table([['Message']] + [[m] for m in flow.messages], [710])]
    _write(path, f'{flow.id}  {flow.name}', f'Flow cover sheet  |  {flow.functionality}  |  {cfg.get("project", "")}', story, cfg,
           f'{cfg.get("project", "")}  |  {flow.id} cover sheet')


# ------------------------------------------------------------------ functionality
def functionality_cover(project, name, flows, path, cfg):
    ids = {f.id: f for f in project.flows}
    tools = {t.id: t for t in project.tools}
    rows = [['Flow', 'Name', 'Entry point', 'Method', 'Nature', 'Upstream', 'Downstream']]
    for f in flows:
        e = f.entry
        rows.append([f.id, f.name, e.route if e.kind != 'page' else e.file, e.method or '-', nature(f), ', '.join(f.upstream) or '-', ', '.join(f.downstream) or '-'])
    mine = {f.id for f in flows}
    up = sorted({ids[u].functionality for f in flows for u in f.upstream if u not in mine})
    down = sorted({ids[d].functionality for f in flows for d in f.downstream if d not in mine})
    tbl = defaultdict(set)
    for f in flows:
        for t, v in _rw(f).items():
            tbl[t] |= v
    facts = [['Item', 'Value'], ['Functionality', name], ['Module', flows[0].module], ['Submodule', flows[0].submodule], ['Flows', str(len(flows))],
             ['Upstream functionalities', ', '.join(up) or 'None'], ['Downstream functionalities', ', '.join(down) or 'None'],
             ['Tables', ', '.join(f'{t} ({"/".join(sorted(v))})' for t, v in sorted(tbl.items())) or '-'],
             ['Stored procedures', ', '.join(sorted({p for f in flows for p in f.procedures})) or '-'],
             ['Middle-layer calls', ', '.join(sorted({c.name + (f" '{c.target}'" if c.target else '') for f in flows for c in f.middle_layer})) or '-'],
             ['Tools', ', '.join(f'{t} {tools[t].name}' for t in sorted({t for f in flows for t in f.tools})) or '-'],
             ['Dependencies', ', '.join(f'{t} {tools[t].name}' for t in sorted({t for f in flows for t in f.dependencies})) or '-']]
    story = [Paragraph('Functionality facts', ST_H), table(facts, [150, 560], key_col=True),
             Paragraph('Flows of this functionality', ST_H), table(rows, [55, 190, 210, 50, 80, 60, 60])]
    _write(path, name, f'Functionality cover sheet  |  {flows[0].module}  |  {cfg.get("project", "")}', story, cfg,
           f'{cfg.get("project", "")}  |  {name} cover sheet')


# ------------------------------------------------------------------ module
def module_cover(project, module, flows, path, cfg):
    tools = {t.id: t for t in project.tools}
    byf = defaultdict(list)
    for f in flows:
        byf[f.functionality].append(f)
    rows = [['Functionality', 'Submodule', 'Flows', 'Display only', 'Includes operations', 'Tables']]
    for name, fl in byf.items():
        rows.append([name, fl[0].submodule, ', '.join(f.id for f in fl), str(sum(nature(f) == 'Display only' for f in fl)),
                     str(sum(nature(f) != 'Display only' for f in fl)), ', '.join(sorted({t for f in fl for t in f.tables}))[:300] or '-'])
    used = Counter(t for f in flows for t in f.tools + f.dependencies)
    trows = [['Tool', 'Type', 'Flows in this module', 'Functions']]
    for t in project.tools:
        if t.id in used:
            trows.append([f'{t.id} {t.name}', t.kind, str(used[t.id]), ', '.join(t.functions[:12]) + (' ...' if len(t.functions) > 12 else '')])
    frows = [['Flow', 'Name', 'Functionality', 'Entry point']]
    for f in flows:
        frows.append([f.id, f.name, f.functionality, f.entry.route if f.entry.kind != 'page' else f.entry.file])
    facts = [['Item', 'Value'], ['Module', module], ['Functionalities', str(len(byf))], ['Flows', str(len(flows))],
             ['Tables', str(len({t for f in flows for t in f.tables}))], ['Stored procedures', str(len({p for f in flows for p in f.procedures}))]]
    story = [Paragraph('Module facts', ST_H), table(facts, [150, 560], key_col=True),
             Paragraph('Functionalities', ST_H), table(rows, [170, 90, 160, 55, 70, 165]),
             Paragraph('Tooling for this module', ST_H), table(trows, [170, 70, 70, 400]),
             Paragraph('All flows', ST_H), table(frows, [55, 220, 180, 255])]
    _write(path, module, f'Module cover sheet  |  {cfg.get("project", "")}', story, cfg, f'{cfg.get("project", "")}  |  {module} module cover sheet')


# ------------------------------------------------------------------ archive
def archive_cover(project, path, cfg, layout_lines):
    flows = project.flows
    mods = defaultdict(list)
    for f in flows:
        mods[f.module].append(f)
    facts = [['Item', 'Value'], ['Application', cfg.get('project', '')], ['Author', cfg.get('author', '') or '-'],
             ['Date', datetime.date.today().isoformat()], ['Modules', str(len(mods))],
             ['Functionalities', str(len({f.functionality for f in flows}))], ['Flows', str(len(flows))],
             ['Source files', str(len(project.files))],
             ['Tables', str(len({t for f in flows for t in f.tables}))], ['Stored procedures', str(len({p for f in flows for p in f.procedures}))],
             ['Tools', str(sum(t.kind != 'Dependency' for t in project.tools))], ['Dependencies', str(sum(t.kind == 'Dependency' for t in project.tools))]]
    langs = Counter(sf.language for sf in project.files.values())
    facts.append(['Languages', ', '.join(f'{k} {v}' for k, v in langs.most_common() if k not in ('other', 'json', 'xml'))])
    mrows = [['Module', 'Functionalities', 'Flows', 'Display only', 'Includes operations']]
    for m, fl in sorted(mods.items()):
        mrows.append([m, str(len({f.functionality for f in fl})), str(len(fl)), str(sum(nature(f) == 'Display only' for f in fl)), str(sum(nature(f) != 'Display only' for f in fl))])
    trows = [['Tool', 'Type', 'Flows', 'Functionalities']]
    for t in project.tools:
        if t.kind != 'Dependency':
            trows.append([f'{t.id} {t.name}', t.kind, str(len(t.flows)), str(len(t.functionalities))])
    mn = cfg.get('tool_min_flows', 3)
    story = [Paragraph('Archive facts', ST_H), table(facts, [150, 560], key_col=True),
             Paragraph('Modules', ST_H), table(mrows, [250, 110, 110, 110, 130]),
             Paragraph('Tooling overview', ST_H),
             Paragraph(escape(f'A tool is a function that several flows use ({mn} or more flows). A dependency is a function, include or class that fewer than {mn} flows use. '
                              f'Platform tools are used by almost every flow. The full lists are in the Tooling workbook.'), ST_P),
             table(trows, [300, 110, 110, 190]),
             Paragraph('How the archive is organised', ST_H)] + [Paragraph(escape('• ' + l), ST_P) for l in layout_lines]
    _write(path, cfg.get('project', '') or 'Application', 'As-is functional and architecture archive', story, cfg,
           f'{cfg.get("project", "")}  |  archive cover sheet')
