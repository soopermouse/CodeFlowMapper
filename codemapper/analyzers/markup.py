"""HTML and server templates (Smarty .tpl, Twig, JSP, Razor .cshtml, ERB-like): forms, fields, dropdowns with options,
links / form actions / AJAX URLs in inline scripts, template includes, titles, user-visible messages."""
from __future__ import annotations
import re
from ..textutil import Text, short, uniq
from . import common as C

INC_RX = [
    r'\{%\s*(?:include|extends|import|embed)\s+[\'"]([^\'"]+)[\'"]', r'\{include\s+file\s*=\s*[\'"]?([^\'"\s}]+)', r'\{extends\s+file\s*=\s*[\'"]?([^\'"\s}]+)',
    r'<jsp:include\s+page\s*=\s*"([^"]+)"', r'<%@\s*include\s+file\s*=\s*"([^"]+)"', r'@Html\.(?:Partial|RenderPartial)(?:Async)?\(\s*"([^"]+)"',
    r'<partial\s+name\s*=\s*"([^"]+)"', r'th:(?:replace|insert|include)\s*=\s*"~?\{?([^:"}]+)', r'\{\{>\s*([\w/.-]+)',
]


def analyze(sf, project, cfg):
    raw = sf.text.replace('\r\n', '\n')
    T = Text(raw, slash_comments=False)
    F = C.FileFacts(path=sf.path, language=sf.language)
    F.includes = uniq([m.group(1) for rx in INC_RX for m in re.finditer(rx, raw)])
    F.forms = C.forms_in(raw, sf.path, T.line)
    F.links = C.links_in(raw, T.line)
    F.title = C.title_in(raw)
    # inline scripts: messages and AJAX targets
    scripts = ' '.join(re.findall(r'<script\b[^>]*>(.*?)</script>', raw, re.S | re.I))
    vis = re.sub(r'<script\b.*?</script>|<style\b.*?</style>', ' ', raw, flags=re.S | re.I)
    vis_text = [t.strip() for t in re.split(r'<[^>]+>', vis) if t.strip()]
    msgs = [(short(t, 200), 0) for t in vis_text if C.MSG_KEY.search(t) and 6 <= len(t) <= 220 and not re.search(r'[{}$<>]', t)]
    F.messages = uniq(msgs + C.messages_in(scripts, T.line))
    F.roles = C.roles_in(raw, cfg['auth_patterns'])
    if sf.language == 'template' and sf.path.lower().endswith(('.jsp', '.aspx')) and (F.forms or re.search(r'<%[^@]', raw)):
        F.is_entry = True
        F.entry_kind = 'page'
    elif sf.language == 'html' and F.forms and not re.search(r'(^|/)(templates?|views?|partials?|components?)/', sf.path, re.I):
        F.is_entry = True
        F.entry_kind = 'page'
    return F
