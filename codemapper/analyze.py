"""Run the language analyzers over the project files and register the entry points."""
from __future__ import annotations
import re
from .model import EntryPoint
from .analyzers import php, java, csharp, js, markup
from .textutil import Text

ANALYZERS = {'php': php.analyze, 'java': java.analyze, 'csharp': csharp.analyze, 'js': js.analyze,
             'html': markup.analyze, 'template': markup.analyze}


def analyze_project(project, cfg, progress=None):
    files = list(project.files.values())
    # configuration files first (servlet mappings)
    for sf in files:
        if sf.language == 'xml' and '<servlet-mapping>' in sf.text:
            java.web_xml(sf, project)
    order = {'xml': 0, 'java': 1, 'csharp': 1, 'php': 2, 'js': 3, 'template': 4, 'html': 4}
    files.sort(key=lambda s: (order.get(s.language, 9), s.path))
    for i, sf in enumerate(files):
        fn = ANALYZERS.get(sf.language)
        if not fn:
            continue
        if progress and i % 25 == 0:
            progress(f'Analysing {i + 1}/{len(files)}: {sf.path}')
        try:
            facts = fn(sf, project, cfg)
        except RecursionError:
            project.note(f'Analysis stopped on {sf.path}: nesting too deep.')
            continue
        except Exception as e:     # one bad file never stops the run; it is listed in the working report
            project.note(f'Analysis error on {sf.path}: {type(e).__name__}: {e}')
            continue
        project.facts[sf.path] = facts
        if facts.is_entry:
            body = facts.top_code or sf.text
            project.entries.append(EntryPoint(key=sf.path, file=sf.path, kind=facts.entry_kind or 'page', name=sf.path,
                                              route='/' + sf.path, handler='', body=body, line=1))
    project.note(f'Analysed {len(project.facts)} files: {len(project.functions)} functions, {len(project.entries)} entry points.')
