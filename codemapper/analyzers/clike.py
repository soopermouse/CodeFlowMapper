"""Shared parsing for Java and C#: classes with annotations / attributes, fields and their types, methods with bodies,
calls resolved through field / local / parameter types, SQL, stored procedures, entity -> table mappings."""
from __future__ import annotations
import re
from ..model import Function, Call
from ..textutil import match_brace, match_paren, short, uniq
from . import common as C
from .branches import switches, ifs

CTRL = {'if', 'for', 'foreach', 'while', 'switch', 'catch', 'using', 'lock', 'return', 'new', 'throw', 'synchronized', 'typeof',
        'nameof', 'sizeof', 'default', 'checked', 'unchecked', 'fixed', 'await', 'super', 'this', 'base', 'else', 'do', 'try', 'case',
        'when', 'select', 'where', 'from', 'yield', 'var', 'get', 'set', 'is', 'as', 'in', 'out', 'ref', 'params'}
MOD = r'(?:(?:public|private|protected|internal|static|final|abstract|virtual|override|sealed|async|synchronized|native|partial|new|unsafe|extern|readonly|default)\s+)*'
TYPE = r'[\w.]+(?:\s*<[^<>;{}()]*(?:<[^<>;{}()]*>[^<>;{}()]*)*>)?(?:\s*\[\s*\])*\??'
ANN = r'(?:@[\w.]+(?:\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))?|\[[^\]]+\])'
METHOD_RX = re.compile(r'(?P<ann>(?:\s*' + ANN + r')*)\s*(?P<mod>' + MOD + r')(?:<[^>]+>\s*)?(?P<ret>' + TYPE + r')\s+(?P<name>\w+)\s*\(')
CLASS_RX = re.compile(r'(?P<ann>(?:\s*' + ANN + r')*)\s*' + MOD +
                      r'(?P<kind>class|interface|record|enum|struct)\s+(?P<name>\w+)(?:\s*<[^>]*>)?(?P<rest>[^{;]*)\{')
STATIC_SKIP = {'System', 'Math', 'String', 'Integer', 'Long', 'Double', 'Boolean', 'Arrays', 'Collections', 'Objects', 'List', 'Map',
               'Set', 'Optional', 'Stream', 'Collectors', 'LocalDate', 'LocalDateTime', 'DateTime', 'Convert', 'Console', 'Guid', 'Enumerable',
               'Task', 'Path', 'File', 'Directory', 'Encoding', 'Regex', 'Pattern', 'Integer', 'BigDecimal', 'UUID', 'Thread', 'Instant',
               'Duration', 'TimeUnit', 'StringUtils', 'Logger', 'LoggerFactory', 'log', 'logger', 'LOG', 'LOGGER', '_logger', 'Debug',
               'Trace', 'Assert', 'Character', 'Float', 'Short', 'Byte', 'Decimal', 'TimeSpan', 'Uri', 'Json', 'JsonConvert', 'JSON',
               'Html', 'Url', 'ViewBag', 'ViewData', 'TempData', 'Request', 'Response', 'HttpContext', 'Environment', 'Activator'}
