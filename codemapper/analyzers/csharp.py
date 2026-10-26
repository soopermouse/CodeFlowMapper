"""C#: ASP.NET MVC / Web API controllers, minimal APIs, Razor Pages handlers, Web Forms code-behind events;
services resolved through interfaces, ADO.NET / Dapper / EF SQL, stored procedures, DbSet tables, DataAnnotations."""
from __future__ import annotations
import re
from ..model import EntryPoint, Param
from ..textutil import Text, short, uniq
from . import common as C
from . import clike

HTTP_ATTR = re.compile(r'\[\s*Http(Get|Post|Put|Delete|Patch)\s*(?:\(\s*"([^"]*)"[^)]*\))?\s*\]')
ROUTE_ATTR = re.compile(r'\[\s*Route\s*\(\s*"([^"]*)"\s*\)\s*\]')


def analyze(sf, project, cfg):
    T = Text(sf.text)
    F = C.FileFacts(path=sf.path, language='csharp')
    F.includes = re.findall(r'^\s*using\s+(?:static\s+)?([\w.]+)\s*;', T.code, re.M)
    clike.parse(sf, project, cfg, T, F, 'csharp')
    for cls in F.classes:
        ann = project.class_ann.get(cls, '')
        parent = project.class_parent.get(cls, '')
        ctrl = cls.endswith('Controller') or parent in ('Controller', 'ControllerBase', 'ApiController')
        api = parent in ('ControllerBase', 'ApiController') or '[ApiController]' in ann
        page_model = parent == 'PageModel'
        webform = parent in ('Page', 'System.Web.UI.Page', 'UserControl') or sf.path.endswith(('.aspx.cs', '.ascx.cs'))
        cname = re.sub(r'Controller$', '', cls)
        rm = ROUTE_ATTR.search(ann)
        prefix = (rm.group(1) if rm else '').replace('[controller]', cname)
        for key in [k for k in F.functions if k.split('#')[0].startswith(cls + '.')]:
            fn = project.functions[key]
            a = fn.annotations
            vis = fn.visibility
            route = method = kind = ''
            if ctrl and 'public' in vis and '[NonAction]' not in a and fn.name != cls and 'static' not in vis:
                hm = HTTP_ATTR.search(a)
                ra = ROUTE_ATTR.search(a)
                method = hm.group(1).upper() if hm else ('POST' if fn.name.startswith(('Create', 'Update', 'Delete', 'Save', 'Post')) and api else 'GET')
                sub = (hm.group(2) if hm and hm.group(2) is not None else (ra.group(1) if ra else ''))
                sub = sub.replace('[action]', fn.name)
                if prefix or sub:
                    route = '/' + '/'.join(x.strip('/') for x in (prefix, sub) if x and x.strip('/')) if not sub.startswith('/') else sub
                else:
                    route = f'/{cname}/{fn.name}'
                route = route.replace('[action]', fn.name)
                kind = 'endpoint' if api else 'controller_action'
            elif page_model and re.match(r'On(Get|Post|Put|Delete)\w*(Async)?$', fn.name):
                method = re.match(r'On(Get|Post|Put|Delete)', fn.name).group(1).upper()
                p = re.sub(r'\.cshtml\.cs$', '', sf.path)
                p = re.sub(r'^.*?/Pages/', '/', p)
                route = p if p.startswith('/') else '/' + p
                kind = 'page'
            elif webform and (fn.name == 'Page_Load' or re.search(r'_(Click|Command|SelectedIndexChanged|TextChanged|RowCommand)$', fn.name)):
                route = '/' + re.sub(r'\.cs$', '', sf.path).split('/')[-1]
                method = 'GET' if fn.name == 'Page_Load' else 'POST'
                kind = 'page'
            else:
                continue
            params = []
            for pm in re.finditer(r'(?:\[\s*From(Query|Body|Route|Form|Header)\s*(?:\([^)]*\))?\s*\]\s*)?(' + clike.TYPE + r')\s+(\w+)\s*(?:=[^,]+)?(?:,|$)', fn.params + ','):
                src = (pm.group(1) or '').lower() or ('body' if pm.group(2)[0].isupper() and pm.group(2) not in ('String', 'Int32', 'DateTime', 'Guid', 'Boolean', 'Decimal') and method in ('POST', 'PUT', 'PATCH') else 'query')
                if pm.group(2) in ('CancellationToken', 'HttpContext', 'object', 'EventArgs', 'sender'):
                    continue
                params.append(Param(name=pm.group(3), source=src, line=fn.line))
                if src in ('body', 'form'):
                    fn.dto = clike._base_type(pm.group(2))
            for pm in re.finditer(r'Request\.(Query|Form|QueryString|Params|Cookies)\[\s*"([^"]+)"', fn.body):
                params.append(Param(name=pm.group(2), source=pm.group(1).lower(), line=fn.line))
            fn.params_read = params
            outs = []
            vm = re.findall(r'\b(?:View|PartialView)\s*\(\s*"([^"]+)"', fn.body)
            for v in vm:
                outs.append(('template', v, fn.line))
            if re.search(r'\breturn\s+(?:View|PartialView)\s*\(\s*\)|\breturn\s+(?:View|PartialView)\s*\(\s*\w+\s*\)', fn.body) and not vm:
                outs.append(('template', f'Views/{cname}/{fn.name}.cshtml', fn.line))
            if page_model:
                outs.append(('template', re.sub(r'\.cs$', '', sf.path), fn.line))
            if re.search(r'\b(Json|Ok|Created|CreatedAtAction|BadRequest|NotFound|NoContent)\s*\(', fn.body) or api:
                outs.append(('json', 'JSON response', fn.line))
            if re.search(r'\bFile\s*\(|FileContentResult|FileStreamResult', fn.body):
                outs.append(('download', 'file download', fn.line))
            fn.outputs = uniq(outs)
            project.entries.append(EntryPoint(key=f'{sf.path}#{key}', file=sf.path, kind=kind, name=f'{cls}.{fn.name}', method=method,
                                              route=route, handler=key, body=fn.body, line=fn.line))
    # minimal APIs: app.MapGet("/x", handler)
    for m in re.finditer(r'\b\w+\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"\s*,', T.code):
        start = m.end()
        end = T.code.find(');', start)
        body = T.code[start:end if end > 0 else start + 2000]
        from ..model import Function
        key = f'minimal:{m.group(1).upper()} {m.group(2)}'
        fn = Function(key=key, name=f'Map{m.group(1)} {m.group(2)}', cls='', file=sf.path, line=T.line(m.start()), end_line=T.line(start + len(body)), body=body)
        fn.calls = clike.calls_in(body, '', {}, sf.path, T.line, start, 'csharp')
        fn.sql = C.sql_in(body, sf.path, lambda o: T.line(start + o), key)
        fn.outputs = [('json', 'JSON response', fn.line)]
        project.functions[key] = fn
        F.functions.append(key)
        project.entries.append(EntryPoint(key=f'{sf.path}#{key}', file=sf.path, kind='endpoint', name=fn.name, method=m.group(1).upper(),
                                          route=m.group(2), handler=key, body=body, line=fn.line))
    return F


