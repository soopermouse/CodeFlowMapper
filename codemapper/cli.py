"""Command line: run a mapping, write a starter configuration, or start the web interface."""
from __future__ import annotations
import argparse, os, sys
from . import __version__, config


def _progress(msg):
    print(msg, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='codemapper', description='Map a codebase into an as-is archive of flows, cover sheets, trackers and tooling.')
    ap.add_argument('--version', action='version', version=f'codemapper {__version__}')
    sub = ap.add_subparsers(dest='cmd', required=True)

    r = sub.add_parser('run', help='map sources and write the archive')
    r.add_argument('sources', nargs='+', help='folders, zip / tar files (code, photos, SonarQube exports) or git URLs')
    r.add_argument('-o', '--out', default=None, help='output folder (default: ./archive)')
    r.add_argument('-c', '--config', default=None, help='configuration file (.yml or .json)')
    r.add_argument('--project', default=None, help='application name shown on the documents')
    r.add_argument('--author', default=None, help='author name written on every document')
    r.add_argument('--tool-min-flows', type=int, default=None, help='flows needed for a function to count as a tool (default 3)')
    r.add_argument('--call-depth', type=int, default=None, help='call levels followed from each entry point (default 4)')
    r.add_argument('--no-split-switch', action='store_true', help='do not split endpoint switch cases into separate flows')
    r.add_argument('-q', '--quiet', action='store_true')

    i = sub.add_parser('init-config', help='write a starter configuration file')
    i.add_argument('path', nargs='?', default='codemapper.yml')

    s = sub.add_parser('serve', help='start the web interface')
    s.add_argument('--host', default=os.environ.get('CODEMAPPER_HOST', '127.0.0.1'))
    s.add_argument('--port', type=int, default=int(os.environ.get('CODEMAPPER_PORT', '8080')))
    s.add_argument('--data', default=os.environ.get('CODEMAPPER_DATA', 'codemapper_data'), help='folder for uploads and results')

    a = ap.parse_args(argv)
    if a.cmd == 'init-config':
        if os.path.exists(a.path):
            sys.exit(f'{a.path} already exists')
        config.save(config.DEFAULTS, a.path)
        print(f'wrote {a.path}')
        return
    if a.cmd == 'serve':
        from .web.app import create_app
        app = create_app(a.data)
        print(f'Code Flow Mapper on http://{a.host}:{a.port}')
        try:
            from waitress import serve
            serve(app, host=a.host, port=a.port, threads=8)
        except ImportError:
            app.run(host=a.host, port=a.port, threaded=True)
        return
    from . import pipeline
    ov = {'project': a.project, 'author': a.author, 'tool_min_flows': a.tool_min_flows, 'call_depth': a.call_depth}
    if a.no_split_switch:
        ov['split_switch_flows'] = False
    cfg = config.load(a.config, ov)
    res = pipeline.run(a.sources, cfg, a.out, None if a.quiet else _progress)
    p = res['project']
    print(f"\n{len(p.flows)} flows, {len({f.functionality for f in p.flows})} functionalities, {len({f.module for f in p.flows})} modules, {res['pdfs']} PDFs")
    print(f"archive:        {res['archive_zip']}")
    print(f"working report: {res['working_zip']}")
