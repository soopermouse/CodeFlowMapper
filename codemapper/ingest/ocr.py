"""Photos or screenshots of code (GitLab / IDE screens) -> reconstructed source files.

Each image is OCR'd with the tesseract binary (large photos in overlapping horizontal bands, small ones upscaled).
The file an image shows is taken from the path or breadcrumb in its header; images without a header continue the
previous file (images are taken in name order). When the screen shows line numbers, lines are placed by number, so
overlapping photos and photos taken out of order merge cleanly; otherwise overlapping lines are de-duplicated."""
from __future__ import annotations
import os, re, shutil, subprocess, tempfile
from collections import defaultdict
from ..model import SourceFile
from .code import detect_language, LANG_BY_EXT

QUOTES = {'‘': "'", '’': "'", '‚': "'", '“': '"', '”': '"', '„': '"', '—': '-', '–': '-', '«': '<<', '»': '>>', '¦': '|', ' ': ' '}
EXTS = '|'.join(sorted({e.lstrip('.') for e in LANG_BY_EXT} | {'class.php'}, key=len, reverse=True))
PATH_RX = re.compile(r'((?:[\w.\-]+\s?/\s?)+[\w.\-]+\.(?:' + EXTS + r'))\b')
NAME_RX = re.compile(r'^\s*([\w.\-]+\.(?:' + EXTS + r'))\s+\d+(?:[.,]\d+)?\s*(?:KiB|KB|MiB|B|bytes)\b', re.I)
LINENO_RX = re.compile(r'^\s*(\d{1,5})\s*[|:\]\)]?\s?(.*)$')


def available() -> bool:
    return shutil.which('tesseract') is not None


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def _prep(path: str, cfg: dict, tmp: str):
    from PIL import Image, ImageOps
    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert('L')
    im = ImageOps.autocontrast(im)
    w, h = im.size
    o = cfg.get('ocr', {})
    if w < int(o.get('upscale_below', 1600)):
        f = max(2, int(2400 / max(w, 1)))
        im = im.resize((w * f, h * f), Image.LANCZOS)
        w, h = im.size
    # dark screen themes: invert so text is dark on light
    if sum(im.resize((64, 64)).getdata()) / 4096 < 110:
        im = ImageOps.invert(im)
    tiles = []
    limit = int(o.get('tile_above', 3000))
    if h > limit:
        n = (h + limit - 1) // limit
        band = h // n
        ov = int(band * float(o.get('tile_overlap', 0.06)))
        for i in range(n):
            top, bot = max(0, i * band - ov), min(h, (i + 1) * band + ov)
            p = os.path.join(tmp, f't{i}.png')
            im.crop((0, top, w, bot)).save(p)
            tiles.append(p)
    else:
        p = os.path.join(tmp, 't0.png')
        im.save(p)
        tiles.append(p)
    return tiles


def ocr_image(path: str, cfg: dict) -> str:
    o = cfg.get('ocr', {})
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for t in _prep(path, cfg, tmp):
            r = subprocess.run(['tesseract', t, 'stdout', '--psm', str(o.get('psm', 6)), '-l', o.get('lang', 'eng'),
                                '-c', 'preserve_interword_spaces=1'], capture_output=True, text=True)
            parts.append(r.stdout)
    text = '\n'.join(parts)
    for k, v in QUOTES.items():
        text = text.replace(k, v)
    return text


def header_path(lines):
    """path of the file shown, from the screen header (first lines)."""
    for ln in lines[:14]:
        s = ln.strip()
        m = NAME_RX.match(s)
        if m:
            return m.group(1)
        # repository address bar: keep the path after blob/<branch>/ (or tree/<branch>/)
        m = re.search(r'(?:blob|tree)\W{0,3}[\w.\-]+\s?/\s?((?:[\w.\-]+\s?/\s?)*[\w.\-]+\.(?:' + EXTS + r'))\b', s)
        if m:
            return re.sub(r'\s*/\s*', '/', m.group(1))
        m = PATH_RX.search(s)
        if m and ('/' in m.group(1) or s == m.group(1)):
            p = re.sub(r'\s*/\s*', '/', m.group(1))
            # a branch name cut by the OCR in front of the path (master -> aster)
            p = re.sub(r'^(?:m?a?ster|main|develop|trunk)/(?=(?:www|lib|src|code|app|s|modules|templates)/)', '', p)
            return p
    return ''


def _numbered(lines):
    nums = []
    for ln in lines:
        m = LINENO_RX.match(ln)
        if m:
            nums.append((int(m.group(1)), m.group(2).rstrip()))
    if len(nums) < max(4, len([l for l in lines if l.strip()]) * 0.5):
        return None
    # keep the increasing run (line numbers on screen go up by one)
    ok = [(n, t) for i, (n, t) in enumerate(nums) if i == 0 or 0 < n - nums[i - 1][0] <= 3 or (i + 1 < len(nums) and 0 < nums[i + 1][0] - n <= 3)]
    return ok if len(ok) >= 3 else None


def _dedupe_append(acc: list, new: list):
    best = 0
    for k in range(min(len(acc), len(new), 60), 0, -1):
        if [a.strip() for a in acc[-k:]] == [b.strip() for b in new[:k]]:
            best = k
            break
    acc.extend(new[best:])


def ingest_images(images, cfg: dict, project, progress=None):
    """images: [(rel, abs_path)] -> adds SourceFile(origin='ocr') to project.files"""
    if not images:
        return
    if not available():
        project.note('OCR skipped: the tesseract program is not installed (images were not read).')
        return
    by_numbers = defaultdict(dict)       # path -> {line: text}
    by_text = defaultdict(list)          # path -> [lines]
    imgs_of = defaultdict(list)
    current = ''
    order = sorted(images, key=lambda x: natural_key(x[0]))
    for i, (rel, p) in enumerate(order):
        if progress:
            progress(f'OCR {i + 1}/{len(order)}: {rel}')
        try:
            text = ocr_image(p, cfg)
        except Exception as e:  # unreadable image
            project.note(f'OCR failed on {rel}: {e}')
            continue
        lines = text.split('\n')
        hp = header_path(lines)
        if hp:
            current = hp
        if not current:
            current = 'ocr/' + os.path.splitext(rel)[0].replace('/', '_') + '.txt'
        imgs_of[current].append(rel)
        num = _numbered(lines)
        if num:
            d = by_numbers[current]
            for n, t in num:
                if len(t.strip()) > len(d.get(n, '').strip()):
                    d[n] = t
        else:
            body = [l for l in lines if not (hp and hp in re.sub(r'\s*/\s*', '/', l))]
            _dedupe_append(by_text[current], body)
    for path in set(by_numbers) | set(by_text):
        if path in by_numbers and by_numbers[path]:
            d = by_numbers[path]
            text = '\n'.join(d.get(n, '') for n in range(1, max(d) + 1))
        else:
            text = '\n'.join(by_text[path])
        if path.endswith('.txt'):
            lang = 'php' if '<?php' in text or '$_' in text else ('java' if re.search(r'\bpublic\s+class\b|@\w+Mapping', text) else
                   ('csharp' if re.search(r'\busing\s+System\b|\bnamespace\s+\w+', text) else ('js' if re.search(r'\bfunction\b|=>|require\(', text) else 'other')))
        else:
            lang = detect_language(path, text)
        key = path if path not in project.files else path + ' (photos)'
        project.files[key] = SourceFile(path=key, text=text, language=lang, origin='ocr', size=len(text), images=imgs_of[path])
    project.note(f'OCR: {len(order)} images read into {len(set(by_numbers) | set(by_text))} files.')