def dto_fields(project, dto: str):
    """fields of a request model class with their validation attributes / annotations -> [Field_], [messages]."""
    from ..model import Field_
    out, msgs = [], []
    for k, f in project.facts.items():
        if dto not in f.classes:
            continue
        sf = project.files.get(k)
        if not sf:
            continue
        m = re.search(r'\b(?:class|record)\s+' + re.escape(dto) + r'\b[^{]*\{', sf.text)
        if not m:
            continue
        from ..textutil import match_brace
        e = match_brace(sf.text, sf.text.find('{', m.end() - 1))
        body = sf.text[m.end():e]
        for fm in re.finditer(r'((?:\s*(?:\[[^\]]+\]|@\w+(?:\([^)]*\))?))*)\s*(?:public|private|protected)?\s*(?:final\s+)?(' + clike.TYPE + r')\s+(\w+)\s*(?:\{\s*get|;|=)', body):
            ann, typ, name = fm.group(1) or '', clike._base_type(fm.group(2)), fm.group(3)
            if typ in ('class', 'return', 'static') or name in ('get', 'set'):
                continue
            kind = 'checkbox' if typ.lower() in ('bool', 'boolean') else ('date' if 'Date' in typ else ('number' if typ.lower() in ('int', 'long', 'integer', 'decimal', 'double', 'float', 'bigdecimal', 'short') else 'text'))
            if re.search(r'Email', ann):
                kind = 'email'
            if re.search(r'\[DataType\(DataType\.Password\)\]|Password', ann):
                kind = 'password'
            f_ = Field_(name=name, kind=kind, required=bool(re.search(r'\[Required|@NotNull|@NotBlank|@NotEmpty', ann)), file=k)
            mx = re.search(r'(?:StringLength|MaxLength|Size\s*\([^)]*max)\s*\(?\s*=?\s*(\d+)', ann)
            if mx:
                f_.maxlength = mx.group(1)
            pt = re.search(r'(?:RegularExpression|Pattern)\s*\(\s*(?:regexp\s*=\s*)?@?"([^"]+)"', ann)
            if pt:
                f_.pattern = pt.group(1)
            dm = re.search(r'\[Display\(\s*Name\s*=\s*"([^"]+)"', ann)
            if dm:
                f_.label = dm.group(1)
            out.append(f_)
            for mm in re.finditer(r'(?:message|ErrorMessage)\s*=\s*"([^"]+)"', ann):
                msgs.append((mm.group(1), 0))
        break
    return out, msgs
