"""PHP: pages and endpoints, includes, classes and functions, calls (static, instance, functions), request parameters,
switch / if decisions on request parameters, SQL and stored procedures, templates, JSON / download / redirect outputs."""
from __future__ import annotations
import re
from ..model import Function, Call, Param
from ..textutil import Text, match_brace, match_paren, strings, short, uniq, ext
from . import common as C
from .branches import switches, ifs

KEYWORDS = {'if', 'elseif', 'else', 'while', 'for', 'foreach', 'switch', 'case', 'return', 'function', 'array', 'list', 'isset', 'unset',
            'empty', 'echo', 'print', 'include', 'include_once', 'require', 'require_once', 'new', 'catch', 'die', 'exit', 'eval',
            'declare', 'use', 'fn', 'match', 'clone', 'instanceof', 'and', 'or', 'not', 'global', 'static', 'self', 'parent'}
BUILTINS = set('''strlen count trim ltrim rtrim substr strpos stripos strrpos str_replace str_ireplace sprintf printf number_format
implode explode join in_array array_key_exists array_keys array_values array_merge array_map array_filter array_push array_pop
array_shift array_unshift array_slice array_splice array_search array_unique array_reverse array_flip array_sum array_combine
array_fill array_diff array_intersect array_walk sort rsort ksort krsort asort arsort usort uasort uksort is_array is_numeric
is_int is_string is_null is_bool is_object is_float intval floatval strval boolval settype gettype date time mktime strtotime
checkdate gmdate strftime date_default_timezone_set microtime round floor ceil abs max min pow sqrt rand mt_rand htmlspecialchars
htmlentities html_entity_decode strip_tags addslashes stripslashes nl2br urlencode urldecode rawurlencode base64_encode
base64_decode json_encode json_decode serialize unserialize md5 sha1 crc32 hash uniqid preg_match preg_match_all preg_replace
preg_split preg_quote preg_replace_callback ereg eregi ereg_replace split strtolower strtoupper ucfirst ucwords lcfirst wordwrap
str_pad str_repeat str_split strrev strcmp strcasecmp strncmp strncasecmp strstr stristr strrchr substr_count mb_strlen mb_substr
mb_strtolower mb_strtoupper mb_convert_encoding utf8_encode utf8_decode iconv header setcookie session_start session_destroy
session_id ob_start ob_get_clean ob_end_clean ob_get_contents flush define defined constant function_exists method_exists
class_exists property_exists get_class is_a is_subclass_of call_user_func call_user_func_array func_get_args file_exists
is_file is_dir file fopen fclose fread fwrite fgets fputs feof file_get_contents file_put_contents unlink mkdir rmdir copy
rename basename dirname pathinfo realpath tempnam glob scandir opendir readdir closedir is_writable is_readable filesize
mail error_reporting ini_set ini_get set_time_limit trigger_error error_log var_dump print_r var_export debug_backtrace
array_key_last array_key_first range compact extract reset end next prev current key each list printf vsprintf sscanf
money_format chr ord bin2hex hex2bin dechex hexdec decbin bindec octdec number_format localeconv setlocale nl_langinfo
filter_var filter_input http_build_query parse_str parse_url get_object_vars spl_autoload_register class_implements
iterator_to_array ctype_digit ctype_alpha ctype_alnum ctype_space ctype_upper ctype_lower mysql_real_escape_string
array_count_values array_change_key_case array_column array_chunk array_pad natsort natcasesort shuffle array_rand
str_word_count similar_text levenshtein soundex metaphone money date_create date_diff date_add date_format checkdnsrr
gethostbyname ip2long long2ip is_callable usleep sleep exec shell_exec system passthru escapeshellarg proc_open
'''.split())
SUPER = re.compile(r'\$_(GET|POST|REQUEST|COOKIE|SESSION|FILES|SERVER)\s*\[\s*([\'"])?([\w\-]+)\2?\s*\]')
FILTER_IN = re.compile(r'filter_input\s*\(\s*INPUT_(GET|POST|COOKIE|SERVER)\s*,\s*[\'"]([\w\-]+)')


def php_only(raw: str) -> str:
    """keep PHP regions, blank HTML regions (same length, newlines kept)."""
    if '<?' not in raw:
        return raw
    out = []
    i, n = 0, len(raw)
    while i < n:
        j = raw.find('<?', i)
        if j < 0:
            out.append(re.sub(r'[^\n]', ' ', raw[i:]))
            break
        out.append(re.sub(r'[^\n]', ' ', raw[i:j]))
        k = raw.find('?>', j + 2)
        k = n if k < 0 else k + 2
        seg = raw[j:k]
        # mark echo short tags as statements so HTML around them stays separate
        out.append(seg)
        i = k
    return ''.join(out)


