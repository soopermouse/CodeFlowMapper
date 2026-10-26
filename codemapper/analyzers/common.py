"""Extraction shared by all languages: SQL, stored procedures, tables, forms and dropdown options, validation and user
messages, links / redirects / AJAX targets, middle-layer calls, authorisation checks and connection names."""
from __future__ import annotations
import html as _html
import re
from dataclasses import dataclass, field
from ..model import SqlStmt, Call, Form, Field_, Option, Param
from ..textutil import strings, match_paren, short, uniq


@dataclass
class FileFacts:
    path: str
    language: str
    includes: list = field(default_factory=list)      # included / imported project files (raw strings)
    classes: list = field(default_factory=list)
    functions: list = field(default_factory=list)     # function keys defined in the file
    top_calls: list = field(default_factory=list)     # calls in code outside functions
    sql: list = field(default_factory=list)
    forms: list = field(default_factory=list)
    params: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    links: list = field(default_factory=list)
    templates: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    branches: list = field(default_factory=list)
    connections: list = field(default_factory=list)
    middle_layer: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    title: str = ''
    is_entry: bool = False
    entry_kind: str = ''
    top_code: str = ''                                # code outside functions / classes


# ------------------------------------------------------------------ SQL
SQL_START = re.compile(r'^\s*(SELECT|INSERT|UPDATE|DELETE|MERGE|EXEC(?:UTE)?|CALL|WITH|CREATE|ALTER|DROP|TRUNCATE|REPLACE|\{\s*\??=?\s*call)\b', re.I)
SQL_ANY = re.compile(r'\b(SELECT\s.+?\sFROM\s|INSERT\s+INTO\s|UPDATE\s+[\w\[\].`"]+\s+SET\s|DELETE\s+FROM\s|EXEC(?:UTE)?\s+[\w\[\].]+|MERGE\s+INTO\s|\{\s*\??=?\s*call\s)', re.I | re.S)
NAME = r'((?:[\w$#]+|\[[^\]]+\]|`[^`]+`|"[^"]+")(?:\s*\.\s*(?:[\w$#]+|\[[^\]]+\]|`[^`]+`|"[^"]+")){0,3})'
TABLE_RX = [
    re.compile(r'\bFROM\s+' + NAME, re.I), re.compile(r'\bJOIN\s+' + NAME, re.I), re.compile(r'\bINTO\s+' + NAME, re.I),
    re.compile(r'^\s*UPDATE\s+' + NAME, re.I), re.compile(r'\bMERGE\s+(?:INTO\s+)?' + NAME, re.I),
    re.compile(r'\bDELETE\s+(?:FROM\s+)?' + NAME, re.I), re.compile(r'\bTRUNCATE\s+TABLE\s+' + NAME, re.I),
]
PROC_RX = re.compile(r'\b(?:EXEC(?:UTE)?|CALL)\s+(?:@\w+\s*=\s*)?' + NAME, re.I)
CALLBRACE_RX = re.compile(r'\{\s*\??\s*=?\s*call\s+' + NAME, re.I)
SQL_WORDS = {'select', 'where', 'set', 'values', 'as', 'on', 'and', 'or', 'not', 'null', 'dual', 'lateral', 'the', 'a', 'an', 'table', 'into'}


def _clean_name(n: str) -> str:
    n = re.sub(r'\s*\.\s*', '.', n)
    n = n.replace('[', '').replace(']', '').replace('`', '').replace('"', '')
    return n


def parse_sql(text: str):
    """(kind, tables, procedure) of one SQL statement."""
    t = re.sub(r'\s+', ' ', text).strip()
    m = SQL_START.match(t)
    kind = (m.group(1).upper() if m else '')
    if kind.startswith('{'):
        kind = 'CALL'
    if kind == 'EXECUTE':
        kind = 'EXEC'
    if not kind:
        m = SQL_ANY.search(t)
        kind = m.group(1).split()[0].upper() if m else 'SQL'
        if kind.startswith('{'):
            kind = 'CALL'
    proc = ''
    m = CALLBRACE_RX.search(t) or PROC_RX.search(t)
    if m and kind in ('EXEC', 'CALL', 'EXECUTE', 'SQL'):
        proc = _clean_name(m.group(1))
    tables = []
    if not proc:
        # drop sub-select aliases like FROM (SELECT ...)
        for rx in TABLE_RX:
            for mm in rx.finditer(t):
                n = _clean_name(mm.group(1))
                if n.lower() in SQL_WORDS or n.startswith(('$', ':', '@', '?')) or re.fullmatch(r'\d+', n):
                    continue
                tables.append(n)
    return kind, uniq(tables), proc


