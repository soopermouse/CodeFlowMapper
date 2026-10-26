"""Flows: one per entry point (page, endpoint, controller action, servlet, route), optionally one per case of a
request-parameter switch. Each flow follows its calls through the project (call_depth levels) and gathers the
forms and fields, decisions, calls with arguments, SQL, stored procedures, tables, middle-layer calls, messages,
outputs and links. Then module / submodule / functionality, flow ids, and upstream / downstream flows."""
from __future__ import annotations
import os, posixpath, re
from collections import defaultdict
from .model import Flow, Call, SqlStmt, Form, Field_
from .textutil import uniq, short
from .analyzers import common as C
from .analyzers import php as PHP, clike as CL, js as JS
from .analyzers.csharp import dto_fields

EF_OPS = r'(Where|Add|AddAsync|AddRange|Remove|RemoveRange|Find|FindAsync|First\w*|Single\w*|ToList\w*|Include|Update|UpdateRange|Any\w*|Count\w*|OrderBy\w*|Select|FromSqlRaw|FromSqlInterpolated|AsNoTracking)'
REPO_WRITE = re.compile(r'^(save|saveAll|saveAndFlush|delete\w*|insert\w*|update\w*|persist|merge|remove\w*)$')
WRITE_SP = re.compile(r'(?i)(^|[_.])(add|ins|insert|upd|update|del|delete|set|save|create|remove|modify|commit|reset|ack|block|release|cancel|link|unlink|import)')


class Resolver:
    def __init__(self, project):
        self.p = project
        self.by_name = defaultdict(list)
        for k, f in project.functions.items():
            self.by_name[f.name].append(k)
        self.paths = list(project.files)
        self.by_base = defaultdict(list)
        for p in self.paths:
            self.by_base[posixpath.basename(p).lower()].append(p)

    # ---------------- files
    def file(self, ref: str, ctx: str = '') -> str:
        if not ref:
            return ''
        r = ref.replace('\\', '/').split('?')[0].split('#')[0]
        r = re.sub(r'^(\./)+', '', r)
        if r.startswith(('http:', 'https:', '//')):
            r = re.sub(r'^(https?:)?//[^/]+', '', r)
        if ctx and (ref.startswith('.') or '/' not in r):
            cand = posixpath.normpath(posixpath.join(posixpath.dirname(ctx), ref.split('?')[0]))
            for c in self._variants(cand):
                if c in self.p.files:
                    return c
        r = r.lstrip('/')
        for c in self._variants(r):
            if c in self.p.files:
                return c
            hits = [p for p in self.paths if p.endswith('/' + c)]
            if len(hits) == 1:
                return hits[0]
            if hits and ctx:
                return sorted(hits, key=lambda h: -len(os.path.commonprefix([h, ctx])))[0]
        base = posixpath.basename(r).lower()
        hits = self.by_base.get(base, [])
        if len(hits) == 1:
            return hits[0]
        if hits and ctx:
            return sorted(hits, key=lambda h: -len(os.path.commonprefix([h, ctx])))[0]
        return ''

    @staticmethod
    def _variants(r: str):
        yield r
        if not os.path.splitext(r)[1] or r.endswith(('.component', '.service')):
            for e in ('.js', '.ts', '.jsx', '.tsx', '.mjs', '/index.js', '/index.ts', '.php', '.inc', '.vue'):
                yield r + e

    def java_import(self, imp: str) -> str:
        p = imp.replace('.', '/') + '.java'
        hits = [x for x in self.paths if x.endswith(p)]
        return hits[0] if hits else ''

    # ---------------- functions
    def function(self, call: Call, ctx_file: str, ctx_cls: str, lang: str, reach_files=()) -> str:
        n = call.name
        fs = self.p.functions
        if n in fs:
            return n
        if lang == 'php':
            if '::' in n:
                cls, meth = n.split('::', 1)
                if not cls.startswith('$'):
                    c = cls
                    seen = set()
                    while c and c not in seen:
                        seen.add(c)
                        if f'{c}::{meth}' in fs:
                            return f'{c}::{meth}'
                        c = self.p.class_parent.get(c, '')
                    return ''
                meth = n.rsplit('->', 1)[-1]
                return self._unique(meth, reach_files, ctx_file, method=True)
            if '->' in n:
                return self._unique(n.rsplit('->', 1)[-1], reach_files, ctx_file, method=True)
            # plain function
            ks = [k for k in self.by_name.get(n, []) if not fs[k].cls]
            return self._pick(ks, reach_files, ctx_file)
        # java / csharp / js: Type.method
        if '.' in n:
            t, meth = n.rsplit('.', 1)
            t0 = t.split('.')[-1]
            t0 = re.sub(r'<.*', '', t0)
            for c in self._types(t0):
                if f'{c}.{meth}' in fs:
                    return f'{c}.{meth}'
            if lang == 'js':
                # imported module object: method defined in the imported file
                ks = self.by_name.get(meth, [])
                return self._pick(ks, reach_files, ctx_file)
            return ''
        ks = self.by_name.get(n, [])
        if lang == 'js':
            same = [k for k in ks if fs[k].file == ctx_file and not fs[k].cls]
            if same:
                return same[0]
            return self._pick([k for k in ks if not fs[k].cls], reach_files, ctx_file)
        return ''

    def _types(self, t: str):
        out, todo, seen = [], [t], set()
        while todo:
            c = todo.pop(0)
            if c in seen or not c:
                continue
            seen.add(c)
            out.append(c)
            todo += self.p.implementations.get(c, [])
            if self.p.class_parent.get(c):
                todo.append(self.p.class_parent[c])
        return out

    def _unique(self, meth, reach_files, ctx_file, method=False):
        ks = [k for k in self.by_name.get(meth, []) if self.p.functions[k].cls or not method]
        return self._pick(ks, reach_files, ctx_file)

    def _pick(self, ks, reach_files, ctx_file):
        if not ks:
            return ''
        if len(ks) == 1:
            return ks[0]
        inr = [k for k in ks if self.p.functions[k].file in reach_files or self.p.functions[k].file == ctx_file]
        if len(inr) == 1:
            return inr[0]
        return ''