def _include_targets(code: str):
    out = []
    for m in re.finditer(r'\b(?:require|include)(?:_once)?\b\s*\(?\s*([^;?]+?)\)?\s*;', code):
        expr = m.group(1)
        parts = [v for _, v in strings(expr)]
        if parts:
            out.append((''.join(parts).lstrip('./') if len(parts) > 1 else parts[-1], m.start()))
    return out


def _calls(code: str, cls: str, parent: str, types: dict, file: str, line_of, base: int):
    calls = []
    for m in re.finditer(r'(?<![\w$\\])(\\?[A-Za-z_][\w\\]*)\s*::\s*(\w+)\s*\(', code):
        c, meth = m.group(1).lstrip('\\').split('\\')[-1], m.group(2)
        if c in ('self', 'static'):
            c = cls or c
        elif c == 'parent':
            c = parent or c
        p = code.find('(', m.end() - 1)
        calls.append(Call(name=f'{c}::{meth}', args=short(code[p + 1:match_paren(code, p)], 160), file=file, line=line_of(base + m.start())))
    for m in re.finditer(r'\$(\w+)((?:\s*->\s*\w+)*)\s*->\s*(\w+)\s*\(', code):
        var, chain, meth = m.group(1), re.sub(r'\s+', '', m.group(2)), m.group(3)
        if var == 'this' and not chain:
            name = f'{cls}::{meth}' if cls else f'$this->{meth}'
        else:
            key = var + chain
            t = types.get(key) or (types.get(chain.split('->')[-1]) if chain else None)
            name = f'{t}::{meth}' if t else f'${var}{chain}->{meth}'
        p = code.find('(', m.end() - 1)
        calls.append(Call(name=name, args=short(code[p + 1:match_paren(code, p)], 160), file=file, line=line_of(base + m.start())))
    for m in re.finditer(r'(?<![\w$>:\\])new\s+\\?([A-Z_a-z][\w\\]*)\s*\(', code):
        c = m.group(1).split('\\')[-1]
        calls.append(Call(name=f'{c}::__construct', file=file, line=line_of(base + m.start()), kind='new'))
    for m in re.finditer(r'(?<![\w$>:\\.])([a-zA-Z_]\w*)\s*\(', code):
        f = m.group(1)
        if f.lower() in KEYWORDS or f in BUILTINS or f.lower() in BUILTINS:
            continue
        pre = code[max(0, m.start() - 10):m.start()]
        if re.search(r'(function|new|->|::)\s*$', pre):
            continue
        p = code.find('(', m.end() - 1)
        calls.append(Call(name=f, args=short(code[p + 1:match_paren(code, p)], 160), file=file, line=line_of(base + m.start())))
    return calls


def _types(code: str, cls_props: dict | None = None):
    t = dict(cls_props or {})
    for m in re.finditer(r'\$(\w+(?:->\w+)*)\s*=\s*(?:&\s*)?new\s+\\?([A-Za-z_][\w\\]*)', code):
        t[m.group(1).replace('this->', '')] = m.group(2).split('\\')[-1]
        t[m.group(1)] = m.group(2).split('\\')[-1]
    for m in re.finditer(r'\$(\w+(?:->\w+)*)\s*=\s*\\?([A-Z][\w\\]*)::(?:getInstance|instance|singleton|factory|create|get)\w*\s*\(', code):
        t[m.group(1).replace('this->', '')] = m.group(2).split('\\')[-1]
    for m in re.finditer(r'(?:\(|,)\s*\\?([A-Z][\w\\]*)\s+\$(\w+)', code):   # typed parameters
        t[m.group(2)] = m.group(1).split('\\')[-1]
    return t


def _params(code: str, line_of, base=0):
    out = []
    for m in SUPER.finditer(code):
        if m.group(1) in ('SERVER',):
            continue
        out.append(Param(name=m.group(3), source=m.group(1), line=line_of(base + m.start())))
    for m in FILTER_IN.finditer(code):
        out.append(Param(name=m.group(2), source=m.group(1), line=line_of(base + m.start())))
    return out