BUILTIN_METHODS = {'toString', 'equals', 'hashCode', 'get', 'set', 'add', 'put', 'remove', 'size', 'isEmpty', 'contains', 'length',
                   'trim', 'substring', 'split', 'format', 'valueOf', 'parse', 'append', 'stream', 'map', 'filter', 'collect', 'forEach',
                   'orElse', 'orElseThrow', 'ToString', 'Equals', 'GetHashCode', 'Add', 'Remove', 'Contains', 'Count', 'Any', 'Where',
                   'Select', 'First', 'FirstOrDefault', 'Single', 'SingleOrDefault', 'ToList', 'ToArray', 'OrderBy', 'OrderByDescending',
                   'GroupBy', 'Sum', 'Max', 'Min', 'Trim', 'Substring', 'Split', 'Replace', 'StartsWith', 'EndsWith', 'ToUpper', 'ToLower',
                   'IsNullOrEmpty', 'IsNullOrWhiteSpace', 'Parse', 'TryParse', 'ConfigureAwait', 'Wait', 'Result', 'getMessage',
                   'printStackTrace', 'info', 'debug', 'warn', 'error', 'trace', 'Info', 'Debug', 'Warn', 'Error', 'LogInformation',
                   'LogError', 'LogWarning', 'LogDebug', 'isPresent', 'ifPresent', 'of', 'asList', 'keySet', 'values', 'entrySet', 'getKey',
                   'getValue', 'close', 'Dispose', 'replace', 'toUpperCase', 'toLowerCase', 'startsWith', 'endsWith', 'indexOf', 'charAt',
                   'compareTo', 'getClass', 'getName', 'Include', 'ThenInclude', 'AsNoTracking', 'Skip', 'Take', 'Join', 'Distinct'}


def fields_of(body: str):
    """field / property name -> type (class body only, not inside methods)."""
    t = {}
    for m in re.finditer(r'(?:^|[;{}\]\)])\s*(?:@[\w.]+(?:\([^)]*\))?\s*)*' + MOD + r'(' + TYPE + r')\s+(\w+)\s*(?:[;=]|\{\s*get)', body):
        typ, name = m.group(1), m.group(2)
        if typ in ('return', 'new', 'throw', 'else', 'package', 'import', 'using', 'namespace'):
            continue
        t[name] = _base_type(typ)
    # constructor-injected parameters
    for m in re.finditer(r'(?:\(|,)\s*(?:@\w+\s*)*(?:final\s+)?(' + TYPE + r')\s+(\w+)\s*(?=[,)])', body):
        t.setdefault(m.group(2), _base_type(m.group(1)))
    return t


def _base_type(typ: str) -> str:
    typ = re.sub(r'\s+', '', typ).rstrip('?')
    m = re.match(r'([\w.]+)<(.+)>$', typ)
    if m and m.group(1).split('.')[-1] in ('List', 'IList', 'IEnumerable', 'Optional', 'Set', 'ICollection', 'Collection', 'Task', 'Lazy', 'Mono', 'Flux', 'IQueryable', 'DbSet'):
        return m.group(1).split('.')[-1] + '<' + _base_type(m.group(2).split(',')[0]) + '>'
    return re.sub(r'<.*', '', typ).split('.')[-1].replace('[]', '')


def calls_in(body: str, cls: str, types: dict, file: str, line_of, base: int, lang: str):
    out = []
    local = dict(types)
    for m in re.finditer(r'(?<![\w.])(' + TYPE + r')\s+(\w+)\s*=', body):
        if m.group(1) not in ('return', 'var', 'new', 'else'):
            local[m.group(2)] = _base_type(m.group(1))
    for m in re.finditer(r'\b(?:var|val|final\s+var)\s+(\w+)\s*=\s*new\s+([\w.]+)', body):
        local[m.group(1)] = m.group(2).split('.')[-1]
    for m in re.finditer(r'(?<![\w.])(?:(this|base|super)\s*\.\s*)?([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(', body):
        recv, meth = m.group(2), m.group(3)
        if m.group(1) in ('base', 'super'):
            continue
        t = local.get(recv)
        if t is None and recv[0].isupper():
            t = recv     # static call or type name
        if t is None or t in STATIC_SKIP or recv in STATIC_SKIP:
            continue
        if meth in BUILTIN_METHODS and not t[0].isupper():
            continue
        p = body.find('(', m.end() - 1)
        out.append(Call(name=f'{t}.{meth}', args=short(body[p + 1:match_paren(body, p)], 160), file=file, line=line_of(base + m.start())))
    for m in re.finditer(r'(?<![\w.])(?:this\s*\.\s*)?([a-zA-Z_]\w*)\s*\(', body):
        f = m.group(1)
        pre = body[max(0, m.start() - 12):m.start()]
        if f in CTRL or re.search(r'(new|\.)\s*$', pre) or (f[0].isupper() and lang == 'java'):
            continue
        if m.group(0).startswith('this') or True:
            p = body.find('(', m.end() - 1)
            out.append(Call(name=f'{cls}.{f}', args=short(body[p + 1:match_paren(body, p)], 160), file=file, line=line_of(base + m.start()), kind='local'))
    for m in re.finditer(r'\bnew\s+([A-Z][\w.]*)\s*(?:<[^>]*>)?\s*\(', body):
        t = m.group(1).split('.')[-1]
        if t not in STATIC_SKIP and not t.endswith(('Exception', 'Builder', 'List', 'Map', 'Dictionary', 'Set', 'StringBuilder')):
            out.append(Call(name=f'{t}.<init>', file=file, line=line_of(base + m.start()), kind='new'))
    return out


