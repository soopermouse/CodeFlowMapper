"""Flowchart drawing on landscape pages: a main sequence of boxes joined by arrows, decisions that open into side-by-side
lanes (one per case) and merge again, automatic page breaks with continuation markers. Lanes too many or too tall for a
page are drawn one after the other under their case label."""
from __future__ import annotations
from dataclasses import dataclass, field
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from . import theme as TH

FS, TFS, LEAD = 7.2, 8.2, 9.0
PAD = 5


@dataclass
class N:
    kind: str
    title: str
    lines: list = field(default_factory=list)


@dataclass
class D:
    question: str
    lanes: list = field(default_factory=list)      # [(label, [N | D])]


def wrap(text: str, width: float, font=TH.FONT, size=FS):
    out = []
    for para in str(text).split('\n'):
        words = para.split(' ')
        cur = ''
        for w in words:
            while stringWidth(w, font, size) > width and len(w) > 1:
                # very long token (SQL, paths): hard split
                k = max(1, int(len(w) * width / max(1, stringWidth(w, font, size))) - 1)
                if cur:
                    out.append(cur)
                    cur = ''
                out.append(w[:k])
                w = w[k:]
            t = (cur + ' ' + w).strip() if cur else w
            if stringWidth(t, font, size) <= width:
                cur = t
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out


