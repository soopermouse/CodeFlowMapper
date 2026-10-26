"""Architectural as-is flow of one flow: four lanes (presentation, application logic, integration, data) with the
components the flow touches, the connections between the lanes, and the upstream / downstream flows."""
from __future__ import annotations
import re
from collections import defaultdict, OrderedDict
from reportlab.pdfgen import canvas as rl_canvas
from . import theme as TH
from .chart import wrap
from ..textutil import short, uniq

FS = 6.9
LEAD = 8.4


def _lanes(project, flow):
    e = flow.entry
    pres, app, integ, data = [], [], [], []
    where = e.route if e.kind != 'page' else e.file
    pres.append((e.kind.replace('_', ' ').capitalize(), [where] + ([f'method {e.method}'] if e.method else []) + ([e.file] if e.file != where else [])))
    for fm in flow.forms:
        pres.append((f'Form {fm.name}', [f'{len(fm.fields)} fields' + (f', posts to {fm.action}' if fm.action else ''), fm.file]))
    for t in flow.templates:
        pres.append(('Template', [t]))
    by_file = OrderedDict()
    for k in flow.functions:
        fn = project.functions.get(k)
        if fn:
            by_file.setdefault(fn.file, []).append(fn.key.split('@')[0].split('#')[0])
    for f in flow.files:
        if f not in by_file and f != e.file and f not in flow.templates:
            by_file.setdefault(f, [])
    for f, fns in by_file.items():
        sf = project.files.get(f)
        app.append((f, [x + '()' for x in uniq(fns)] or ['included']))
    ext = defaultdict(list)
    mlnames = {c.name for c in flow.middle_layer}
    for d, c, k in flow.calls:
        if c.kind == 'middle_layer' or c.name in mlnames or re.search(r'Exception\b', c.name):
            continue
        if not k:
            cls = re.split(r'::|->|\.', c.name)[0].lstrip('$')
            ext[cls].append(c.name)
    for c in flow.middle_layer:
        integ.append(('Middle layer', [c.name + (f" '{c.target}'" if c.target else '')]))
    for cls, names in ext.items():
        integ.append((f'{cls} (library / framework)', uniq(names)[:8]))
    rw = defaultdict(set)
    for s in flow.sql:
        w = s.kind not in ('SELECT', 'WITH', 'SQL')
        for t in s.tables:
            rw[t].add('write' if w else 'read')
    if flow.connections:
        data.append(('Connections', flow.connections))
    if rw:
        data.append(('Tables', [f'{t} ({"/".join(sorted(v))})' for t, v in rw.items()]))
    if flow.procedures:
        data.append(('Stored procedures', flow.procedures))
    return [('Presentation', pres), ('Application logic', app), ('Integration', integ), ('Data', data)]