# ------------------------------------------------------------------ helpers
def humanize(s: str) -> str:
    s = re.sub(r'\.(class\.php|php\d?|html?|inc|tpl|jsp|aspx|cshtml|cs|java|js|ts|tsx|jsx|phtml)$', '', s, flags=re.I)
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s)
    s = re.sub(r'[_\-]+', ' ', s).strip()
    return (s[:1].upper() + s[1:]) if s else s


def lang_of(project, path):
    sf = project.files.get(path)
    return sf.language if sf else ''


def route_segments(route: str):
    segs = [x for x in re.split(r'[/?#]', route or '') if x]
    return [s for s in segs if not re.match(r'^(\{.*\}|:\w+|\[.*\]|\d+|\*+)$', s)]


def _split_case_flows(entry, facts):
    """cases of the first top-level switch on a request parameter, when the entry has no forms (endpoint style)."""
    if not facts:
        return []
    sw = [b for b in facts.branches if b.kind == 'switch' and len(b.cases) >= 2]
    if not sw or (facts.forms and any(f.fields for f in facts.forms)):
        return []
    return sw[0]


def _calls_of_text(lang, text, file, cls=''):
    if lang == 'php':
        return PHP._calls(text, cls, '', PHP._types(text), file, lambda o: 0, 0)
    if lang in ('java', 'csharp'):
        return CL.calls_in(text, cls, {}, file, lambda o: 0, 0, lang)
    if lang == 'js':
        return JS._calls(text, cls, file, lambda o: 0, 0, {})
    return []


# ------------------------------------------------------------------ build
def build_flows(project, cfg, progress=None):
    R = Resolver(project)
    depth_max = int(cfg.get('call_depth', 4))
    flows = []
    for e in project.entries:
        facts = project.facts.get(e.file)
        lang = lang_of(project, e.file)
        cases = _split_case_flows(e, facts) if (cfg.get('split_switch_flows', True) and not e.handler and facts) else []
        if cases:
            for label, text, line in cases.cases:
                fl = _collect(project, R, e, facts, lang, depth_max, cfg, case=(cases.subject, label, text))
                flows.append(fl)
        else:
            flows.append(_collect(project, R, e, facts, lang, depth_max, cfg))
    _classify(project, flows, cfg)
    flows.sort(key=lambda f: (f.module.lower(), f.submodule.lower(), f.functionality.lower(), f.entry.file, f.entry.route, f.name))
    for i, f in enumerate(flows, 1):
        f.id = f'FLW-{i:03d}'
    project.flows = flows
    _edges(project, R, flows)
    project.note(f'Flows: {len(flows)} built from {len(project.entries)} entry points.')
    return flows


