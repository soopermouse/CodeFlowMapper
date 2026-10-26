"""Tooling by function.

Every function a flow reaches (project functions, external library calls, middle-layer calls, SQL run) is given a
capability: a generic one from the rules below (data access, validation, logging ...) or, when no rule applies, the
class it belongs to (a class is one functional unit) or the function itself.
- Platform tool: a capability used by (almost) every flow (platform_share of the flows).
- Tool:          a capability several flows use (tool_min_flows or more).
- Dependency:    a capability, include, class or template only one or two flows use (fewer than tool_min_flows).
The flow's own entry file and handler are the flow itself, not a dependency."""
from __future__ import annotations
import re
from collections import defaultdict
from .model import Tool

RULES = [
    ('Identity and session', r'(?i)authenticat|\blogin\b|logon|session|ticket|SecureSite|currentUser|getCurrentUser|principal|HttpContext\.User|passport'),
    ('Authorisation (roles and rights)', r'(?i)authori[sz]e|hasRole|isInRole|permission|PreAuthorize|\bacl\b|rights?\b|checkAccess|requireRole'),
    ('Configuration and secrets', r'(?i)\bRegistry\b|Registry::|config|getenv|process\.env|ConfigurationManager|IConfiguration|getPassword|secret|getDsn|settings|ConnectionData'),
    ('Middle layer / remote services', r'(?i)requestML|KML::|RPC::|xmlrpc|soap|grpc|HttpClient|RestTemplate|WebClient|axios|getFromBankingRT|callKmlPlugin'),
    ('Data access', r'(?i)(^|[:.>])(getData|query|execute\w*|fetch\w*|exec)$|DBwrapper|AbstractDB|OldDatabase|Database|mysqli?_|PDO|jdbcTemplate|EntityManager|DbContext|Dapper|SqlCommand|knex|prisma|sequelize|mongoose|dbConnect|connectDB|getConnection'),
    ('Validation', r'(?i)valid|sanitize|(^|[:.>])check[A-Z_]|verify|Validator|isNotSqlKeyword|errorCheck'),
    ('Logging and audit', r'(?i)(^|[:.>])log\w*$|Logger|audit|Debug::|K_LOG|K_ERROR|trigger_error|error_log|console\.'),
    ('Documents (PDF) and printing', r'(?i)pdf|FPDF|iText|print[A-Z_]|Printout|borde'),
    ('Excel / CSV export', r'(?i)xls|excel|csv|Spreadsheet|export\w*'),
    ('E-mail and notifications', r'(?i)\bmail|smtp|notify|notification|\bsms\b|sendSms|push'),
    ('Reference data (lists, codes, labels)', r'(?i)countr|currenc|getTypes|AccountType|(^|[:.>])get\w*(List|Types|Labels|Codes|Options)$|lookup|translate|getLabel|i18n|locale|fetchStrings|getMonthName'),
    ('Formatting', r'(?i)format\w*|money_|number_format'),
    ('Page rendering and templates', r'(?i)Template|render|->display|BuildPage|Smarty|setActiveMenu|setPage|setSection|tpl'),
    ('Files and storage', r'(?i)upload|download|file_put|fopen|Storage|Blob|S3'),
    ('Dates and calendars', r'(?i)holiday|calendar|businessDay|workingDay'),
]


def capability(name: str, cls: str, rules) -> str:
    for cap, rx in rules:
        if rx.search(name):
            return cap
    if cls:
        return f'{cls} (class)'
    return f'{name} (function)'


def classify(project, cfg):
    flows = project.flows
    rules = [(r['name'], re.compile(r['match'])) for r in cfg.get('tool_rules', []) if r.get('name') and r.get('match')]
    rules += [(n, re.compile(x)) for n, x in RULES]
    cap_flows = defaultdict(set)
    cap_funcs = defaultdict(set)
    for f in flows:
        own = {f.entry.handler}
        for d, c, k in f.calls:
            if k and k in own:
                continue
            fn = project.functions.get(k) if k else None
            if c.kind == 'middle_layer':
                cap = 'Middle layer / remote services'
                label = c.name + (f" '{c.target}'" if c.target else '')
            elif fn:
                if fn.file == f.entry.file and not fn.cls:
                    continue         # the page's own functions are the flow itself
                stem = re.sub(r'\..*$', '', fn.file.split('/')[-1])
                cap = capability(fn.key.split('@')[0], fn.cls or f'{stem}', rules)
                if not fn.cls and cap == f'{stem} (class)':
                    cap = f'{stem} (module)'
                label = fn.key.split('@')[0].split('#')[0]
            else:
                # library / framework calls count only when they are a generic capability (configuration, logging ...)
                cap = next((n for n, rx in rules if rx.search(c.name)), '')
                if not cap:
                    continue
                label = c.name
            cap_flows[cap].add(f.id)
            cap_funcs[cap].add(label)
        if f.sql:
            cap_flows['Data access'].add(f.id)
            for s in f.sql:
                cap_funcs['Data access'].add(f'{s.kind} {", ".join(s.tables) or s.procedure}'.strip())
        if f.roles:
            cap_flows['Authorisation (roles and rights)'].add(f.id)
        if f.templates:
            cap_flows['Page rendering and templates'].add(f.id)
    n = max(1, len(flows))
    mn = int(cfg.get('tool_min_flows', 3))
    share = float(cfg.get('platform_share', 0.9))
    funcs_of = {f.id: f.functionality for f in flows}
    tools = []
    for cap, fl in cap_flows.items():
        kind = 'Platform tool' if len(fl) >= max(mn, share * n) else ('Tool' if len(fl) >= mn else 'Dependency')
        tools.append(Tool(id='', name=cap, kind=kind, functions=sorted(cap_funcs[cap]), flows=sorted(fl),
                          functionalities=sorted({funcs_of[x] for x in fl})))
    order = {'Platform tool': 0, 'Tool': 1, 'Dependency': 2}
    tools.sort(key=lambda t: (order[t.kind], -len(t.flows), t.name.lower()))
    ti = di = 0
    for t in tools:
        if t.kind == 'Dependency':
            di += 1
            t.id = f'D-{di:02d}'
        else:
            ti += 1
            t.id = f'T-{ti:02d}'
    project.tools = tools
    by_flow = defaultdict(list)
    for t in tools:
        for x in t.flows:
            by_flow[x].append(t.id)
    for f in flows:
        f.tools = [t for t in by_flow[f.id] if t.startswith('T-')]
        f.dependencies = [t for t in by_flow[f.id] if t.startswith('D-')]
    # files: includes / classes / templates per flow (the entry file itself excluded)
    file_flows = defaultdict(set)
    for f in flows:
        for p in f.files[1:]:
            file_flows[p].add(f.id)
    project.file_dependencies = []
    for p, fl in sorted(file_flows.items(), key=lambda kv: (len(kv[1]), kv[0])):
        sf = project.files.get(p)
        kind = 'template' if sf and sf.language in ('template', 'html') else ('class / module' if p.endswith(('.php', '.java', '.cs', '.js', '.ts')) and not p.endswith('.inc') else 'include')
        project.file_dependencies.append({'file': p, 'kind': kind, 'flows': sorted(fl), 'type': 'Shared file' if len(fl) >= mn else 'Dependency',
                                          'functionalities': sorted({funcs_of[x] for x in fl})})
    project.note(f'Tooling: {sum(t.kind != "Dependency" for t in tools)} tools, {sum(t.kind == "Dependency" for t in tools)} dependencies, '
                 f'{len(project.file_dependencies)} files used by the flows.')
