"""End-to-end run: sources -> project -> analysis -> flows -> tooling -> archive."""
from __future__ import annotations
import os, tempfile, time
from .model import Project
from .ingest import code as CODE, ocr as OCR, sonar as SONAR
from .analyze import analyze_project
from .flows import build_flows
from .tooling import classify


def load_sources(sources, cfg, project, workdir, progress=None):
    images, sonar = [], []
    todo = [s for s in sources if s]
    n = 0
    while todo:
        src = todo.pop(0)
        n += 1
        if progress:
            progress(f'Reading {os.path.basename(str(src).rstrip("/")) or src}')
        folder = CODE.unpack(src, os.path.join(workdir, f's{n}'))
        # archives inside a folder (uploads, photo batches) are read as further sources
        for root, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__MACOSX')]
            for nm in names:
                if nm.lower().endswith(('.zip', '.tar', '.tgz', '.tar.gz')) and src != os.path.join(root, nm):
                    todo.append(os.path.join(root, nm))
        for kind, rel, item in CODE.collect(folder, cfg):
            if kind == 'code':
                project.files[item.path] = item
            elif kind == 'image':
                images.append((rel, item))
            else:
                sonar.append((rel, item))
    if images:
        OCR.ingest_images(images, cfg, project, progress)
    if sonar:
        SONAR.ingest(sonar, cfg, project)
    project.note(f'Sources: {len(project.files)} files ({sum(f.origin == "ocr" for f in project.files.values())} from photos, '
                 f'{sum(f.origin == "sonar" for f in project.files.values())} from SonarQube).')


def run(sources, cfg, out_dir=None, progress=None, render=True):
    t0 = time.time()
    project = Project(name=cfg.get('project') or 'Application')
    out_dir = out_dir or cfg.get('output') or 'archive'
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        load_sources(sources, cfg, project, work, progress)
        if progress:
            progress('Analysing the code')
        analyze_project(project, cfg, progress)
        if progress:
            progress('Building the flows')
        build_flows(project, cfg, progress)
        classify(project, cfg)
        result = {'project': project, 'out_dir': out_dir}
        if render:
            from .render.archive import write_archive
            result.update(write_archive(project, cfg, out_dir, progress))
    project.note(f'Run time {time.time() - t0:.1f} s.')
    return result