def looks_sql(s: str) -> bool:
    if len(s) < 8:
        return False
    return bool(SQL_START.match(s) and (re.search(r'\b(FROM|INTO|SET|VALUES|WHERE|call)\b', s, re.I) or re.match(r'\s*(EXEC|CALL)', s, re.I))) \
        or bool(re.match(r'\s*\{\s*\??=?\s*call\s', s, re.I))


def sql_in(code: str, file: str, base_line, func: str = ''):
    """SQL found in the string literals of code. Adjacent concatenated literals are joined."""
    out = []
    lits = list(strings(code))
    i = 0
    while i < len(lits):
        off, v = lits[i]
        if looks_sql(v) or (SQL_START.match(v) and i + 1 < len(lits)):
            text = v
            j = i + 1
            # join literals separated only by concatenation operators / variables (".", "+", "&", interpolation)
            while j < len(lits):
                gap = code[lits[j - 1][0] + len(lits[j - 1][1]) + 2: lits[j][0]]
                if len(gap) < 80 and re.fullmatch(r'[\s.+&\w$>\-\[\]\'"(),:]*', gap) and not re.search(r'[;{}]', gap):
                    var = re.findall(r'\$\w+(?:->\w+)*|(?<![\w$])[A-Za-z_]\w*(?:\.\w+)*', gap)
                    var = [v for v in var if v not in ('intval', 'trim', 'addslashes', 'mysql_real_escape_string', 'String', 'str')]
                    text += ('{' + var[-1] + '}' if var else '') + lits[j][1]
                    j += 1
                else:
                    break
            if looks_sql(text):
                kind, tables, proc = parse_sql(text)
                params = uniq(re.findall(r'(?<![\w@])[:@](\w+)|\$(\w+)|(\?)', text))
                params = [a or b or c for a, b, c in params]
                out.append(SqlStmt(kind=kind, text=short(text, 600), tables=tables, procedure=proc, params=params, file=file,
                                   line=base_line(off), function=func))
            i = j
        else:
            i += 1
    return out


PROC_CALL_RX = [   # stored procedures called by name in code, not inside SQL text
    re.compile(r'CommandType\.StoredProcedure'),
    re.compile(r'createStoredProcedureQuery\s*\(\s*"([^"]+)"'),
    re.compile(r'@Procedure\s*\(\s*(?:name\s*=\s*|procedureName\s*=\s*|value\s*=\s*)?"([^"]+)"'),
    re.compile(r'new\s+SimpleJdbcCall\([^)]*\)\s*\.withProcedureName\s*\(\s*"([^"]+)"'),
    re.compile(r'\bmssql_init\s*\(\s*[\'"]([^\'"]+)'), re.compile(r'\boci_parse\s*\([^,]+,\s*[\'"]\s*BEGIN\s+([\w.]+)', re.I),
]


def procs_by_api(code: str, file: str, base_line, func: str = ''):
    out = []
    if PROC_CALL_RX[0].search(code):
        # C#: new SqlCommand("name", conn) / cmd.CommandText = "name" with CommandType.StoredProcedure
        for m in re.finditer(r'new\s+(?:Sql|OleDb|Odbc|Oracle|MySql|Npgsql)Command\s*\(\s*"([\w.\[\]]+)"|CommandText\s*=\s*"([\w.\[\]]+)"', code):
            n = _clean_name(m.group(1) or m.group(2))
            out.append(SqlStmt(kind='EXEC', text=f'stored procedure {n}', procedure=n, file=file, line=base_line(m.start()), function=func))
    for rx in PROC_CALL_RX[1:]:
        for m in rx.finditer(code):
            n = _clean_name(m.group(1))
            out.append(SqlStmt(kind='EXEC', text=f'stored procedure {n}', procedure=n, file=file, line=base_line(m.start()), function=func))
    return out


# ------------------------------------------------------------------ messages
MSG_KEY = re.compile(r'(?i)\b(invalid|required|must|mandatory|not allowed|please|failed|failure|cannot|can\'t|could not|incorrect|missing|'
                     r'empty|too (long|short|large|small)|exceed|at least|at most|not (a )?valid|does not|doesn\'t|already exists|'
                     r'not found|unauthori[sz]ed|forbidden|denied|error|wrong|duplicate|expired|successfully|saved|deleted|updated|'
                     r'are you sure|confirm|no (results|records|data)|not permitted|only|between|format)\b')
