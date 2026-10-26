"""JavaScript / TypeScript: Express / Koa / Fastify / Next.js API routes, React Router / Vue Router pages, functions and
arrow functions, imports, calls, request parameters (req.query / req.body / req.params), validation messages, SQL in
strings, knex / Sequelize / Prisma / Mongoose data access, and front-end AJAX calls to back-end endpoints."""
from __future__ import annotations
import re
from ..model import Function, Call, EntryPoint, Param
from ..textutil import Text, match_brace, match_paren, short, uniq, strings
from . import common as C
from .branches import switches

JS_KW = {'if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'typeof', 'new', 'await', 'async', 'import', 'require',
         'super', 'constructor', 'else', 'do', 'try', 'with', 'delete', 'void', 'in', 'of', 'instanceof', 'yield', 'class', 'export'}
JS_BUILTIN_OBJ = {'console', 'Math', 'JSON', 'Object', 'Array', 'String', 'Number', 'Date', 'Promise', 'window', 'document', 'res',
                  'req', 'this', 'Reflect', 'process', 'Buffer', 'path', 'fs', 'util', 'moment', 'dayjs', '_', 'lodash', 'React',
                  'Vue', 'module', 'exports', 'localStorage', 'sessionStorage', 'navigator', 'history', 'event', 'e', 'err', 'error',
                  'arr', 'list', 'str', 'result', 'response', 'data', 'Symbol', 'Intl', 'RegExp', 'Boolean', 'Map', 'Set', 'axios', '$'}
JS_BUILTIN_FN = {'parseInt', 'parseFloat', 'isNaN', 'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval', 'alert', 'confirm',
                 'prompt', 'encodeURIComponent', 'decodeURIComponent', 'encodeURI', 'decodeURI', 'fetch', 'require', 'useState',
                 'useEffect', 'useMemo', 'useCallback', 'useRef', 'useContext', 'useReducer', 'Boolean', 'Number', 'String', 'Array',
                 'Object', 'Date', 'Error', 'Promise', 'describe', 'it', 'expect', 'test', 'next', 'resolve', 'reject', 'callback', 'cb', 'done'}