def _collect(project, R, e, facts, lang, depth_max, cfg, case=None):
    fl = Flow(id='', entry=e, name='')
    fl.origin = project.files[e.file].origin if e.file in project.files else 'code'
    reach_files = [e.file]
    # includes (PHP transitive, JS / Java imports)
    todo = list((facts.includes if facts else []))
    seen_inc = set()
    while todo:
        ref = todo.pop(0)
        if lang == 'java':
            p = R.java_import(ref)
        elif lang == 'csharp':
            p = ''
        else:
            p = R.file(ref, e.file)
        if p and p not in seen_inc and p != e.file:
            seen_inc.add(p)
            reach_files.append(p)
            ff = project.facts.get(p)
            if ff and lang == 'php':
                todo += ff.includes
        elif not p and lang in ('php',) and ref:
            fl.unresolved.append(f'include not found: {ref}')
    # starting code
    start_calls, start_sql, start_msgs, start_links = [], [], [], []
    hf = project.functions.get(e.handler) if e.handler and not e.handler.startswith('ref:') else None
    if e.handler.startswith('ref:') if e.handler else False:
        k = R.function(Call(name=e.handler[4:]), e.file, '', lang, reach_files)
        hf = project.functions.get(k) if k else None
        if hf:
            e.handler = k
    if case:
        subject, label, text = case
        start_calls = _calls_of_text(lang, text, e.file) + C.pattern_calls(text, cfg['middle_layer_patterns'], 'middle_layer', e.file, lambda o: 0)
        start_sql = C.sql_in(text, e.file, lambda o: 0) + C.procs_by_api(text, e.file, lambda o: 0)
        start_msgs = C.messages_in(text, lambda o: 0)
        start_links = C.links_in(text, lambda o: 0)
        fl.params = (facts.params if facts else [])
        fl.case = (subject, label)
    elif hf:
        start_calls = list(hf.calls)
        start_sql = list(hf.sql)
        start_msgs = list(hf.messages)
        start_links = list(hf.links)
        fl.params = list(hf.params_read)
        fl.branches = list(hf.branches)
        fl.roles += hf.roles
        fl.outputs += hf.outputs
        fl.connections += hf.connections
        fl.functions.append(hf.key)
        if hf.file not in reach_files:
            reach_files.append(hf.file)
        dto = getattr(hf, 'dto', '')
        if dto:
            fields, msgs = dto_fields(project, dto)
            if fields:
                fl.forms.append(Form(name=f'Request body ({dto})', action=e.route, method=e.method, fields=fields, file=fields[0].file or e.file, line=hf.line))
            start_msgs += msgs
    elif facts:
        start_calls = list(facts.top_calls)
        start_sql = list(facts.sql)
        start_msgs = list(facts.messages)
        start_links = list(facts.links)
        fl.params = list(facts.params)
        fl.branches = list(facts.branches)
        fl.outputs += facts.outputs
    if facts:
        fl.roles += facts.roles
        fl.connections += facts.connections
        if not hf or lang != 'php':
            pass
        if not case and not hf:
            fl.forms += facts.forms
        if case is None and hf is None:
            pass
    fl.roles += getattr(e, 'middleware_roles', [])
    fl.sql += start_sql
    fl.messages += start_msgs
    fl.links += start_links
    # follow calls
    visited = set(fl.functions)
    queue = [(c, 0, e.file, '') for c in start_calls]
    ctx_cls = hf.cls if hf else ''
    if hf:
        queue = [(c, 0, hf.file, hf.cls) for c in start_calls]
    while queue:
        c, d, cfile, ccls = queue.pop(0)
        if c.kind == 'middle_layer':
            fl.middle_layer.append(c)
            fl.calls.append((d, c, ''))
            continue
        k = R.function(c, cfile, ccls, lang_of(project, cfile) or lang, reach_files)
        if not k and c.kind == 'local':
            continue
        if not k:
            if _external_worth(c, lang):
                fl.calls.append((d, c, ''))
                fl.unresolved.append(f'not found in the project: {c.name}')
            continue
        c.target = k
        fl.calls.append((d, c, k))
        if k in visited:
            continue
        visited.add(k)
        fn = project.functions[k]
        fl.functions.append(k)
        if fn.file not in reach_files:
            reach_files.append(fn.file)
        fl.sql += fn.sql
        fl.messages += fn.messages
        fl.links += fn.links
        fl.connections += fn.connections
        fl.roles += fn.roles
        if d <= 1:
            fl.outputs += fn.outputs
        if d == 0 and not fl.branches:
            fl.branches += fn.branches
        # repository / DbSet data access
        _repo_sql(project, fn, fl)
        if d + 1 <= depth_max:
            queue += [(cc, d + 1, fn.file, fn.cls) for cc in fn.calls]
    if hf:
        _repo_sql(project, hf, fl)
    # templates rendered -> their forms, links, messages
    for kind, name, line in uniq(fl.outputs):
        if kind != 'template':
            continue
        t = _template_file(R, name, e.file)
        if t:
            fl.templates.append(t)
            if t not in reach_files:
                reach_files.append(t)
            tf = project.facts.get(t)
            if tf:
                fl.forms += tf.forms
                fl.links += tf.links
                fl.messages += tf.messages
                for inc in tf.includes:
                    p = _template_file(R, inc, t)
                    if p and p not in reach_files:
                        reach_files.append(p)
                        pf = project.facts.get(p)
                        if pf:
                            fl.forms += pf.forms
        else:
            fl.templates.append(name)
    fl.templates = uniq(fl.templates)
    # what each case of the decisions does
    fl.branch_detail = []
    for b in fl.branches[:8]:
        cases = []
        for label, text, line in b.cases[:12]:
            cl = []
            for c in _calls_of_text(lang, text, b.file):
                k = R.function(c, b.file, ctx_cls, lang, reach_files)
                if k or (c.kind != 'local' and _external_worth(c, lang)) or c.kind == 'middle_layer':
                    cl.append((c.name, short(c.args, 80), k))
            cl += [(c.name, short(c.args, 80), '') for c in C.pattern_calls(text, cfg['middle_layer_patterns'], 'middle_layer', b.file, lambda o: 0)]
            sq = [(s_.kind, s_.tables, s_.procedure) for s_ in C.sql_in(text, b.file, lambda o: 0) + C.procs_by_api(text, b.file, lambda o: 0)]
            ms = [m for m, _ in C.messages_in(text, lambda o: 0)]
            lk = [u for u, k_, _ in C.links_in(text, lambda o: 0)]
            cases.append({'label': label, 'calls': uniq(cl)[:10], 'sql': sq[:6], 'messages': ms[:4], 'links': lk[:4], 'line': line})
        fl.branch_detail.append({'subject': b.subject, 'kind': b.kind, 'cases': cases, 'line': b.line, 'file': b.file})
    # result
    fl.files = uniq(reach_files)
    fl.sql = uniq_sql(fl.sql)
    fl.tables = uniq([t for s in fl.sql for t in s.tables])
    fl.procedures = uniq([s.procedure for s in fl.sql if s.procedure])
    fl.messages = uniq([m for m, _ in fl.messages]) if fl.messages and isinstance(fl.messages[0], tuple) else uniq(fl.messages)
    fl.links = uniq(fl.links)
    fl.roles = uniq([r for r in fl.roles if r])
    fl.connections = uniq(fl.connections)
    fl.outputs = uniq(fl.outputs)
    fl.forms = _uniq_forms(fl.forms)
    fl.params = uniq([(p.source, p.name) for p in fl.params])
    fl.issues = [dict(i, file=f) for f in fl.files for i in (project.files[f].issues if f in project.files else [])]
    # names
    title = facts.title if facts else ''
    if case:
        act = humanize(case[1].strip('\'"')) or case[1]
        fl.name = f'{humanize(posixpath.basename(e.file))}: {act}'
        fl.business = f'{title}: {act}' if title else ''
    elif hf and e.kind != 'page':
        fl.name = humanize(hf.name) if hf.name and not hf.key.startswith(('route:', 'minimal:')) else e.name
        fl.business = title or ''
    else:
        stem = posixpath.basename(e.file)
        fl.name = title or humanize(stem)
        fl.business = title
    return fl