class Chart:
    def __init__(self, path, title, subtitle, author='', footer='', max_lines=38):
        self.path, self.title, self.subtitle, self.author, self.footer = path, title, subtitle, author, footer
        self.items = []
        self.max_lines = max_lines
        self.W, self.H = TH.PAGE
        self.page = 0

    def add(self, item):
        self.items.append(item)
        return item

    # ------------------------------------------------------------ measuring
    def _node_lines(self, n: N, width):
        tl = wrap(n.title, width - 2 * PAD, TH.BOLD, TFS)
        bl = []
        for ln in n.lines:
            bl += wrap(ln, width - 2 * PAD - 6, TH.FONT, FS)
        return tl, bl

    def _h(self, n: N, width):
        tl, bl = self._node_lines(n, width)
        return 2 * PAD + len(tl) * (TFS + 1.5) + len(bl) * LEAD + (2 if bl else 0)

    def _split(self, n: N, width):
        """a node too long for one box becomes several boxes"""
        tl, bl = self._node_lines(n, width)
        if len(bl) <= self.max_lines:
            return [n]
        out, chunk, first = [], [], True
        for ln in n.lines:
            chunk.append(ln)
            if sum(len(wrap(c, width - 2 * PAD - 6)) for c in chunk) >= self.max_lines:
                out.append(N(n.kind, n.title if first else n.title + ' (continued)', chunk))
                chunk, first = [], False
        if chunk:
            out.append(N(n.kind, n.title if first else n.title + ' (continued)', chunk))
        return out

    def _seq_h(self, items, width):
        h = 0
        for it in items:
            if isinstance(it, N):
                h += sum(self._h(x, width) + 14 for x in self._split(it, width))
            else:
                h += 30 + max((self._seq_h(l, width) for _, l in it.lanes), default=0) + 20
        return h

    # ------------------------------------------------------------ pages
    def _new_page(self, c):
        if self.page:
            c.showPage()
        self.page += 1
        W, H = self.W, self.H
        c.setFillColor(TH.ACCENT)
        c.rect(0, H - 34, W, 34, stroke=0, fill=1)
        c.setFillColor(TH.hexc('#FFFFFF'))
        c.setFont(TH.BOLD, 12)
        c.drawString(TH.MARGIN, H - 22, self.title[:150])
        c.setFont(TH.FONT, 7.5)
        c.drawRightString(W - TH.MARGIN, H - 22, self.subtitle[:120])
        c.setFillColor(TH.MUTED)
        c.setFont(TH.FONT, 6.8)
        c.drawString(TH.MARGIN, 14, self.footer[:180])
        c.drawRightString(W - TH.MARGIN, 14, f'Page {self.page}')
        self._legend(c)
        return H - 50

    def _legend(self, c):
        keys = [('start', 'Entry / end'), ('access', 'Access check'), ('input', 'Request input'), ('form', 'Form'), ('dropdown', 'Dropdown'),
                ('decision', 'Decision'), ('call', 'Call'), ('data', 'Database'), ('middle', 'Middle layer'), ('message', 'Message'),
                ('output', 'Output'), ('link', 'Next page / flow')]
        x = TH.MARGIN
        y = 26
        c.setFont(TH.FONT, 6.2)
        for k, lab in keys:
            fill, stroke = TH.NODE[k]
            c.setFillColor(TH.hexc(fill))
            c.setStrokeColor(TH.hexc(stroke))
            c.rect(x, y, 8, 6, stroke=1, fill=1)
            c.setFillColor(TH.MUTED)
            c.drawString(x + 11, y + 0.5, lab)
            x += 14 + stringWidth(lab, TH.FONT, 6.2) + 10

    # ------------------------------------------------------------ drawing
    def _box(self, c, n: N, x, y, width):
        """draw node with top-left at (x, y); return height"""
        tl, bl = self._node_lines(n, width)
        h = self._h(n, width)
        fill, stroke = TH.NODE.get(n.kind, TH.NODE['note'])
        c.setFillColor(TH.hexc(fill))
        c.setStrokeColor(TH.hexc(stroke))
        c.setLineWidth(0.9)
        if n.kind in ('start', 'end'):
            c.roundRect(x, y - h, width, h, 9, stroke=1, fill=1)
        elif n.kind == 'decision':
            p = c.beginPath()
            k = 9
            p.moveTo(x + k, y)
            p.lineTo(x + width - k, y)
            p.lineTo(x + width, y - h / 2)
            p.lineTo(x + width - k, y - h)
            p.lineTo(x + k, y - h)
            p.lineTo(x, y - h / 2)
            p.close()
            c.drawPath(p, stroke=1, fill=1)
        elif n.kind in ('data',):
            c.roundRect(x, y - h, width, h, 3, stroke=1, fill=1)
            c.line(x, y - 4, x + width, y - 4)
        else:
            c.roundRect(x, y - h, width, h, 3, stroke=1, fill=1)
        c.setFillColor(TH.hexc(stroke))
        yy = y - PAD - TFS + 1
        c.setFont(TH.BOLD, TFS)
        for t in tl:
            c.drawString(x + PAD, yy, t)
            yy -= TFS + 1.5
        c.setFillColor(TH.INK)
        c.setFont(TH.FONT, FS)
        yy -= 1
        for t in bl:
            c.drawString(x + PAD + 4, yy, t)
            yy -= LEAD
        return h

    def _arrow(self, c, x, y1, y2):
        c.setStrokeColor(TH.MUTED)
        c.setLineWidth(0.8)
        c.line(x, y1, x, y2 + 3)
        p = c.beginPath()
        p.moveTo(x - 3, y2 + 5)
        p.lineTo(x + 3, y2 + 5)
        p.lineTo(x, y2)
        p.close()
        c.setFillColor(TH.MUTED)
        c.drawPath(p, stroke=0, fill=1)

    def _cont(self, c, x, y, text):
        c.setFillColor(TH.MUTED)
        c.setFont(TH.FONT, 6.8)
        c.drawCentredString(x, y, text)

    def _draw_seq(self, c, items, xc, width, y, bottom, first_arrow=False):
        """main column; returns y after the last item"""
        x = xc - width / 2
        prev_bottom = None if not first_arrow else y + 10
        for it in items:
            if isinstance(it, N):
                for n in self._split(it, width):
                    h = self._h(n, width)
                    if y - h < bottom:
                        self._cont(c, xc, bottom - 8, 'continues on the next page')
                        y = self._new_page(c)
                        self._cont(c, xc, y, 'continued from the previous page')
                        y -= 12
                        prev_bottom = None
                    if prev_bottom is not None:
                        self._arrow(c, xc, prev_bottom, y)
                    self._box(c, n, x, y, width)
                    prev_bottom = y - h
                    y = y - h - 14
            else:
                y, prev_bottom = self._draw_decision(c, it, xc, width, y, bottom, prev_bottom)
        return y

    def _draw_decision(self, c, d: D, xc, width, y, bottom, prev_bottom):
        q = N('decision', d.question, [])
        qh = self._h(q, min(width, 420))
        usable_w = self.W - 2 * TH.MARGIN
        n = max(1, len(d.lanes))
        gap = 10
        lane_w = (usable_w - gap * (n - 1)) / n
        lane_w = min(lane_w, 300)
        lanes_h = max((self._seq_h(l, lane_w) for _, l in d.lanes), default=0)
        block = qh + 26 + lanes_h + 16
        page_h = self.H - 50 - 40
        parallel = lane_w >= 140 and block <= page_h and n > 1
        if parallel and y - block < bottom:
            self._cont(c, xc, bottom - 8, 'continues on the next page')
            y = self._new_page(c)
            y -= 4
            prev_bottom = None
        if not parallel:
            # decision box then each case one after the other
            if y - qh < bottom:
                y = self._new_page(c)
                prev_bottom = None
            if prev_bottom is not None:
                self._arrow(c, xc, prev_bottom, y)
            qw = min(width, 420)
            self._box(c, q, xc - qw / 2, y, qw)
            y = y - qh - 14
            prev = y + 14
            for label, items in d.lanes:
                lab = N('decision', f'Case: {label}', [])
                y = self._draw_seq(c, [lab] + items, xc, width - 30, y, bottom, first_arrow=False)
                prev = y + 14
            return y, prev
        if prev_bottom is not None:
            self._arrow(c, xc, prev_bottom, y)
        qw = min(width, 420)
        self._box(c, q, xc - qw / 2, y, qw)
        y -= qh
        total = n * lane_w + gap * (n - 1)
        x0 = xc - total / 2
        bus = y - 10
        c.setStrokeColor(TH.MUTED)
        c.setLineWidth(0.8)
        c.line(xc, y, xc, bus)
        centers = [x0 + i * (lane_w + gap) + lane_w / 2 for i in range(n)]
        c.line(centers[0], bus, centers[-1], bus)
        bottoms = []
        top = bus - 16
        for (label, items), cx in zip(d.lanes, centers):
            c.setFillColor(TH.hexc(TH.NODE['decision'][1]))
            c.setFont(TH.BOLD, 6.8)
            lab = wrap(label, lane_w - 6, TH.BOLD, 6.8)[0]
            c.drawCentredString(cx, bus - 8, lab)
            yy = top - 4
            first = True
            for it in items:
                nodes = self._split(it, lane_w) if isinstance(it, N) else [N('decision', it.question, [f'{l}: ' + '; '.join(x.title for x in li if isinstance(x, N)) for l, li in it.lanes])]
                for nd in nodes:
                    h = self._h(nd, lane_w)
                    self._arrow(c, cx, bus - 11 if first else yy + 14, yy)
                    self._box(c, nd, cx - lane_w / 2, yy, lane_w)
                    yy -= h + 14
                    first = False
            if first:
                self._arrow(c, cx, bus - 11, yy)
            bottoms.append(yy + 14)
        merge = min(bottoms) - 8
        c.setStrokeColor(TH.MUTED)
        for b, cx in zip(bottoms, centers):
            c.line(cx, b, cx, merge)
        c.line(centers[0], merge, centers[-1], merge)
        return merge - 14, merge

    def save(self):
        c = rl_canvas.Canvas(self.path, pagesize=TH.PAGE)
        TH.stamp(c, self.title, self.author, self.subtitle)
        y = self._new_page(c)
        width = min(560, self.W - 2 * TH.MARGIN)
        self._draw_seq(c, self.items, self.W / 2, width, y, 44)
        c.showPage()
        c.save()
        return self.page