def build(project, flow, path, cfg):
    W, H = TH.PAGE
    c = rl_canvas.Canvas(path, pagesize=TH.PAGE)
    title = f'{flow.id}  {flow.name}'
    TH.stamp(c, title, cfg.get('author', ''), 'Architectural flow (as is)')
    ids = {f.id: f for f in project.flows}
    lanes = _lanes(project, flow)
    page = [0]

    def new_page():
        if page[0]:
            c.showPage()
        page[0] += 1
        c.setFillColor(TH.ACCENT)
        c.rect(0, H - 34, W, 34, stroke=0, fill=1)
        c.setFillColor(TH.hexc('#FFFFFF'))
        c.setFont(TH.BOLD, 12)
        c.drawString(TH.MARGIN, H - 22, title[:150])
        c.setFont(TH.FONT, 7.5)
        c.drawRightString(W - TH.MARGIN, H - 22, f'Architectural flow (as is)  |  {flow.functionality}'[:120])
        c.setFillColor(TH.MUTED)
        c.setFont(TH.FONT, 6.8)
        c.drawString(TH.MARGIN, 14, f'{cfg.get("project", "")}  |  {flow.id} architectural flow (as is)')
        c.drawRightString(W - TH.MARGIN, 14, f'Page {page[0]}')

    new_page()
    y = H - 46
    # upstream strip
    def strip(label, fl_ids, y):
        txt = '; '.join(f'{i} {ids[i].name}' for i in fl_ids) or 'None'
        lines = wrap(f'{label}: {txt}', W - 2 * TH.MARGIN - 12, TH.FONT, FS)[:4]
        h = 8 + LEAD * len(lines)
        c.setFillColor(TH.ZEBRA)
        c.setStrokeColor(TH.RULE)
        c.roundRect(TH.MARGIN, y - h, W - 2 * TH.MARGIN, h, 3, stroke=1, fill=1)
        c.setFillColor(TH.INK)
        c.setFont(TH.FONT, FS)
        yy = y - 4 - FS
        for ln in lines:
            c.drawString(TH.MARGIN + 6, yy, ln)
            yy -= LEAD
        return y - h - 8

    y = strip('Upstream flows (this flow is reached from / depends on)', flow.upstream, y)
    gap = 22
    lw = (W - 2 * TH.MARGIN - 3 * gap) / 4
    xs = [TH.MARGIN + i * (lw + gap) for i in range(4)]
    bottom_reserved = 60
    top = y
    # lane headers
    for (name, boxes), x in zip(lanes, xs):
        col = TH.hexc(TH.LANE[name])
        c.setFillColor(col)
        c.roundRect(x, top - 16, lw, 16, 3, stroke=0, fill=1)
        c.setFillColor(TH.hexc('#FFFFFF'))
        c.setFont(TH.BOLD, 8)
        c.drawCentredString(x + lw / 2, top - 11.5, name)
    avail = top - 22 - bottom_reserved
    mids = []
    lane_bottom = []
    for (name, boxes), x in zip(lanes, xs):
        col = TH.hexc(TH.LANE[name])
        yy = top - 24
        first_mid = None
        # fit: limit lines per box so that the lane fits on the page
        budget = int(avail / LEAD)
        need = sum(2 + len(wrap(t, lw - 10, TH.BOLD, 7.2)) + sum(len(wrap(l, lw - 12, TH.FONT, FS)) for l in ls) for t, ls in boxes)
        per_box_cap = 999 if need <= budget else max(3, int(budget / max(1, len(boxes))) - 3)
        shown = 0
        for t, ls in boxes:
            tl = wrap(t, lw - 10, TH.BOLD, 7.2)
            bl = []
            for l in ls:
                bl += wrap(l, lw - 12, TH.FONT, FS)
            if len(bl) > per_box_cap:
                more = len(bl) - per_box_cap
                bl = bl[:per_box_cap] + [f'+ {more} more lines, listed on the cover sheet']
            h = 6 + len(tl) * 8.6 + len(bl) * LEAD + 2
            if yy - h < bottom_reserved:
                c.setFillColor(TH.MUTED)
                c.setFont(TH.FONT, FS)
                c.drawString(x + 2, yy - 8, f'+ {len(boxes) - shown} more components, listed on the cover sheet')
                break
            c.setFillColor(TH.hexc('#FFFFFF'))
            c.setStrokeColor(col)
            c.setLineWidth(0.9)
            c.roundRect(x, yy - h, lw, h, 3, stroke=1, fill=1)
            c.setFillColor(col)
            c.setFont(TH.BOLD, 7.2)
            ty = yy - 4 - 7.2
            for s in tl:
                c.drawString(x + 5, ty, s)
                ty -= 8.6
            c.setFillColor(TH.INK)
            c.setFont(TH.FONT, FS)
            for s in bl:
                c.drawString(x + 7, ty, s)
                ty -= LEAD
            if first_mid is None:
                first_mid = yy - h / 2
            yy -= h + 8
            shown += 1
        if not boxes:
            c.setFillColor(TH.MUTED)
            c.setFont(TH.FONT, FS)
            c.drawCentredString(x + lw / 2, top - 34, 'not used by this flow')
        mids.append(first_mid)
        lane_bottom.append(yy)
    # connectors between lanes
    def harrow(x1, x2, yv, label):
        c.setStrokeColor(TH.MUTED)
        c.setLineWidth(0.9)
        c.line(x1, yv, x2 - 4, yv)
        p = c.beginPath()
        p.moveTo(x2 - 6, yv + 3)
        p.lineTo(x2 - 6, yv - 3)
        p.lineTo(x2, yv)
        p.close()
        c.setFillColor(TH.MUTED)
        c.drawPath(p, stroke=0, fill=1)
        c.setFont(TH.FONT, 5.8)
        c.drawCentredString((x1 + x2) / 2, yv + 3, label)

    if mids[0] and mids[1]:
        harrow(xs[0] + lw, xs[1], mids[0], 'calls')
    if mids[1] and mids[2]:
        harrow(xs[1] + lw, xs[2], mids[1], 'invokes')
    if mids[3]:
        src = 1 if mids[1] else 0
        if mids[2]:
            # application -> data passes under the integration lane
            yv = max(lane_bottom[2] - 4, bottom_reserved + 4)
            c.setStrokeColor(TH.MUTED)
            c.setDash(2, 2)
            c.line(xs[src] + lw, yv, xs[3] - 4, yv)
            c.setDash()
            p = c.beginPath()
            p.moveTo(xs[3] - 6, yv + 3)
            p.lineTo(xs[3] - 6, yv - 3)
            p.lineTo(xs[3], yv)
            p.close()
            c.setFillColor(TH.MUTED)
            c.drawPath(p, stroke=0, fill=1)
            c.setFont(TH.FONT, 5.8)
            c.drawCentredString((xs[2] + xs[3]) / 2 + lw / 2, yv + 3, 'reads / writes')
        else:
            harrow(xs[src] + lw, xs[3], mids[3], 'reads / writes')
    strip('Downstream flows (reached from / depending on this flow)', flow.downstream, bottom_reserved - 2)
    c.showPage()
    c.save()
    return page[0]
