"""SonarQube material: issue exports, source line exports, measure trees and scanner logs.

Recognised (by content, any file name):
- api/issues/search JSON                -> issues attached to the files and to the flows that use them
- api/sources/lines or api/sources/show -> the source of a file (Sonar shows the code); the file path comes from the
                                           JSON name (path with '__' or '%2F' for '/') or from a 'component' field
- api/measures/component_tree JSON      -> file list, language, size and complexity measures
- api/components/tree JSON              -> file list
- sonar-scanner log                     -> files indexed with their language, sensors run, project key"""
from __future__ import annotations
import html, json, os, re
from urllib.parse import unquote
from ..model import SourceFile
from .code import detect_language

TAG = re.compile(r'<[^>]+>')


def _strip_key(component: str, cfg: dict) -> str:
    k = cfg.get('sonar_project_key') or ''
    if k and component.startswith(k + ':'):
        return component[len(k) + 1:]
    return component.split(':', 1)[1] if ':' in component else component


def ingest(paths, cfg: dict, project):
    files_meta = project.sonar.setdefault('files', {})
    issues = project.sonar.setdefault('issues', [])
    for rel, p in paths:
        try:
            raw = open(p, 'rb').read().decode('utf-8', 'replace')
        except OSError:
            continue
        data = None
        if raw.lstrip().startswith(('{', '[')):
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
        if data is None:
            _scanner_log(raw, project, rel)
            continue
        if isinstance(data, dict) and 'issues' in data:
            for c in data.get('components', []) or []:
                if c.get('qualifier') in ('FIL', 'UTS') and c.get('path'):
                    files_meta.setdefault(c['path'], {})
            for it in data['issues']:
                path = _strip_key(str(it.get('component', '')), cfg)
                issues.append({'path': path, 'line': it.get('line') or (it.get('textRange') or {}).get('startLine') or '',
                               'rule': it.get('rule', ''), 'severity': it.get('severity', ''), 'type': it.get('type', ''),
                               'message': it.get('message', ''), 'status': it.get('status', '')})
            project.note(f'SonarQube issues: {len(data["issues"])} read from {rel}.')
        elif isinstance(data, dict) and 'sources' in data:
            src = data['sources']
            if src and isinstance(src[0], dict):
                lines = [(int(s.get('line', i + 1)), html.unescape(TAG.sub('', s.get('code', '')))) for i, s in enumerate(src)]
            else:
                lines = [(int(a), html.unescape(TAG.sub('', b))) for a, b in src]
            path = data.get('component') or data.get('path') or ''
            if path:
                path = _strip_key(path, cfg)
            else:
                base = os.path.basename(rel)
                base = re.sub(r'\.json$', '', base, flags=re.I)
                path = unquote(base).replace('__', '/')
            mx = max((n for n, _ in lines), default=0)
            d = dict(lines)
            text = '\n'.join(d.get(n, '') for n in range(1, mx + 1))
            project.files[path] = SourceFile(path=path, text=text, language=detect_language(path, text), origin='sonar', size=len(text))
            project.note(f'SonarQube source: {path} ({mx} lines) from {rel}.')
        elif isinstance(data, dict) and 'components' in data:
            n = 0
            for c in data['components']:
                if c.get('qualifier') in ('FIL', 'UTS') or c.get('path', '').count('.'):
                    m = {x.get('metric'): x.get('value') for x in c.get('measures', []) or []}
                    files_meta[c.get('path') or _strip_key(c.get('key', ''), cfg)] = {'language': c.get('language', ''), **m}
                    n += 1
            project.note(f'SonarQube component tree: {n} files from {rel}.')
    # attach issues to files
    for it in issues:
        f = _find(project, it['path'])
        if f:
            f.issues.append(it)


def _find(project, path):
    if path in project.files:
        return project.files[path]
    for k, f in project.files.items():
        if k.endswith('/' + path) or path.endswith('/' + k):
            return f
    return None


def _scanner_log(raw: str, project, rel: str):
    meta = project.sonar.setdefault('files', {})
    sensors = project.sonar.setdefault('sensors', [])
    n = 0
    for m in re.finditer(r"'([^']+)'\s+indexed with(?:\s+language)?\s+'?(\w+)'?", raw):
        meta.setdefault(m.group(1), {})['language'] = m.group(2)
        n += 1
    for m in re.finditer(r'INFO:\s+Sensor\s+(.+?)\s*(?:\[\w+\])?\s*$', raw, re.M):
        if m.group(1) not in sensors and 'done' not in m.group(1).lower():
            sensors.append(m.group(1))
    m = re.search(r'Project key:\s*(\S+)', raw)
    if m:
        project.sonar['project_key'] = m.group(1)
    m = re.search(r'(\d+)\s+files indexed', raw)
    if m:
        project.sonar['files_indexed'] = int(m.group(1))
    project.note(f'SonarQube scanner log {rel}: {n} files listed, {len(sensors)} sensors.')