def _external_worth(c: Call, lang: str) -> bool:
    n = c.name
    if re.search(r'Exception\b', n):
        return False
    if lang == 'php':
        return '::' in n and not n.startswith('$') and n.split('::')[0] not in ('self', 'static', 'parent')
    if lang in ('java', 'csharp'):
        return '.' in n and c.kind != 'local' and n.split('.')[0][:1].isupper()
    if lang == 'js':
        return '.' in n and c.kind != 'local'
    return False


def _repo_sql(project, fn, fl):
    repos = getattr(project, 'repositories', {})
    dbsets = getattr(project, 'dbsets', {})
    for c in fn.calls:
        if '.' not in c.name:
            continue
        t, meth = c.name.rsplit('.', 1)
        if t in repos:
            ent = repos[t]
            table = project.entities.get(ent, ent)
            kind = 'INSERT/UPDATE' if REPO_WRITE.match(meth) else 'SELECT'
            if meth.startswith('delete'):
                kind = 'DELETE'
            fl.sql.append(SqlStmt(kind=kind, text=f'{t}.{meth}({short(c.args, 60)}) on entity {ent}', tables=[table], file=fn.file, line=c.line, function=fn.key))
    for m in re.finditer(r'\.(\w+)\s*\.\s*' + EF_OPS + r'\s*\(', fn.body):
        if m.group(1) in dbsets:
            op = m.group(2)
            kind = 'INSERT' if op.startswith('Add') else ('DELETE' if op.startswith('Remove') else ('UPDATE' if op.startswith('Update') else 'SELECT'))
            ent = dbsets[m.group(1)]
            fl.sql.append(SqlStmt(kind=kind, text=f'{m.group(1)}.{op} (Entity Framework, {ent})', tables=[project.entities.get(ent, m.group(1))],
                                  file=fn.file, line=fn.line, function=fn.key))


