"""switch / case and if / else decisions in brace languages (PHP, Java, C#, JS)."""
from __future__ import annotations
import re
from ..model import Branch
from ..textutil import match_brace, match_paren, skip_string, short

CASE_RX = re.compile(r'\b(case\s+(.+?)|default)\s*:(?!:)')


def _split_cases(body: str):
    """top-level case labels of a switch body -> [(label, text, offset)]"""
    cuts = []
    depth = 0
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c in '"\'`':
            i = skip_string(body, i)
            continue
        if c in '{([':
            depth += 1
        elif c in '})]':
            depth -= 1
        elif depth == 0 and (body.startswith('case', i) or body.startswith('default', i)) and (i == 0 or not (body[i - 1].isalnum() or body[i - 1] == '_')):
            m = CASE_RX.match(body, i)
            if m:
                lab = 'default' if m.group(1) == 'default' else m.group(2).strip()
                cuts.append((i, m.end(), lab))
                i = m.end()
                continue
        i += 1
    out = []
    for k, (s, e, lab) in enumerate(cuts):
        end = cuts[k + 1][0] if k + 1 < len(cuts) else n
        out.append((lab, body[e:end], e))
    # fall-through labels with no code join the next label
    merged = []
    pend = []
    for lab, txt, off in out:
        if not re.sub(r'\s+', '', txt):
            pend.append(lab)
            continue
        merged.append((' / '.join(pend + [lab]), txt, off))
        pend = []
    return merged


def switches(code: str, line_of, file: str, subject_ok=None, base: int = 0):
    out = []
    for m in re.finditer(r'\bswitch\s*\(', code):
        p = code.find('(', m.start())
        q = match_paren(code, p)
        subject = code[p + 1:q].strip()
        if subject_ok and not subject_ok(subject):
            continue
        b = code.find('{', q)
        if b < 0 or code[q + 1:b].strip() not in ('', ':'):
            continue
        e = match_brace(code, b)
        cases = [(short(lab.strip('\'"'), 80), txt, line_of(base + b + 1 + off)) for lab, txt, off in _split_cases(code[b + 1:e])]
        if cases:
            br = Branch(subject=short(subject, 100), kind='switch', cases=cases, file=file, line=line_of(base + m.start()))
            br.span = (m.start(), e)
            out.append(br)
    return out


def ifs(code: str, line_of, file: str, cond_ok, base: int = 0, skip=()):
    """if / elseif / else chains whose first condition passes cond_ok (not inside the spans in skip)."""
    out = []
    consumed = set()
    for m in re.finditer(r'\bif\s*\(', code):
        if m.start() in consumed or any(a <= m.start() <= b for a, b in skip):
            continue
        # skip "else if" handled as part of a chain
        pre = code[max(0, m.start() - 6):m.start()]
        if re.search(r'else\s*$', pre):
            continue
        p = code.find('(', m.start())
        q = match_paren(code, p)
        cond = code[p + 1:q].strip()
        if not cond_ok(cond):
            continue
        cases = []
        pos = q + 1
        label = cond
        while True:
            j = pos
            while j < len(code) and code[j] in ' \t\n\r':
                j += 1
            if j < len(code) and code[j] == '{':
                e = match_brace(code, j)
                cases.append((short(label, 100), code[j + 1:e], line_of(base + j)))
                pos = e + 1
            elif code.startswith(':', j):      # PHP alternative syntax if (...): ... endif;
                e = code.find('endif', j)
                e = len(code) if e < 0 else e
                cases.append((short(label, 100), code[j + 1:e], line_of(base + j)))
                pos = e
                break
            else:
                semi = code.find(';', j)
                semi = len(code) if semi < 0 else semi
                cases.append((short(label, 100), code[j:semi + 1], line_of(base + j)))
                pos = semi + 1
            k = pos
            while k < len(code) and code[k] in ' \t\n\r':
                k += 1
            mm = re.match(r'(?:else\s*if|elseif)\s*\(', code[k:])
            if mm:
                p2 = k + mm.end() - 1
                consumed.add(k + mm.start())
                q2 = match_paren(code, p2)
                label = code[p2 + 1:q2].strip()
                pos = q2 + 1
                continue
            if re.match(r'else\b', code[k:]):
                label = 'otherwise'
                pos = k + 4
                continue
            break
        if cases:
            out.append(Branch(subject=short(cond, 100), kind='if', cases=cases, file=file, line=line_of(base + m.start())))
    return out
