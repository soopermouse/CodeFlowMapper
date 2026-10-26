"""Configuration: defaults, loading from YAML / JSON, and merging with command-line or UI values."""
from __future__ import annotations
import copy, json, os

DEFAULTS = {
    'project': 'Legacy application',
    'author': '',
    'organisation': '',
    'output': 'archive',
    # which files are analysed
    'include_globs': ['**/*'],
    'exclude_globs': ['**/vendor/**', '**/node_modules/**', '**/.git/**', '**/bin/**', '**/obj/**', '**/target/**',
                      '**/build/**', '**/dist/**', '**/*.min.js', '**/test/**', '**/tests/**'],
    'max_file_kb': 2048,
    # how deep the call chain from an entry point is followed
    'call_depth': 4,
    # an endpoint whose code is one switch on a request parameter (ajax.php?action=...) gives one flow per case
    'split_switch_flows': True,
    # extra tool capabilities, checked before the built-in ones: [{name: 'Quotes', match: 'getQuote|QuotesPort'}]
    'tool_rules': [],
    # tooling: a function used by at least this many flows is a tool; fewer flows makes it a dependency
    'tool_min_flows': 3,
    # a tool used by at least this share of the flows is a platform tool
    'platform_share': 0.9,
    # module / submodule from the path: list of {match: regex on the path, module: name, submodule: name or group ref}
    # when empty, module = first meaningful folder, submodule = second meaningful folder
    'modules': [],
    # folder names skipped when deriving modules from the path
    'path_noise': ['www', 's', 'src', 'main', 'java', 'app', 'apps', 'web', 'webapp', 'public', 'htdocs', 'code', 'actions',
                   'controllers', 'Controllers', 'pages', 'Pages', 'views', 'Views', 'com', 'org', 'net', 'routes', 'api', 'lib'],
    # functionalities: optional explicit list {name, module, submodule, match (regex on the entry path or route)}
    'functionalities': [],
    # extra patterns: middle layer / RPC calls, authorisation checks, database connection names
    'middle_layer_patterns': [
        r'\b(?:DBwrapper::requestML2?|KML::request|RPC::request|callKmlPlugin|getFromBankingRT|xmlrpc_\w+|SoapClient|->__soapCall)\b',
        r'\b(?:restTemplate\.\w+|WebClient\b|HttpClient\.\w+Async|HttpClient\b|axios\.\w+|fetch)\s*\(',
    ],
    'auth_patterns': [
        r'->authorize\s*\(\s*([^)]*)\)', r'hasRole\s*\(\s*([^)]*)\)', r'@PreAuthorize\(\s*"([^"]*)"', r'@Secured\(\s*\{?([^)}]*)',
        r'@RolesAllowed\(\s*\{?([^)}]*)', r'\[Authorize\(([^)]*)\)\]', r'\bisInRole\s*\(\s*([^)]*)\)', r'\brequireRole\s*\(\s*([^)]*)\)',
        r'PAGE_ACCESSROLE[\'"]?\s*,\s*[\'"]([^\'"]+)',
    ],
    'connection_patterns': [
        r'Registry::(?:getInstance|c|cd|cr)\s*\(\s*[\'"]([^\'"]+)[\'"]', r'getConnection\s*\(\s*[\'"]([^\'"]+)[\'"]',
        r'ConnectionStrings\[\s*"([^"]+)"\s*\]', r'GetConnectionString\(\s*"([^"]+)"', r'@Qualifier\(\s*"([^"]+DataSource[^"]*)"',
        r'new\s+(?:PDO|mysqli)\s*\(\s*[\'"]?([^,\'")]+)',
    ],
    # OCR
    'ocr': {'lang': 'eng', 'psm': 6, 'upscale_below': 1600, 'tile_above': 3000, 'tile_overlap': 0.06},
    # SonarQube: path prefix to strip from component keys (project key) - detected automatically when empty
    'sonar_project_key': '',
    # wording: words that never appear in the archive (the working report keeps everything)
    'archive_banned_words': [],
}


def load(path: str | None = None, overrides: dict | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            if path.endswith(('.yml', '.yaml')):
                import yaml
                data = yaml.safe_load(fh) or {}
            else:
                data = json.load(fh)
        _merge(cfg, data)
    if overrides:
        _merge(cfg, {k: v for k, v in overrides.items() if v not in (None, '')})
    return cfg


def _merge(base: dict, extra: dict):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v


def save(cfg: dict, path: str):
    with open(path, 'w', encoding='utf-8') as fh:
        if path.endswith(('.yml', '.yaml')):
            import yaml
            yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True)
        else:
            json.dump(cfg, fh, indent=2)