def _template_file(R, name, ctx):
    if not name:
        return ''
    cands = [name]
    if not os.path.splitext(name)[1]:
        cands += [name + e for e in ('.html', '.jsp', '.cshtml', '.tpl', '.twig', '.ejs', '.hbs', '.pug', '.vue')]
        cands += ['templates/' + name + '.html', 'views/' + name + '.ejs', 'WEB-INF/views/' + name + '.jsp', 'Views/' + name + '.cshtml']
    for c in cands:
        p = R.file(c, ctx)
        if p:
            return p
    return ''


def uniq_sql(sql):
    seen, out = set(), []
    for s in sql:
        k = (s.kind, s.text[:200], s.procedure, s.function)
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def _uniq_forms(forms):
    seen, out = set(), []
    for f in forms:
        k = (f.file, f.name, f.action, tuple((x.name, x.kind) for x in f.fields))
        if k not in seen and f.fields:
            seen.add(k)
            out.append(f)
    return out


# ------------------------------------------------------------------ module / submodule / functionality
def _classify(project, flows, cfg):
    noise = set(x.lower() for x in cfg.get('path_noise', []))
    rules = [(re.compile(r['match'], re.I), r) for r in cfg.get('modules', []) if r.get('match')]
    frules = [(re.compile(r['match'], re.I), r) for r in cfg.get('functionalities', []) if r.get('match')]
    for f in flows:
        e = f.entry
        target = e.route if e.kind in ('endpoint', 'controller_action', 'servlet') and e.route else e.file
        mod = sub = ''
        for rx, r in rules:
            m = rx.search(target) or rx.search(e.file)
            if m:
                mod = m.expand(r.get('module', '')) if r.get('module') else ''
                sub = m.expand(r.get('submodule', '')) if r.get('submodule') else ''
                break
        if not mod:
            if target == e.route:
                segs = [s for s in route_segments(e.route) if s.lower() not in noise]
                if len(segs) >= 2:
                    segs = segs[:-1]           # the last segment is the action
                if not segs:
                    segs = [s for s in _path_segs(e.file, noise)]
            else:
                segs = _path_segs(e.file, noise)
            mod = segs[0] if segs else 'Application'
            if len(segs) > 1:
                sub = segs[1]
            else:
                cls = (project.functions.get(e.handler).cls if e.handler in project.functions else '')
                sub = re.sub(r'(Controller|Resource|Servlet|Page|Handler|Routes?|Api)$', '', cls) or mod
        f.module = humanize(mod)
        f.submodule = humanize(sub)
        if f.submodule.lower().rstrip('s') == f.module.lower().rstrip('s'):
            f.submodule = f.module
        f.functionality = f'{f.module} > {f.submodule}' if f.submodule and f.submodule != f.module else f.module
        for rx, r in frules:
            if rx.search(e.file) or rx.search(e.route or ''):
                f.functionality = r.get('name', f.functionality)
                f.module = r.get('module', f.module)
                f.submodule = r.get('submodule', f.submodule)
                break