MSG_CALL = re.compile(r'(?:alert|confirm|throw\s+new\s+\w+|AddModelError|addError|setError|setCustomValidity|withMessage|message|'
                      r'ErrorMessage|errorMessage|errors?\s*\[\s*[^\]]*\]\s*=|\$error\w*\s*\.?=|flash\w*|toastr\.\w+|notify\w*|'
                      r'reject\w*|res\.status\(\s*4\d\d\s*\)\.\w+|BadRequest|NotFound|Problem|ValidationError|die|exit)\b', re.I)


def messages_in(code: str, base_line):
    out = []
    for off, v in strings(code):
        s = v.strip()
        if not (6 <= len(s) <= 220) or looks_sql(s) or not re.search(r'[A-Za-z]{3,}\s+[A-Za-z]{2,}', s):
            continue
        if re.search(r'[<>{}]|^\w+(\.\w+)+$|^[\w/.-]+\.(php|inc|html|js|tpl|cs|java)$|^https?:', s):
            s2 = re.sub(r'<[^>]+>', ' ', s).strip()
            if not s2 or s2 == s:
                continue
            s = s2
        before = code[max(0, off - 90):off]
        if MSG_KEY.search(s) or MSG_CALL.search(before):
            out.append((short(_html.unescape(s), 200), base_line(off)))
    # annotation / attribute messages (Java Bean Validation, .NET DataAnnotations)
    for m in re.finditer(r'(?:message|ErrorMessage)\s*=\s*"([^"]+)"', code):
        out.append((short(m.group(1), 200), base_line(m.start())))
    return uniq(out)


# ------------------------------------------------------------------ links / redirects / AJAX
LINK_RX = [
    (re.compile(r'\b(?:href|action|src|formaction|data-url|data-href)\s*=\s*["\']([^"\'#][^"\']*)["\']', re.I), 'link'),
    (re.compile(r'(?:window\.)?location(?:\.href)?\s*=\s*["\']([^"\']+)["\']'), 'redirect'),
    (re.compile(r'header\s*\(\s*["\']Location:\s*([^"\']+)["\']', re.I), 'redirect'),
    (re.compile(r'\b(?:res\.redirect|redirect|Redirect|sendRedirect)\s*\(\s*(?:\d{3}\s*,\s*)?["\'`]([^"\'`]+)["\'`]'), 'redirect'),
    (re.compile(r'"redirect:([^"]+)"'), 'redirect'),
    (re.compile(r'RedirectToAction\s*\(\s*"(\w+)"(?:\s*,\s*"(\w+)")?'), 'redirect'),
    (re.compile(r'\$\.(?:ajax|get|post|getJSON|load)\s*\(\s*["\']([^"\']+)["\']'), 'ajax'),
    (re.compile(r'\.load\s*\(\s*["\']([^"\']+)["\']'), 'ajax'),
    (re.compile(r'\burl\s*:\s*["\']([^"\']+)["\']'), 'ajax'),
    (re.compile(r'\bfetch\s*\(\s*["\'`]([^"\'`]+)["\'`]'), 'ajax'),
    (re.compile(r'\baxios\.(?:get|post|put|delete|patch)\s*\(\s*["\'`]([^"\'`]+)["\'`]'), 'ajax'),
    (re.compile(r'\$http\.(?:get|post|put|delete)\s*\(\s*["\']([^"\']+)["\']'), 'ajax'),
    (re.compile(r'window\.open\s*\(\s*["\']([^"\']+)["\']'), 'popup'),
]


def _concat(text: str, end: int) -> str:
    """string continued by '+ variable + "literal"' after a literal ending at end: variables become X."""
    out = ''
    rx = re.compile(r'\s*\+\s*(?:"([^"\n]*)"|\'([^\'\n]*)\'|`([^`]*)`|([\w$.\[\]()]+))')
    pos = end
    for _ in range(8):
        m = rx.match(text, pos)
        if not m:
            break
        lit = next((g for g in m.groups()[:3] if g is not None), None)
        out += lit if lit is not None else 'X'
        pos = m.end()
    return out


def links_in(text: str, base_line):
    out = []
    for rx, kind in LINK_RX:
        for m in rx.finditer(text):
            u = m.group(1).strip()
            if kind == 'ajax':
                u = u + _concat(text, m.end(1) + 1)
            u = re.sub(r'^@\{(.*)\}$', r'\1', u)
            u = re.sub(r'\$\{[^}]*\}', 'X', u)
            if kind == 'redirect' and rx.pattern.startswith('RedirectToAction'):
                u = f'{m.group(2) or ""}/{m.group(1)}'.lstrip('/')
            if not u or u.startswith(('javascript:', 'mailto:', '#', 'data:', 'tel:')) or re.search(r'\.(css|png|gif|jpe?g|svg|ico|woff2?|ttf)(\?|$)', u, re.I):
                continue
            if kind == 'link' and re.search(r'\.js(\?|$)', u):
                continue
            out.append((u, kind, base_line(m.start())))
    return uniq(out)