def _request_vars(code: str):
    """variables assigned from request parameters ($action = $_GET['action'])."""
    return set(re.findall(r'\$(\w+)\s*=\s*(?:\(?\s*(?:isset\s*\()?\s*)?(?:trim\s*\(|intval\s*\(|\(int\)\s*|htmlspecialchars\s*\()?\s*\$_(?:GET|POST|REQUEST)\b', code))


def _outputs(code: str, raw: str, line_of):
    out = []
    for m in re.finditer(r'->\s*(?:display|fetch|render|parse|assign_by_ref_tpl)\s*\(\s*[\'"]([^\'"]+\.(?:tpl|html|php|twig))[\'"]', code):
        out.append(('template', m.group(1), line_of(m.start())))
    for m in re.finditer(r'new\s+\w*(?:Template|Smarty|Tpl|View)\w*\s*\(\s*[\'"]([^\'"]+)[\'"]', code, re.I):
        out.append(('template', m.group(1), line_of(m.start())))
    for _, v in strings(code):
        if re.fullmatch(r'[\w/.\-]+\.(?:tpl|twig|phtml)', v):
            out.append(('template', v, 0))
    if re.search(r'json_encode\s*\(', code) and re.search(r'\becho\b|print\b|exit\s*\(|die\s*\(', code):
        out.append(('json', 'JSON response', 0))
    if re.search(r'Content-Type:\s*application/json', code, re.I):
        out.append(('json', 'JSON response', 0))
    m = re.search(r'Content-Disposition:\s*attachment[^\'"]*', code, re.I)
    if m:
        out.append(('download', short(m.group(0), 80), line_of(m.start())))
    m = re.search(r'Content-Type:\s*([\w/.+\-]+)', code, re.I)
    if m and 'json' not in m.group(1) and 'html' not in m.group(1):
        out.append(('download', m.group(1), line_of(m.start())))
    if re.search(r'<(html|table|div|form|body)\b', raw, re.I) or re.search(r'\becho\s+[\'"]\s*<', code):
        out.append(('html', 'HTML page', 0))
    return uniq(out)