def parse(sf, project, cfg, T, F, lang: str):
    code = T.code
    line_of = T.line
    for cm in CLASS_RX.finditer(code):
        name = cm.group('name')
        b = code.find('{', cm.end() - 1)
        e = match_brace(code, b)
        body = code[b + 1:e]
        ann = cm.group('ann') or ''
        rest = cm.group('rest') or ''
        F.classes.append(name)
        project.class_ann = getattr(project, 'class_ann', {})
        project.class_ann[name] = ann
        # parent / interfaces
        sup = re.findall(r'(?:extends|implements|:)\s*([\w.<>,\s]+)', rest)
        bases = [_base_type(x.strip()) for s in sup for x in re.split(r',(?![^<]*>)', s) if x.strip()]
        bases = [b_ for b_ in bases if b_ not in ('extends', 'implements')]
        if bases:
            project.class_parent[name] = bases[0]
            for b_ in bases:
                project.implementations.setdefault(b_, []).append(name)
        # entity -> table
        tm = re.search(r'@Table\s*\(\s*(?:name\s*=\s*)?"([^"]+)"|\[Table\(\s*"([^"]+)"', ann)
        if tm:
            project.entities[name] = tm.group(1) or tm.group(2)
        elif re.search(r'@Entity\b', ann):
            project.entities[name] = name
        # Spring Data repository: interface X extends JpaRepository<Entity, Id>
        rm = re.search(r'(?:Jpa|Crud|PagingAndSorting|Mongo|Reactive\w*)Repository\s*<\s*(\w+)', rest)
        if rm:
            project.repositories = getattr(project, 'repositories', {})
            project.repositories[name] = rm.group(1)
        types = fields_of(_strip_methods(body))
        # EF DbSet<T> Name -> table Name
        for dm in re.finditer(r'DbSet\s*<\s*(\w+)\s*>\s+(\w+)', body):
            project.entities.setdefault(dm.group(1), dm.group(2))
            project.dbsets = getattr(project, 'dbsets', {})
            project.dbsets[dm.group(2)] = dm.group(1)
        # methods
        for mm in METHOD_RX.finditer(body):
            mname, ret = mm.group('name'), mm.group('ret')
            if ret in CTRL or mname in CTRL or ret in ('new', 'return', 'else', 'throw', 'await'):
                continue
            p = body.find('(', mm.end() - 1)
            q = match_paren(body, p)
            after = body[q + 1:q + 200]
            am = re.match(r'\s*(?:throws\s+[\w.,\s]+)?(?:where\s+[^{]+)?\s*(\{|=>|;)', after)
            if not am:
                continue
            if am.group(1) == ';':
                if ann_is_query(mm.group('ann')):
                    pass
                else:
                    continue
            if am.group(1) == '{':
                ob = q + 1 + am.end() - 1
                ee = match_brace(body, ob)
                fb = body[ob + 1:ee]
                fbase = b + 1 + ob + 1
            elif am.group(1) == '=>':
                ob = q + 1 + am.end()
                ee = body.find(';', ob)
                fb = body[ob:ee]
                fbase = b + 1 + ob
            else:
                ee = q + 1 + am.end()
                fb = ''
                fbase = b + 1 + q
            key = f'{name}.{mname}'
            if key in project.functions:
                key = f'{key}#{len(project.functions)}'
            fn = Function(key=key, name=mname, cls=name, file=sf.path, line=line_of(b + 1 + mm.start('name')), end_line=line_of(b + 1 + ee),
                          body=fb, params=short(body[p + 1:q], 200), visibility=mm.group('mod').strip())
            fn.annotations = (mm.group('ann') or '').strip()
            ptypes = {}
            for pm in re.finditer(r'(?:@\w+(?:\([^)]*\))?\s*|\[\w+(?:\([^)]*\))?\]\s*)*(?:final\s+)?(' + TYPE + r')\s+(\w+)\s*(?:[,)=]|$)', body[p + 1:q] + ')'):
                ptypes[pm.group(2)] = _base_type(pm.group(1))
            fn.ptypes = ptypes
            fn.calls = calls_in(fb, name, {**types, **ptypes}, sf.path, line_of, fbase, lang)
            fn.calls += C.pattern_calls(fb, cfg['middle_layer_patterns'], 'middle_layer', sf.path, lambda o, _b=fbase: line_of(_b + o))
            lo = (lambda o, _b=fbase: line_of(_b + o))
            fn.sql = C.sql_in(fb, sf.path, lo, key) + C.procs_by_api(fb, sf.path, lo, key)
            qm = re.search(r'@Query\s*\(\s*(?:value\s*=\s*)?"((?:[^"\\]|\\.)*)"', fn.annotations, re.S)
            if qm:
                kind, tables, proc = C.parse_sql(qm.group(1))
                if not tables and re.search(r'\bFROM\s+(\w+)', qm.group(1), re.I):
                    tables = [re.search(r'\bFROM\s+(\w+)', qm.group(1), re.I).group(1)]
                fn.sql.append(C.SqlStmt(kind=kind if kind != 'SQL' else 'SELECT', text=short(qm.group(1), 400), tables=tables, procedure=proc,
                                        file=sf.path, line=fn.line, function=key))
            pm2 = re.search(r'@Procedure\s*\(\s*(?:name\s*=\s*|procedureName\s*=\s*|value\s*=\s*)?"([^"]+)"', fn.annotations)
            if pm2:
                fn.sql.append(C.SqlStmt(kind='EXEC', text=f'stored procedure {pm2.group(1)}', procedure=pm2.group(1), file=sf.path, line=fn.line, function=key))
            fn.messages = C.messages_in(fb, lo) + C.messages_in(fn.annotations, lo)
            req_ok = lambda s: True
            fn.branches = switches(fb, line_of, sf.path, None, fbase)
            fn.links = C.links_in(fb, lo)
            fn.connections = C.connections_in(fb, cfg['connection_patterns'])
            fn.roles = C.roles_in(fn.annotations + ' ' + fb, cfg['auth_patterns'])
            project.functions[key] = fn
            F.functions.append(key)
    # class-level authorisation applies to every handler of the class; method-level roles stay on the method
    F.roles = uniq([r for c in F.classes for r in C.roles_in(project.class_ann.get(c, ''), cfg['auth_patterns'])])
    F.connections = C.connections_in(code, cfg['connection_patterns'])
    F.messages = C.messages_in(code, line_of)


def ann_is_query(ann: str) -> bool:
    return bool(re.search(r'@(Query|Procedure|Select|Insert|Update|Delete)\b', ann or ''))


def _strip_methods(body: str) -> str:
    """class body with method bodies blanked, to read fields only."""
    out = list(body)
    depth = 0
    for i, c in enumerate(body):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif depth > 0 and c != '\n':
            out[i] = ' '
    return ''.join(out)