# ------------------------------------------------------------------ forms, fields, dropdowns
TAG_RX = re.compile(r'<(input|select|textarea|button|form:input|form:select|form:checkbox|form:radiobutton|form:textarea|form:password|form:hidden)\b([^>]*)>', re.I)
ATTR_RX = re.compile(r'([\w:\-@.\[\]()*#]+)\s*=\s*("([^"]*)"|\'([^\']*)\'|\{([^}]*)\}|([^\s>]+))')


def attrs(s: str) -> dict:
    d = {}
    for m in ATTR_RX.finditer(s):
        v = next((g for g in m.groups()[2:] if g is not None), '')
        d[m.group(1).lower()] = v
    for flag in ('required', 'disabled', 'readonly', 'multiple', 'checked', 'selected'):
        if re.search(r'(?<![\w-])' + flag + r'(?![\w=-])', s, re.I):
            d.setdefault(flag, flag)
    return d


def _label_for(text: str, fid: str, name: str, start: int) -> str:
    if fid:
        m = re.search(r'<label[^>]*\bfor\s*=\s*["\']' + re.escape(fid) + r'["\'][^>]*>(.*?)</label>', text, re.I | re.S)
        if m:
            return short(re.sub(r'<[^>]+>|<\?.*?\?>', ' ', m.group(1)), 80)
    # text of the cell / element just before the field, after the previous field or heading
    before = text[max(0, start - 400):start]
    before = re.sub(r'<\?(?:php)?.*?\?>', ' ', before, flags=re.S)
    cut = [m.end() for m in re.finditer(r'<(?:input|textarea|button|form|h[1-6])\b[^>]*>|</(?:select|textarea|button|h[1-6]|label|form)\s*>', before, re.I)]
    if cut:
        before = before[cut[-1]:]
    parts = [p.strip() for p in re.split(r'<[^>]+>', before) if p.strip() and not re.fullmatch(r'[\W\d_]*', p.strip())]
    if parts:
        cand = _html.unescape(parts[-1])
        if 1 < len(cand) <= 60 and not re.search(r'[{};$=]', cand):
            return short(cand.rstrip(':').strip(), 60)
    return ''


def forms_in(text: str, file: str, base_line):
    """forms with their fields; fields outside any <form> are collected in a form named '(page fields)'."""
    forms = []
    spans = []
    for m in re.finditer(r'<form\b([^>]*)>', text, re.I):
        end = text.lower().find('</form', m.end())
        end = len(text) if end < 0 else end
        a = attrs(m.group(1))
        spans.append((m.start(), end, Form(name=a.get('name') or a.get('id') or f'form {len(spans) + 1}',
                                            action=a.get('action', ''), method=(a.get('method') or 'GET').upper(),
                                            file=file, line=base_line(m.start()))))
    loose = Form(name='(page fields)', action='', method='', file=file, line=1)
    for m in TAG_RX.finditer(text):
        tag = m.group(1).lower()
        a = attrs(m.group(2))
        name = a.get('name') or a.get('path') or a.get('id') or a.get('asp-for') or a.get('v-model') or a.get('[(ngmodel)]') or a.get('formcontrolname') or ''
        kind = tag.split(':')[-1]
        if kind == 'input':
            kind = (a.get('type') or 'text').lower()
        elif kind in ('radiobutton',):
            kind = 'radio'
        if kind in ('button',) and not name:
            name = re.sub(r'<[^>]+>', '', text[m.end(): text.find('</button', m.end()) if text.find('</button', m.end()) > 0 else m.end()]).strip()[:40]
        f = Field_(name=name, kind=kind, required=('required' in a) or a.get('aria-required') == 'true',
                   default=a.get('value', ''), maxlength=a.get('maxlength', ''), pattern=a.get('pattern', ''),
                   file=file, line=base_line(m.start()))
        f.label = a.get('placeholder', '') if kind not in ('submit', 'button', 'hidden') else a.get('value', '')
        lab = _label_for(text, a.get('id', ''), name, m.start())
        if lab and kind not in ('submit', 'button', 'hidden'):
            f.label = lab
        if kind in ('select',):
            close = re.search(r'</(?:form:)?select\s*>', text[m.end():], re.I)
            inner = text[m.end(): m.end() + (close.start() if close else 3000)]
            for om in re.finditer(r'<option\b([^>]*)>(.*?)(?=</option|<option|$)', inner, re.I | re.S):
                oa = attrs(om.group(1))
                lab2 = short(_html.unescape(re.sub(r'<[^>]+>', '', om.group(2))), 80)
                if re.search(r'<\?|\{\{|\$\{|\$\w|@\w|\{%', om.group(0)):
                    # option built by code
                    f.options_source = short(om.group(0), 160)
                    continue
                f.options.append(Option(value=oa.get('value', lab2), label=lab2 or oa.get('value', ''), selected='selected' in oa))
            code_parts = re.findall(r'<\?(?:php)?(.*?)\?>|\{%(.*?)%\}|@foreach\s*\(([^)]*)\)|th:each\s*=\s*"([^"]+)"|\*ngFor\s*=\s*"([^"]+)"|v-for\s*=\s*"([^"]+)"|\{(\w+\.map\([^}]*)', inner, re.S)
            if code_parts:
                src = ' '.join(next((g for g in cp if g), '') for cp in code_parts)
                f.options_source = short(src, 200)
            if 'items' in a:
                f.options_source = a['items']
        if kind == 'textarea' and not f.label:
            f.label = a.get('placeholder', '')
        tgt = next((fm for s, e, fm in spans if s <= m.start() <= e), loose)
        tgt.fields.append(f)
    # Razor / MVC helpers
    for m in re.finditer(r'@Html\.(TextBox|TextArea|DropDownList|CheckBox|RadioButton|Password|Hidden|ListBox|Editor)(?:For)?\s*\(\s*(?:\w+\s*=>\s*\w+\.)?"?(\w+)"?', text):
        k = {'TextBox': 'text', 'TextArea': 'textarea', 'DropDownList': 'select', 'ListBox': 'select', 'CheckBox': 'checkbox',
             'RadioButton': 'radio', 'Password': 'password', 'Hidden': 'hidden', 'Editor': 'text'}[m.group(1)]
        loose.fields.append(Field_(name=m.group(2), kind=k, file=file, line=base_line(m.start())))
    for s, e, fm in spans:
        forms.append(fm)
    if loose.fields:
        forms.append(loose)
    return forms


