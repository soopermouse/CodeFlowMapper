"""Write the archive folder (covers, flows, workbooks), the separate working report, and a zip of each."""
from __future__ import annotations
import os, re, shutil, zipfile
from collections import defaultdict, OrderedDict
from . import functional, architecture, covers, sheets
from .sheets import _book, sheet


def safe(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', '-', s or '').strip()
    s = re.sub(r'\s*>\s*|\s+', '_', s)
    return s[:80] or 'unnamed'


def write_archive(project, cfg, out_dir, progress=None):
    name = safe(cfg.get('project') or 'Application')
    root = os.path.join(out_dir, f'{name}_archive')
    work = os.path.join(out_dir, f'{name}_working_report')
    for d in (root, work):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    mods = OrderedDict()
    for f in project.flows:
        mods.setdefault(f.module, OrderedDict()).setdefault(f.functionality, []).append(f)
    total = len(project.flows)
    done = 0
    pdfs = 0
    for mi, (mod, funcs) in enumerate(mods.items(), 1):
        mdir = os.path.join(root, f'{mi:02d}_{safe(mod)}')
        os.makedirs(mdir, exist_ok=True)
        allf = [f for fl in funcs.values() for f in fl]
        covers.module_cover(project, mod, allf, os.path.join(mdir, '00_Module_cover_sheet.pdf'), cfg)
        pdfs += 1
        for fi, (func, fl) in enumerate(funcs.items(), 1):
            sub = func.split(' > ', 1)[1] if ' > ' in func else func
            fdir = os.path.join(mdir, f'{fi:02d}_{safe(sub)}')
            os.makedirs(fdir, exist_ok=True)
            covers.functionality_cover(project, func, fl, os.path.join(fdir, '00_Cover_sheet.pdf'), cfg)
            pdfs += 1
            for f in fl:
                done += 1
                if progress:
                    progress(f'Writing {f.id} ({done}/{total})')
                d = os.path.join(fdir, f.id)
                os.makedirs(d, exist_ok=True)
                covers.flow_cover(project, f, os.path.join(d, f'{f.id}_cover_sheet.pdf'), cfg)
                functional.build(project, f, os.path.join(d, f'{f.id}_functional_flow.pdf'), cfg)
                architecture.build(project, f, os.path.join(d, f'{f.id}_architectural_flow.pdf'), cfg)
                pdfs += 3
    layout = ['00_Archive_cover_sheet.pdf: this summary.',
              'Flow_Tracker.xlsx: one row per flow (number, name, functionality, module, submodule, upstream and downstream flows and '
              'functionalities, data sources, nature, tools, dependencies), plus flow details, fields and dropdowns, decisions, calls, '
              'flow dependencies and functionalities.',
              'Database_Tables_And_Calls.xlsx: tables with the flows that read or write them, stored procedures, every SQL statement per flow, '
              'middle-layer calls and connections.',
              'Tooling_And_Dependencies.xlsx: tools (functions several flows use), dependencies (functions, includes and classes used by one or two flows), '
              'shared files, tools by module and by functionality.',
              'One numbered folder per module, opening with 00_Module_cover_sheet.pdf; inside, one numbered folder per functionality with its '
              '00_Cover_sheet.pdf and one folder per flow holding the flow cover sheet, the functional flow and the architectural flow.']
    covers.archive_cover(project, os.path.join(root, '00_Archive_cover_sheet.pdf'), cfg, layout)
    pdfs += 1
    sheets.flow_tracker(project, os.path.join(root, 'Flow_Tracker.xlsx'), cfg)
    sheets.database(project, os.path.join(root, 'Database_Tables_And_Calls.xlsx'), cfg)
    sheets.tooling(project, os.path.join(root, 'Tooling_And_Dependencies.xlsx'), cfg)
    working_report(project, work, cfg)
    zips = []
    for d in (root, work):
        z = d + '.zip'
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
            for r, _, names in os.walk(d):
                for n in sorted(names):
                    p = os.path.join(r, n)
                    zf.write(p, os.path.relpath(p, os.path.dirname(d)))
        zips.append(z)
    return {'archive_dir': root, 'working_dir': work, 'archive_zip': zips[0], 'working_zip': zips[1], 'pdfs': pdfs}


def working_report(project, work, cfg):
    """Everything that stays out of the archive: run log, names not found, analysis notes, OCR-rebuilt files."""
    wb = _book(cfg.get('author'), 'Working report')
    sheet(wb, 'Run log', ['Note'], [[l] for l in project.log], [140])
    ur = []
    for f in project.flows:
        for u in sorted(set(f.unresolved)):
            ur.append([f.id, f.name, u])
    sheet(wb, 'Not found in the project', ['Flow number', 'Flow name', 'Name'], ur, [11, 40, 80])
    meta = project.sonar.get('files', {})
    have = set(project.files)
    miss = [[p, m.get('language', ''), m.get('ncloc', '')] for p, m in sorted(meta.items()) if not any(h.endswith(p) or p.endswith(h) for h in have)]
    if meta:
        sheet(wb, 'SonarQube files without source', ['File', 'Language', 'Lines of code'], miss, [70, 12, 12])
    ocr = [[sf.path, sf.language, len(sf.text.splitlines()), '\n'.join(sf.images)] for sf in project.files.values() if sf.origin == 'ocr']
    if ocr:
        sheet(wb, 'Files rebuilt from photos', ['File', 'Language', 'Lines', 'Photos'], ocr, [60, 10, 8, 60])
        src = os.path.join(work, 'rebuilt_sources')
        for sf in project.files.values():
            if sf.origin in ('ocr', 'sonar'):
                p = os.path.join(src, sf.path.replace('..', '_'))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, 'w', encoding='utf-8') as fh:
                    fh.write(sf.text)
    ent = [[e.key, e.kind, e.method, e.route, e.handler] for e in project.entries]
    sheet(wb, 'Entry points found', ['Entry', 'Kind', 'Method', 'Route', 'Handler'], ent, [60, 14, 9, 40, 40])
    wb.save(os.path.join(work, 'Working_Report.xlsx'))