ROUTE_RX = re.compile(r'\b(app|router|server|api|fastify|r)\s*\.\s*(get|post|put|delete|patch|all|route)\s*\(\s*([\'"`])([^\'"`]+)\3\s*,')
FUNC_RX = [
    re.compile(r'(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\('),
    re.compile(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function\s*\w*\s*\(|\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*(?::\s*[\w<>\[\]|, ]+)?\s*=>|(\w+)\s*=>)'),
    re.compile(r'^\s*(?:static\s+|async\s+|public\s+|private\s+|protected\s+)*(\w+)\s*\(([^()]*)\)\s*(?::\s*[\w<>\[\]|, .]+)?\s*\{', re.M),
    re.compile(r'(?:module\.)?exports\.(\w+)\s*=\s*(?:async\s+)?(?:function\s*\w*\s*\(|\(([^)]*)\)\s*=>)'),
    re.compile(r'^\s*(\w+)\s*:\s*(?:async\s+)?function\s*\('),
]


def _body_after(code: str, pos: int):
    """body of a function whose header ends near pos: returns (open, close) of the braces or an expression end."""
    ob = code.find('{', pos)
    arrow = code.find('=>', pos)
    if arrow >= 0 and (ob < 0 or arrow < ob) and code[arrow + 2:].lstrip()[:1] != '{':
        e = arrow + 2
        depth = 0
        while e < len(code):
            c = code[e]
            if c in '([{':
                depth += 1
            elif c in ')]}':
                if depth == 0:
                    break
                depth -= 1
            elif c in ';\n' and depth == 0:
                break
            e += 1
        return arrow + 2, e
    if ob < 0:
        return pos, pos
    return ob, match_brace(code, ob)


def _calls(body: str, cls: str, file: str, line_of, base: int, imports: dict):
    out = []
    for m in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)((?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\.\s*([A-Za-z_$][\w$]*)\s*\(', body):
        obj, chain, meth = m.group(1), re.sub(r'\s+', '', m.group(2)), m.group(3)
        if obj in JS_BUILTIN_OBJ and obj not in imports:
            if obj == 'this':
                out.append(Call(name=f'{cls}.{meth}' if cls else meth, file=file, line=line_of(base + m.start()), kind='local'))
            continue
        name = f'{imports.get(obj, obj)}{chain}.{meth}'
        p = body.find('(', m.end() - 1)
        out.append(Call(name=name, args=short(body[p + 1:match_paren(body, p)], 160), file=file, line=line_of(base + m.start())))
    for m in re.finditer(r'(?<![\w.$])([A-Za-z_$][\w$]*)\s*\(', body):
        f = m.group(1)
        if f in JS_KW or f in JS_BUILTIN_FN:
            continue
        pre = body[max(0, m.start() - 10):m.start()]
        if re.search(r'(function|new|\.)\s*$', pre):
            continue
        p = body.find('(', m.end() - 1)
        out.append(Call(name=imports.get(f, f), args=short(body[p + 1:match_paren(body, p)], 160), file=file, line=line_of(base + m.start()), kind='local'))
    for m in re.finditer(r'\bnew\s+([A-Z]\w*)\s*\(', body):
        if m.group(1) not in ('Date', 'Error', 'Promise', 'Map', 'Set', 'RegExp', 'Array', 'Object', 'URL', 'FormData', 'Headers', 'Intl'):
            out.append(Call(name=f'{m.group(1)}.constructor', file=file, line=line_of(base + m.start()), kind='new'))
    return out


def _params(body: str, line_of, base=0):
    out = []
    for m in re.finditer(r'\b(?:req|request|ctx\.request|ctx)\s*\.\s*(query|body|params|cookies|headers)\s*\.\s*(\w+)', body):
        out.append(Param(name=m.group(2), source=m.group(1).replace('params', 'path'), line=line_of(base + m.start())))
    for m in re.finditer(r'(?:const|let|var)\s*\{([^}]+)\}\s*=\s*(?:req|request|ctx\.request)\s*\.\s*(query|body|params)', body):
        for n in re.split(r'\s*,\s*', m.group(1)):
            n = n.split(':')[0].split('=')[0].strip()
            if n:
                out.append(Param(name=n, source=m.group(2).replace('params', 'path'), line=line_of(base + m.start())))
    for m in re.finditer(r'searchParams\.get\s*\(\s*[\'"](\w+)', body):
        out.append(Param(name=m.group(1), source='query', line=line_of(base + m.start())))
    return out


def _data_access(body: str, file: str, line_of, base: int, key: str):
    out = C.sql_in(body, file, lambda o: line_of(base + o), key)
    for m in re.finditer(r'\bknex\s*\(\s*[\'"](\w+)[\'"]\s*\)|\.(?:from|into|table)\s*\(\s*[\'"](\w+)[\'"]\s*\)', body):
        t = m.group(1) or m.group(2)
        rest = body[m.end():m.end() + 200]
        kind = 'INSERT' if re.match(r'\s*\.\s*insert', rest) else ('UPDATE' if re.match(r'[\s\S]*?\.\s*update\s*\(', rest[:120]) else
                                                                  ('DELETE' if re.search(r'\.\s*(del|delete)\s*\(', rest[:120]) else 'SELECT'))
        out.append(C.SqlStmt(kind=kind, text=short(f'knex {t} {rest[:80]}', 200), tables=[t], file=file, line=line_of(base + m.start()), function=key))
    for m in re.finditer(r'\bprisma\s*\.\s*(\w+)\s*\.\s*(find\w*|create\w*|update\w*|delete\w*|upsert|count|aggregate|groupBy)\s*\(', body):
        op = m.group(2)
        kind = 'SELECT' if op.startswith(('find', 'count', 'aggregate', 'group')) else ('INSERT' if op.startswith('create') else ('DELETE' if op.startswith('delete') else 'UPDATE'))
        out.append(C.SqlStmt(kind=kind, text=f'prisma.{m.group(1)}.{op}', tables=[m.group(1)], file=file, line=line_of(base + m.start()), function=key))
    for m in re.finditer(r'\b([A-Z]\w*)\s*\.\s*(findAll|findOne|findByPk|findOrCreate|create|bulkCreate|update|destroy|find|findById|insertMany|updateOne|deleteOne|aggregate|countDocuments)\s*\(', body):
        op = m.group(2)
        kind = 'SELECT' if op.startswith(('find', 'count', 'aggregate')) else ('INSERT' if op in ('create', 'bulkCreate', 'insertMany') else ('DELETE' if op in ('destroy', 'deleteOne') else 'UPDATE'))
        out.append(C.SqlStmt(kind=kind, text=f'{m.group(1)}.{op}', tables=[f'model {m.group(1)}'], file=file, line=line_of(base + m.start()), function=key))
    return out


def analyze(sf, project, cfg):
    T = Text(sf.text)
    code = T.code
    F = C.FileFacts(path=sf.path, language='js')
    imports = {}
    for m in re.finditer(r'import\s+(?:(\w+)\s*,?\s*)?(?:\{([^}]*)\})?\s*(?:\*\s+as\s+(\w+))?\s*from\s*[\'"]([^\'"]+)[\'"]', code):
        F.includes.append(m.group(4))
        mod = m.group(4).split('/')[-1]
        if m.group(1):
            imports[m.group(1)] = m.group(1)
        if m.group(3):
            imports[m.group(3)] = m.group(3)
        for n in (m.group(2) or '').split(','):
            n = n.strip()
            if n:
                a = re.split(r'\s+as\s+', n)
                imports[a[-1]] = a[0]
    for m in re.finditer(r'(?:const|let|var)\s+(?:(\w+)|\{([^}]*)\})\s*=\s*require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)', code):
        F.includes.append(m.group(3))
        if m.group(1):
            imports[m.group(1)] = m.group(1)
        for n in (m.group(2) or '').split(','):
            n = n.strip().split(':')[0].strip()
            if n:
                imports[n] = n
    for m in re.finditer(r'\brequire\s*\(\s*[\'"](\.[^\'"]+)[\'"]\s*\)', code):
        F.includes.append(m.group(1))
    F.includes = uniq(F.includes)
    project.js_imports = getattr(project, 'js_imports', {})
    project.js_imports[sf.path] = imports
    # classes
    cls_spans = []
    for m in re.finditer(r'\bclass\s+(\w+)(?:\s+extends\s+([\w.]+))?\s*\{', code):
        b = code.find('{', m.end() - 1)
        cls_spans.append((b, match_brace(code, b), m.group(1)))
        F.classes.append(m.group(1))
        if m.group(2):
            project.class_parent[m.group(1)] = m.group(2).split('.')[-1]
    seen = set()
    for rx in FUNC_RX:
        for m in rx.finditer(code):
            name = m.group(1)
            if name in JS_KW or name in seen and rx is not FUNC_RX[2]:
                continue
            cls = next((c for s, e, c in cls_spans if s < m.start() < e), '')
            if rx is FUNC_RX[2] and not cls:
                continue
            ob, cb = _body_after(code, m.end() - 1 if rx is not FUNC_RX[2] else m.end() - 1)
            body = code[ob + 1:cb] if code[ob:ob + 1] == '{' else code[ob:cb]
            key = f'{cls}.{name}' if cls else (f'{name}' if name not in project.functions else f'{name}@{sf.path}')
            if key in project.functions and project.functions[key].file != sf.path:
                key = f'{key}@{sf.path}'
            seen.add(name)
            base = ob + 1
            fn = Function(key=key, name=name, cls=cls, file=sf.path, line=T.line(m.start()), end_line=T.line(cb), body=body,
                          params=short(m.group(2) if m.lastindex and m.lastindex >= 2 and m.group(2) else '', 160))
            fn.calls = _calls(body, cls, sf.path, T.line, base, imports)
            fn.calls += C.pattern_calls(body, cfg['middle_layer_patterns'], 'middle_layer', sf.path, lambda o, _b=base: T.line(_b + o))
            fn.sql = _data_access(body, sf.path, T.line, base, key)
            fn.messages = C.messages_in(body, lambda o, _b=base: T.line(_b + o))
            fn.params_read = _params(body, T.line, base)
            fn.links = C.links_in(body, lambda o, _b=base: T.line(_b + o))
            fn.branches = switches(body, T.line, sf.path, None, base)
            fn.roles = C.roles_in(body, cfg['auth_patterns'])
            project.functions[key] = fn
            F.functions.append(key)
    # routes
    for m in ROUTE_RX.finditer(code):
        method, route = m.group(2).upper(), m.group(4)
        p = code.find('(', m.start(2))
        q = match_paren(code, p)
        args = code[m.end():q]
        # middleware names (auth) and the handler (last argument)
        parts = _split_args(args)
        handler = parts[-1].strip() if parts else ''
        mids = [x.strip() for x in parts[:-1]]
        hkey = ''
        if re.match(r'(async\s+)?(function|\()|\w+\s*=>|async\s+\w+\s*=>', handler):
            body = handler
            off = m.end() + args.find(handler)
            hkey = f'route:{method} {route}@{sf.path}'
            fn = Function(key=hkey, name=f'{method} {route}', cls='', file=sf.path, line=T.line(m.start()), end_line=T.line(q), body=body)
            fn.calls = _calls(body, '', sf.path, T.line, off, imports)
            fn.calls += C.pattern_calls(body, cfg['middle_layer_patterns'], 'middle_layer', sf.path, lambda o, _b=off: T.line(_b + o))
            fn.sql = _data_access(body, sf.path, T.line, off, hkey)
            fn.messages = C.messages_in(body, lambda o, _b=off: T.line(_b + o))
            fn.params_read = _params(body, T.line, off)
            fn.links = C.links_in(body, lambda o, _b=off: T.line(_b + o))
            fn.branches = switches(body, T.line, sf.path, None, off)
            fn.outputs = _outputs(body)
            project.functions[hkey] = fn
            F.functions.append(hkey)
        else:
            hname = re.sub(r'\s+', '', handler)
            hname = imports.get(hname.split('.')[0], hname.split('.')[0]) + ('.' + hname.split('.', 1)[1] if '.' in hname else '')
            hkey = 'ref:' + hname
        roles = [x for x in mids if re.search(r'auth|role|admin|permission|guard|login|passport|jwt|acl|protect', x, re.I)]
        e = EntryPoint(key=f'{sf.path}#{method} {route}', file=sf.path, kind='endpoint', name=f'{method} {route}', method=method,
                       route=route, handler=hkey, body=handler, line=T.line(m.start()))
        e.middleware_roles = roles
        project.entries.append(e)
    # Next.js API routes / pages
    pm = re.search(r'(?:^|/)pages/(api/.+?|.+?)\.(?:js|jsx|ts|tsx)$', sf.path)
    if pm and re.search(r'export\s+default\b', code):
        route = '/' + re.sub(r'/index$', '', pm.group(1)).replace('[', ':').replace(']', '')
        kind = 'endpoint' if pm.group(1).startswith('api/') else 'page'
        dm = re.search(r'export\s+default\s+(?:async\s+)?function\s*(\w*)', code)
        hkey = dm.group(1) if dm and dm.group(1) in project.functions else ''
        project.entries.append(EntryPoint(key=f'{sf.path}#default', file=sf.path, kind=kind, name=route, method='ANY', route=route,
                                          handler=hkey, body=code, line=1))
    # React Router / Vue Router declarations: <Route path="/x" element={<Comp/>}/>, { path: '/x', component: Comp }
    for m in re.finditer(r'<Route\b[^>]*\bpath\s*=\s*["\']([^"\']+)["\'][^>]*?(?:element\s*=\s*\{\s*<\s*(\w+)|component\s*=\s*\{\s*(\w+))', code):
        project.ui_routes = getattr(project, 'ui_routes', [])
        project.ui_routes.append((m.group(1), m.group(2) or m.group(3), sf.path))
    for m in re.finditer(r'\{\s*path\s*:\s*[\'"]([^\'"]+)[\'"]\s*,\s*(?:name\s*:\s*[\'"][^\'"]*[\'"]\s*,\s*)?component\s*:\s*(\w+)', code):
        project.ui_routes = getattr(project, 'ui_routes', [])
        project.ui_routes.append((m.group(1), m.group(2), sf.path))
    F.links = C.links_in(sf.text, T.line)
    F.forms = C.forms_in(sf.text, sf.path, T.line) if re.search(r'<(form|input|select|textarea)\b', sf.text) else []
    F.messages = C.messages_in(code, T.line)
    F.roles = C.roles_in(code, cfg['auth_patterns'])
    return F


def _outputs(body: str):
    out = []
    if re.search(r'\bres\s*\.\s*(json|send)\s*\(', body):
        out.append(('json', 'JSON response', 0))
    for m in re.finditer(r'\bres\s*\.\s*render\s*\(\s*[\'"]([^\'"]+)', body):
        out.append(('template', m.group(1), 0))
    if re.search(r'\bres\s*\.\s*(download|sendFile|attachment)\s*\(', body):
        out.append(('download', 'file download', 0))
    return out


def _split_args(s: str):
    out, depth, cur = [], 0, ''
    i = 0
    while i < len(s):
        c = s[i]
        if c in '"\'`':
            from ..textutil import skip_string
            j = skip_string(s, i)
            cur += s[i:j]
            i = j
            continue
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        if c == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += c
        i += 1
    if cur.strip():
        out.append(cur)
    return out