# ------------------------------------------------------------------ configured patterns
def first_string(args: str) -> str:
    for _, v in strings(args):
        return v
    return ''


def pattern_calls(code: str, patterns, kind: str, file: str, base_line):
    out = []
    for p in patterns:
        for m in re.finditer(p, code):
            paren = code.find('(', m.start(), m.end() + 2)
            if paren < 0:
                paren = code.find('(', m.end())
            args = ''
            if 0 <= paren < m.end() + 3:
                args = code[paren + 1: match_paren(code, paren)]
            name = re.sub(r'\s*\($', '', m.group(0)).strip()
            out.append(Call(name=name, args=short(args, 200), file=file, line=base_line(m.start()), kind=kind,
                            target=first_string(args)))
    return out


def roles_in(code: str, patterns):
    out = []
    for p in patterns:
        for m in re.finditer(p, code):
            v = (m.group(1) if m.groups() else m.group(0)).strip()
            rm = re.search(r'Roles\s*=\s*"([^"]+)"', v)
            if rm:
                vals = [x.strip() for x in rm.group(1).split(',')]
            elif re.search(r'[\'"]', v.strip('\'" ')):
                vals = re.findall(r'[\'"]([^\'"]+)[\'"]', v) or [v.strip('\'" ')]
            else:
                vals = [v.strip('\'" ')]
            for x in vals:
                x = x.strip()
                if x and not x.startswith('$'):
                    out.append(short(x, 120))
                elif x.startswith('$'):
                    out.append(short(x, 120))
    return uniq(out)


def connections_in(code: str, patterns):
    out = []
    for p in patterns:
        for m in re.finditer(p, code):
            out.append(short(m.group(1).strip('\'" '), 80))
    return uniq(out)


def title_in(text: str) -> str:
    for rx in (r'<title>\s*([^<]{3,120}?)\s*</title>', r'<h1[^>]*>\s*([^<]{3,120}?)\s*</h1>', r'define\s*\(\s*[\'"]PAGE_TITLE[\'"]\s*,\s*[\'"]([^\'"]+)',
               r'ViewData\["Title"\]\s*=\s*"([^"]+)"', r'@(?:ApiOperation|Operation)\s*\(\s*(?:value\s*=\s*|summary\s*=\s*)?"([^"]+)"',
               r'<h2[^>]*>\s*([^<]{3,120}?)\s*</h2>', r'document\.title\s*=\s*["\']([^"\']+)'):
        m = re.search(rx, text, re.I)
        if m and not re.search(r'<\?|\{\{|\$', m.group(1)):
            return short(_html.unescape(m.group(1)), 100)
    return ''
