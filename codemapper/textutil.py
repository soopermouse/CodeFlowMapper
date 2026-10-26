"""Source text helpers shared by the analyzers: comment blanking, string literals, brace matching, line numbers."""
from __future__ import annotations
import bisect, re


class Text:
    """Source text with comments blanked out (same length, so offsets and line numbers stay valid)."""

    def __init__(self, raw: str, hash_comments: bool = False, slash_comments: bool = True):
        self.raw = raw.replace('\r\n', '\n').replace('\r', '\n')
        self.code = blank_comments(self.raw, hash_comments, slash_comments)
        self._nl = [i for i, c in enumerate(self.raw) if c == '\n']

    def line(self, offset: int) -> int:
        return bisect.bisect_left(self._nl, offset) + 1

    def block(self, open_at: int) -> int:
        """offset of the brace closing the one at open_at (or end of text)."""
        return match_brace(self.code, open_at)


def blank_comments(src: str, hash_comments: bool = False, slash_comments: bool = True) -> str:
    """Replace // and /* */ comments (and # when asked) by spaces, keep strings and newlines."""
    out = list(src)
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in '"\'`':
            j = skip_string(src, i)
            i = j
            continue
        if (slash_comments and c == '/' and i + 1 < n and src[i + 1] == '/' and (i == 0 or src[i - 1] != ':')) or \
                (hash_comments and c == '#' and not src.startswith('#[', i)):
            j = src.find('\n', i)
            j = n if j < 0 else j
            # PHP: a closing ?> ends a // comment
            k = src.find('?>', i, j)
            if k >= 0:
                j = k
            for k2 in range(i, j):
                out[k2] = ' '
            i = j
            continue
        if slash_comments and c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            j = n if j < 0 else j + 2
            for k2 in range(i, j):
                if out[k2] != '\n':
                    out[k2] = ' '
            i = j
            continue
        if c == '<' and src.startswith('<!--', i):
            j = src.find('-->', i)
            j = n if j < 0 else j + 3
            for k2 in range(i, j):
                if out[k2] != '\n':
                    out[k2] = ' '
            i = j
            continue
        i += 1
    return ''.join(out)


def skip_string(src: str, i: int) -> int:
    q = src[i]
    j = i + 1
    n = len(src)
    while j < n:
        if src[j] == '\\':
            j += 2
            continue
        if src[j] == q:
            return j + 1
        if src[j] == '\n' and q != '`' and q != '"' and q != "'":
            return j
        j += 1
    return n


def match_brace(code: str, open_at: int, open_ch: str = '{', close_ch: str = '}') -> int:
    depth = 0
    i, n = open_at, len(code)
    while i < n:
        c = code[i]
        if c in '"\'`':
            i = skip_string(code, i)
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n - 1


def match_paren(code: str, open_at: int) -> int:
    return match_brace(code, open_at, '(', ')')


STR_RX = re.compile(r'"((?:[^"\\\n]|\\.)*)"|\'((?:[^\'\\\n]|\\.)*)\'|`((?:[^`\\]|\\.)*)`', re.S)


def strings(code: str):
    """yield (offset, value) of string literals."""
    for m in STR_RX.finditer(code):
        v = m.group(1) if m.group(1) is not None else (m.group(2) if m.group(2) is not None else m.group(3))
        yield m.start(), v


def short(s: str, n: int = 160) -> str:
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s if len(s) <= n else s[:n - 1] + '…'


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        k = x if isinstance(x, (str, int, tuple)) else repr(x)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def ext(path: str) -> str:
    p = path.lower()
    if p.endswith('.class.php'):
        return '.php'
    i = p.rfind('.')
    return p[i:] if i >= 0 else ''
