"""Java: Spring MVC / REST controllers, JAX-RS resources, servlets (annotation or web.xml), Struts-style actions;
services, repositories (Spring Data -> entity table), JDBC / JPA SQL, stored procedures, Bean Validation messages."""
from __future__ import annotations
import re
from ..model import EntryPoint, Param
from ..textutil import Text, short, uniq
from . import common as C
from . import clike

MAP_RX = re.compile(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*(?:\(\s*(?P<args>[^)]*)\))?')
JAXRS_RX = re.compile(r'@(GET|POST|PUT|DELETE|PATCH)\b')


def _route_of(args: str) -> str:
    if not args:
        return ''
    m = re.search(r'(?:value|path)\s*=\s*\{?\s*"([^"]*)"', args) or re.search(r'^\s*\{?\s*"([^"]*)"', args)
    return m.group(1) if m else ''


def _method_of(kind: str, args: str) -> str:
    if kind != 'Request':
        return kind.upper()
    m = re.findall(r'RequestMethod\.(\w+)', args or '')
    return ','.join(m) if m else 'ANY'


def analyze(sf, project, cfg):
    T = Text(sf.text)
    F = C.FileFacts(path=sf.path, language='java')
    F.includes = re.findall(r'^\s*import\s+(?:static\s+)?([\w.]+)\s*;', T.code, re.M)
    clike.parse(sf, project, cfg, T, F, 'java')
    for cls in F.classes:
        ann = project.class_ann.get(cls, '')
        prefix = ''
        m = re.search(r'@RequestMapping\s*\(([^)]*)\)', ann)
        if m:
            prefix = _route_of(m.group(1))
        m = re.search(r'@Path\s*\(\s*"([^"]*)"', ann)
        if m:
            prefix = m.group(1)
        is_ctrl = bool(re.search(r'@(Rest)?Controller\b|@Path\b', ann))
        rest = bool(re.search(r'@RestController\b|@Path\b', ann))
        servlet = project.class_parent.get(cls) in ('HttpServlet', 'GenericServlet')
        sroute = ''
        sm = re.search(r'@WebServlet\s*\(\s*(?:(?:value|urlPatterns)\s*=\s*)?\{?\s*"([^"]+)"', ann)
        if sm:
            sroute = sm.group(1)
        for key in [k for k in F.functions if k.split('#')[0].startswith(cls + '.')]:
            fn = project.functions[key]
            a = fn.annotations
            mm = MAP_RX.search(a)
            jm = JAXRS_RX.search(a)
            route = method = ''
            if is_ctrl and (mm or jm):
                if mm:
                    route = _join(prefix, _route_of(mm.group('args') or ''))
                    method = _method_of(mm.group(1), mm.group('args') or '')
                else:
                    pm = re.search(r'@Path\s*\(\s*"([^"]*)"', a)
                    route = _join(prefix, pm.group(1) if pm else '')
                    method = jm.group(1)
                kind = 'endpoint' if rest or '@ResponseBody' in a else 'controller_action'
            elif servlet and fn.name in ('doGet', 'doPost', 'doPut', 'doDelete', 'service'):
                route = sroute or getattr(project, 'servlet_routes', {}).get(cls, '')
                method = {'doGet': 'GET', 'doPost': 'POST', 'doPut': 'PUT', 'doDelete': 'DELETE'}.get(fn.name, 'ANY')
                kind = 'servlet'
            elif project.class_parent.get(cls, '').endswith(('Action', 'DispatchAction')) and fn.name in ('execute',):
                kind, method = 'controller_action', 'ANY'
            else:
                continue
            params = []
            for pm in re.finditer(r'@(RequestParam|PathVariable|RequestHeader|CookieValue|RequestBody|ModelAttribute|QueryParam|PathParam|FormParam)\s*(?:\(\s*(?:(?:value|name)\s*=\s*)?"?(\w*)"?[^)]*\))?\s*(?:final\s+)?(' + clike.TYPE + r')\s+(\w+)', fn.params):
                src = {'RequestParam': 'query', 'PathVariable': 'path', 'RequestHeader': 'header', 'CookieValue': 'cookie',
                       'RequestBody': 'body', 'ModelAttribute': 'form', 'QueryParam': 'query', 'PathParam': 'path', 'FormParam': 'form'}[pm.group(1)]
                params.append(Param(name=pm.group(2) or pm.group(4), source=src, line=fn.line))
                if src in ('body', 'form'):
                    fn.dto = clike._base_type(pm.group(3))
            for pm in re.finditer(r'getParameter\s*\(\s*"([^"]+)"', fn.body):
                params.append(Param(name=pm.group(1), source='request', line=fn.line))
            fn.params_read = params
            outs = []
            for om in re.finditer(r'return\s+"(?!redirect:|forward:)([\w/\-]+)"\s*;', fn.body):
                outs.append(('template', om.group(1), fn.line))
            for om in re.finditer(r'new\s+ModelAndView\s*\(\s*"([^"]+)"', fn.body):
                outs.append(('template', om.group(1), fn.line))
            for om in re.finditer(r'getRequestDispatcher\s*\(\s*"([^"]+)"', fn.body):
                outs.append(('template', om.group(1), fn.line))
            if kind in ('endpoint',) or re.search(r'ResponseEntity|@ResponseBody', a + fn.body):
                outs.append(('json', 'JSON response', fn.line))
            fn.outputs = uniq(outs)
            project.entries.append(EntryPoint(key=f'{sf.path}#{key}', file=sf.path, kind=kind, name=f'{cls}.{fn.name}', method=method,
                                              route=route, handler=key, body=fn.body, line=fn.line))
    # web.xml servlet mappings
    return F


def _join(a: str, b: str) -> str:
    r = '/' + '/'.join(x.strip('/') for x in (a, b) if x and x.strip('/'))
    return r


def web_xml(sf, project):
    names = dict(re.findall(r'<servlet-name>\s*([^<]+?)\s*</servlet-name>\s*<servlet-class>\s*([^<]+?)\s*</servlet-class>', sf.text, re.S))
    routes = {}
    for n, u in re.findall(r'<servlet-mapping>\s*<servlet-name>\s*([^<]+?)\s*</servlet-name>\s*<url-pattern>\s*([^<]+?)\s*</url-pattern>', sf.text, re.S):
        cls = names.get(n, '')
        if cls:
            routes[cls.split('.')[-1]] = u
    project.servlet_routes = {**getattr(project, 'servlet_routes', {}), **routes}