def analyze(sf, project, cfg):
    raw = sf.text.replace('\r\n', '\n')
    code_src = php_only(raw)
    T = Text(code_src)
    code = T.code
    F = C.FileFacts(path=sf.path, language='php')
    line_of = T.line
    F.includes = [p for p, _ in _include_targets(code)]
    spans = []
    # classes and methods
    for m in re.finditer(r'\b(?:abstract\s+|final\s+)?(class|interface|trait)\s+(\w+)(?:\s+extends\s+([\w\\]+))?(?:\s+implements\s+([\w\\,\s]+))?\s*\{', code):
        kind, cls, parent = m.group(1), m.group(2), (m.group(3) or '').split('\\')[-1]
        b = code.find('{', m.end() - 1)
        e = match_brace(code, b)
        spans.append((m.start(), e))
        F.classes.append(cls)
        body = code[b + 1:e]
        props = {}
        for pm in re.finditer(r'\$this->(\w+)\s*=\s*(?:&\s*)?new\s+\\?([A-Za-z_][\w\\]*)', body):
            props[pm.group(1)] = pm.group(2).split('\\')[-1]
        for pm in re.finditer(r'@var\s+\\?([A-Z][\w\\]*)\s*\*/\s*(?:public|private|protected|var)\s+\$(\w+)', T.raw[b:e]):
            props.setdefault(pm.group(2), pm.group(1).split('\\')[-1])
        project.class_parent[cls] = parent
        for fm in re.finditer(r'((?:(?:public|private|protected|static|final|abstract)\s+)*)function\s+&?\s*(\w+)\s*\(', body):
            p = body.find('(', fm.end() - 1)
            q = match_paren(body, p)
            ob = body.find('{', q)
            semi = body.find(';', q)
            if ob < 0 or (0 <= semi < ob):
                continue
            ee = match_brace(body, ob)
            fb = body[ob + 1:ee]
            base = b + 1 + ob + 1
            _add_function(project, F, sf, cls, parent, fm.group(2), body[p + 1:q], fm.group(1).strip(), fb, base, line_of,
                          b + 1 + fm.start(), b + 1 + ee, props, cfg, raw)
    # functions outside classes
    for fm in re.finditer(r'(?<![\w>$:])function\s+&?\s*(\w+)\s*\(', code):
        if any(s <= fm.start() <= e for s, e in spans):
            continue
        p = code.find('(', fm.end() - 1)
        q = match_paren(code, p)
        ob = code.find('{', q)
        if ob < 0:
            continue
        ee = match_brace(code, ob)
        spans.append((fm.start(), ee))
        _add_function(project, F, sf, '', '', fm.group(1), code[p + 1:q], '', code[ob + 1:ee], ob + 1, line_of, fm.start(), ee, {}, cfg, raw)
    # top-level code
    top = list(code)
    for s, e in spans:
        for i in range(s, min(e + 1, len(top))):
            if top[i] != '\n':
                top[i] = ' '
    top = ''.join(top)
    F.top_code = top
    types = _types(top)
    F.top_calls = [c for c in _calls(top, '', '', types, sf.path, line_of, 0)]
    F.top_calls += C.pattern_calls(top, cfg['middle_layer_patterns'], 'middle_layer', sf.path, line_of)
    F.params = _params(top, line_of)
    F.sql = C.sql_in(top, sf.path, line_of) + C.procs_by_api(top, sf.path, line_of)
    F.messages = C.messages_in(top, line_of) + C.messages_in(re.sub(r'<\?.*?\?>', ' ', raw, flags=re.S), Text(raw).line)
    F.roles = C.roles_in(code, cfg['auth_patterns'])
    F.connections = C.connections_in(code, cfg['connection_patterns'])
    F.links = C.links_in(raw, Text(raw).line)
    F.forms = C.forms_in(raw, sf.path, Text(raw).line)
    F.outputs = _outputs(top, raw, line_of)
    F.templates = [o[1] for o in F.outputs if o[0] == 'template']
    F.title = C.title_in(raw)
    rv = _request_vars(top)
    req_ok = lambda s: bool(re.search(r'\$_(GET|POST|REQUEST)', s)) or any(re.search(r'\$' + re.escape(v) + r'\b', s) for v in rv)
    sw = switches(top, line_of, sf.path, req_ok)
    F.branches = sw + ifs(top, line_of, sf.path, req_ok, 0, [b.span for b in sw])
    # entry point?
    e_ = ext(sf.path)
    has_top = bool(re.search(r'\becho\b|\bprint\b|\$_(GET|POST|REQUEST)|\binclude|\brequire|->\s*display|header\s*\(', top)) or \
        bool(re.search(r'<(html|body|form|table|div)\b', raw, re.I))
    in_lib = bool(re.search(r'(^|/)(includes?|lib|libs|classes|class|vendor|config|inc)/', sf.path, re.I))
    if e_ in ('.php', '.html', '.htm', '.phtml', '.php5') and has_top and not (in_lib and not re.search(r'<(html|form)\b', raw, re.I)):
        F.is_entry = True
        json_out = any(o[0] == 'json' for o in F.outputs)
        html_out = any(o[0] == 'html' for o in F.outputs)
        F.entry_kind = 'endpoint' if (json_out and not html_out) or re.search(r'ajax|api|json|rpc', sf.path, re.I) and not F.forms else 'page'
    return F


def _add_function(project, F, sf, cls, parent, name, params, vis, body, base, line_of, start, end, props, cfg, raw):
    key = f'{cls}::{name}' if cls else name
    types = _types(body, props)
    fn = Function(key=key, name=name, cls=cls, file=sf.path, line=line_of(start), end_line=line_of(end), body=body,
                  params=short(params, 160), visibility=vis)
    fn.calls = _calls(body, cls, parent, types, sf.path, line_of, base)
    fn.calls += C.pattern_calls(body, cfg['middle_layer_patterns'], 'middle_layer', sf.path, lambda o: line_of(base + o))
    fn.sql = C.sql_in(body, sf.path, lambda o: line_of(base + o), key) + C.procs_by_api(body, sf.path, lambda o: line_of(base + o), key)
    fn.messages = C.messages_in(body, lambda o: line_of(base + o))
    fn.params_read = _params(body, line_of, base)
    rv = _request_vars(body)
    req_ok = lambda s: bool(re.search(r'\$_(GET|POST|REQUEST)', s)) or any(re.search(r'\$' + re.escape(v) + r'\b', s) for v in rv)
    sw = switches(body, line_of, sf.path, req_ok, base)
    fn.branches = sw + ifs(body, line_of, sf.path, req_ok, base, [b.span for b in sw])
    fn.links = C.links_in(body, lambda o: line_of(base + o))
    fn.connections = C.connections_in(body, cfg['connection_patterns'])
    fn.outputs = _outputs(body, '', lambda o: line_of(base + o))
    if key in project.functions:
        key = f'{key}@{sf.path}'
        fn.key = key
    project.functions[key] = fn
    F.functions.append(key)
