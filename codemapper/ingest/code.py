"""Load a codebase from a folder, a zip / tar archive or a git URL into SourceFile objects."""
from __future__ import annotations
import fnmatch, io, os, re, shutil, subprocess, tarfile, tempfile, zipfile
from ..model import SourceFile
from ..textutil import ext

LANG_BY_EXT = {
    '.php': 'php', '.inc': 'php', '.phtml': 'php', '.php5': 'php', '.module': 'php',
    '.java': 'java', '.jsp': 'template', '.jspf': 'template',
    '.cs': 'csharp', '.cshtml': 'template', '.razor': 'template', '.aspx': 'template', '.ascx': 'template', '.master': 'template',
    '.js': 'js', '.mjs': 'js', '.cjs': 'js', '.jsx': 'js', '.ts': 'js', '.tsx': 'js', '.vue': 'js',
    '.html': 'html', '.htm': 'html', '.tpl': 'template', '.twig': 'template', '.hbs': 'template', '.ejs': 'template',
    '.mustache': 'template', '.ftl': 'template', '.vm': 'template',
    '.sql': 'sql', '.xml': 'xml', '.json': 'json', '.config': 'xml', '.properties': 'other', '.yml': 'other', '.yaml': 'other',
}
TEXT_EXT = set(LANG_BY_EXT)
IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp', '.gif'}


def detect_language(path: str, text: str) -> str:
    e = ext(path)
    lang = LANG_BY_EXT.get(e, 'other')
    if lang in ('html', 'template', 'other') and '<?php' in text[:200000]:
        return 'php'
    if e == '.xml' and '<web-app' in text[:5000]:
        return 'xml'
    return lang


def _wanted(rel: str, cfg: dict) -> bool:
    rel_l = rel.replace('\\', '/')
    for g in cfg.get('exclude_globs', []):
        if fnmatch.fnmatch(rel_l, g) or fnmatch.fnmatch('/' + rel_l, g):
            return False
    inc = cfg.get('include_globs') or ['**/*']
    return any(fnmatch.fnmatch(rel_l, g) or g == '**/*' for g in inc)


def _read(data: bytes) -> str:
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', 'replace')


def unpack(source: str, workdir: str) -> str:
    """Return a folder holding the sources: the folder itself, an extracted archive, or a git clone."""
    if os.path.isdir(source):
        return source
    if re.match(r'^(https?://|git@).+', source) or source.endswith('.git'):
        dest = os.path.join(workdir, 'repo')
        shutil.rmtree(dest, ignore_errors=True)
        subprocess.run(['git', 'clone', '--depth', '1', source, dest], check=True, capture_output=True)
        return dest
    dest = os.path.join(workdir, 'unpacked_' + re.sub(r'\W+', '_', os.path.basename(source)))
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(workdir, exist_ok=True)
    os.makedirs(dest, exist_ok=True)
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as z:
            for m in z.infolist():
                name = m.filename
                if name.startswith('/') or '..' in name.split('/'):
                    continue
                z.extract(m, dest)
    elif tarfile.is_tarfile(source):
        with tarfile.open(source) as t:
            try:
                t.extractall(dest, filter='data')
            except TypeError:          # Python < 3.12
                t.extractall(dest, members=[m for m in t.getmembers() if not (m.name.startswith('/') or '..' in m.name.split('/'))])
    else:
        shutil.copy(source, dest)
    # nested archives (a zip of zips, as photo batches often arrive)
    for root, _, names in os.walk(dest):
        for n in names:
            p = os.path.join(root, n)
            if n.lower().endswith('.zip') and zipfile.is_zipfile(p):
                sub = p[:-4]
                os.makedirs(sub, exist_ok=True)
                with zipfile.ZipFile(p) as z:
                    for m in z.infolist():
                        if not (m.filename.startswith('/') or '..' in m.filename.split('/')):
                            z.extract(m, sub)
                os.remove(p)
    return dest


def collect(folder: str, cfg: dict):
    """yield ('code', rel, SourceFile) | ('image', rel, abs_path) | ('sonar', rel, abs_path)."""
    max_b = int(cfg.get('max_file_kb', 2048)) * 1024
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__MACOSX')]
        for n in sorted(names):
            p = os.path.join(root, n)
            rel = os.path.relpath(p, folder).replace('\\', '/')
            if not _wanted(rel, cfg):
                continue
            e = ext(n)
            if e in IMAGE_EXT:
                yield 'image', rel, p
                continue
            if n.lower().endswith(('.zip', '.tar', '.tgz', '.tar.gz')):
                continue
            if e in ('.json', '.log', '.txt') and _looks_sonar(p):
                yield 'sonar', rel, p
                continue
            if e not in TEXT_EXT:
                continue
            try:
                size = os.path.getsize(p)
                if size > max_b:
                    continue
                with open(p, 'rb') as fh:
                    text = _read(fh.read())
            except OSError:
                continue
            yield 'code', rel, SourceFile(path=rel, text=text, language=detect_language(rel, text), size=size)


def _looks_sonar(p: str) -> bool:
    try:
        with open(p, 'rb') as fh:
            head = fh.read(20000).decode('utf-8', 'replace')
    except OSError:
        return False
    return bool(re.search(r'"issues"\s*:|"components"\s*:|"sources"\s*:|"measures"\s*:|SonarScanner|sonar-scanner|INFO: Sensor |'
                          r'INFO: Indexing files|INFO: Analysis report|"baseComponent"', head))