def _path_segs(path, noise):
    parts = path.split('/')[:-1]
    segs = [p for p in parts if p.lower() not in noise and not re.fullmatch(r'v\d+|\d+', p)]
    if not segs:
        stem = re.sub(r'\..*$', '', path.split('/')[-1])
        segs = [stem]
    return segs


# ------------------------------------------------------------------ upstream / downstream
def _route_rx(route: str):
    r = re.sub(r'\{[^}]*\}|:\w+|\[[^\]]*\]|\*\*?', '\x00', route.strip('/'))
    r = re.escape(r).replace('\x00', '[^/]+')
    return re.compile(r'^/?' + r + r'/?$', re.I)


def _edges(project, R, flows):
    by_file = defaultdict(list)
    routes = []
    for f in flows:
        by_file[f.entry.file].append(f)
        if f.entry.route and f.entry.kind != 'page':
            routes.append((_route_rx(f.entry.route), f))
    edges = []
    for a in flows:
        for u, kind, line in a.links:
            url = re.sub(r'^(https?:)?//[^/]+', '', u).split('#')[0]
            path, _, query = url.partition('?')
            path = re.sub(r'<\?.*?\?>|\{\{.*?\}\}|\$\{[^}]*\}|@\w+(\.\w+)*', 'X', path)
            targets = []
            cands = [path]
            if path and '/' not in path and a.entry.route and a.entry.kind != 'page':
                cands.append(a.entry.route.rsplit('/', 1)[0] + '/' + path)     # relative action / RedirectToAction
            if path and '/' not in path and getattr(a, 'controller_prefix', ''):
                cands.append(a.controller_prefix + '/' + path)
            for cand in cands:
                for rx, b in routes:
                    if rx.match(cand):
                        targets.append(b)
                if targets:
                    break
            if not targets and path:
                p = R.file(path, a.entry.file)
                if p and p in by_file:
                    cand = by_file[p]
                    # a link to a case flow: match the request parameter value in the query string
                    qvals = set(re.findall(r'=([\w\-]+)', query))
                    sel = [b for b in cand if getattr(b, 'case', None) and any(v.strip('\'"') in qvals for v in b.case[1].split(' / '))]
                    targets = sel or cand
            for b in targets:
                if b is not a:
                    edges.append((a.id, b.id, {'link': 'Link', 'redirect': 'Redirect', 'ajax': 'AJAX call', 'popup': 'Pop-up'}.get(kind, kind), u))
    # data: a flow writing a table is upstream of the flows reading it
    writers, readers = defaultdict(set), defaultdict(set)
    for f in flows:
        for s in f.sql:
            w = s.kind in ('INSERT', 'UPDATE', 'DELETE', 'MERGE', 'INSERT/UPDATE', 'REPLACE', 'TRUNCATE') or (s.procedure and WRITE_SP.search(s.procedure))
            for t in s.tables:
                (writers if w else readers)[t.lower()].add(f.id)
    for t in writers:
        for w in writers[t]:
            for r in readers.get(t, ()):
                if w != r:
                    edges.append((w, r, 'Data (table)', t))
    seen = set()
    project.edges = []
    for e in edges:
        k = (e[0], e[1], e[2], e[3])
        if k not in seen:
            seen.add(k)
            project.edges.append(e)
    ids = {f.id: f for f in flows}
    for a, b, kind, via in project.edges:
        if b not in ids[a].downstream:
            ids[a].downstream.append(b)
        if a not in ids[b].upstream:
            ids[b].upstream.append(a)
