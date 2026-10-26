"""Local web interface: upload code / photos / SonarQube exports (or give a folder path or git URL), set the options,
follow the run, browse the flows and their PDFs, download the archive and the working report.

Environment:
  CODEMAPPER_DATA          folder for jobs (uploads and results)
  CODEMAPPER_USER / CODEMAPPER_PASSWORD   basic authentication for every page (set both on a shared server)
  CODEMAPPER_ALLOW_PATHS   1 = the form accepts folder paths on the server (default 1 on 127.0.0.1, set 0 on a shared server)
  CODEMAPPER_MAX_UPLOAD_MB upload limit per run (default 2048)"""
from __future__ import annotations
import json, os, re, shutil, threading, time, traceback, uuid
from functools import wraps
from flask import Flask, request, redirect, url_for, render_template, send_file, abort, jsonify, Response
from werkzeug.utils import secure_filename
from .. import config as CONFIG, __version__

JOBS = {}
LOCK = threading.Lock()


def create_app(data_dir='codemapper_data'):
    app = Flask(__name__, template_folder='templates', static_folder='static')
    data_dir = os.path.abspath(data_dir)
    os.makedirs(os.path.join(data_dir, 'jobs'), exist_ok=True)
    app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('CODEMAPPER_MAX_UPLOAD_MB', '2048')) * 1024 * 1024
    user, pwd = os.environ.get('CODEMAPPER_USER'), os.environ.get('CODEMAPPER_PASSWORD')
    allow_paths = os.environ.get('CODEMAPPER_ALLOW_PATHS', '1') == '1'

    def auth(fn):
        @wraps(fn)
        def inner(*a, **k):
            if user and pwd:
                au = request.authorization
                if not au or au.username != user or au.password != pwd:
                    return Response('Authentication required', 401, {'WWW-Authenticate': 'Basic realm="Code Flow Mapper"'})
            return fn(*a, **k)
        return inner

    def job_dir(jid):
        if not re.fullmatch(r'[0-9a-f]{12}', jid or ''):
            abort(404)
        d = os.path.join(data_dir, 'jobs', jid)
        if not os.path.isdir(d):
            abort(404)
        return d

    def load_job(jid):
        d = job_dir(jid)
        with LOCK:
            if jid in JOBS:
                return JOBS[jid]
        try:
            with open(os.path.join(d, 'job.json'), encoding='utf-8') as fh:
                return json.load(fh)
        except OSError:
            abort(404)

    def save_job(job):
        with LOCK:
            JOBS[job['id']] = job
            with open(os.path.join(data_dir, 'jobs', job['id'], 'job.json'), 'w', encoding='utf-8') as fh:
                json.dump(job, fh, indent=1)

    @app.context_processor
    def ctx():
        return {'version': __version__, 'allow_paths': allow_paths}

    @app.get('/')
    @auth
    def index():
        jobs = []
        for jid in sorted(os.listdir(os.path.join(data_dir, 'jobs')), reverse=True):
            p = os.path.join(data_dir, 'jobs', jid, 'job.json')
            if os.path.exists(p):
                try:
                    jobs.append(load_job(jid))
                except Exception:
                    pass
        jobs.sort(key=lambda j: j.get('created', 0), reverse=True)
        return render_template('index.html', jobs=jobs[:30], defaults=CONFIG.DEFAULTS)

    @app.post('/run')
    @auth
    def run():
        jid = uuid.uuid4().hex[:12]
        d = os.path.join(data_dir, 'jobs', jid)
        up = os.path.join(d, 'uploads')
        os.makedirs(up, exist_ok=True)
        sources = []
        for f in request.files.getlist('files'):
            if not f or not f.filename:
                continue
            rel = f.filename.replace('\\', '/')
            parts = [secure_filename(x) for x in rel.split('/') if x not in ('', '.', '..')]
            parts = [x for x in parts if x]
            if not parts:
                continue
            dest = os.path.join(up, *parts)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f.save(dest)
        if os.listdir(up):
            sources.append(up)
        for line in (request.form.get('paths') or '').splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r'^(https?://|git@)', line):
                sources.append(line)
            elif allow_paths and os.path.exists(line):
                sources.append(line)
        if not sources:
            shutil.rmtree(d, ignore_errors=True)
            return render_template('index.html', jobs=[], defaults=CONFIG.DEFAULTS, error='Add files, a folder path or a git URL.'), 400
        ov = {'project': request.form.get('project') or 'Application', 'author': request.form.get('author') or '',
              'tool_min_flows': int(request.form.get('tool_min_flows') or 3), 'call_depth': int(request.form.get('call_depth') or 4),
              'split_switch_flows': request.form.get('split_switch') == 'on'}
        cfg_text = request.form.get('config_yaml') or ''
        extra = {}
        if cfg_text.strip():
            import yaml
            try:
                extra = yaml.safe_load(cfg_text) or {}
            except yaml.YAMLError as e:
                shutil.rmtree(d, ignore_errors=True)
                return render_template('index.html', jobs=[], defaults=CONFIG.DEFAULTS, error=f'Settings are not valid YAML: {e}'), 400
        cfg = CONFIG.load(None, {**extra, **ov})
        job = {'id': jid, 'created': time.time(), 'project': cfg['project'], 'author': cfg['author'], 'status': 'queued',
               'log': [], 'sources': [os.path.basename(s) if s == up else s for s in sources], 'result': {}}
        save_job(job)
        threading.Thread(target=_work, args=(job, sources, cfg, os.path.join(d, 'out'), save_job), daemon=True).start()
        return redirect(url_for('job', jid=jid))

    @app.get('/job/<jid>')
    @auth
    def job(jid):
        return render_template('job.html', job=load_job(jid))

    @app.get('/job/<jid>/status')
    @auth
    def status(jid):
        j = load_job(jid)
        return jsonify({'status': j['status'], 'log': j['log'][-40:], 'result': j.get('result', {})})

    @app.get('/job/<jid>/flows')
    @auth
    def flows(jid):
        j = load_job(jid)
        return render_template('flows.html', job=j, flows=j.get('result', {}).get('flows', []))

    @app.get('/job/<jid>/file/<path:rel>')
    @auth
    def file(jid, rel):
        d = os.path.realpath(os.path.join(job_dir(jid), 'out'))
        p = os.path.realpath(os.path.join(d, rel))
        if not p.startswith(d + os.sep) or not os.path.isfile(p):
            abort(404)
        return send_file(p, as_attachment=request.args.get('dl') == '1')

    @app.post('/job/<jid>/delete')
    @auth
    def delete(jid):
        d = job_dir(jid)
        with LOCK:
            JOBS.pop(jid, None)
        shutil.rmtree(d, ignore_errors=True)
        return redirect(url_for('index'))

    @app.get('/health')
    def health():
        return {'ok': True, 'version': __version__}

    return app


def _work(job, sources, cfg, out, save):
    from .. import pipeline

    def progress(msg):
        job['log'].append(time.strftime('%H:%M:%S ') + msg)
        if len(job['log']) % 5 == 0:
            save(job)

    job['status'] = 'running'
    save(job)
    try:
        res = pipeline.run(sources, cfg, out, progress)
        p = res['project']
        rel = lambda x: os.path.relpath(x, out).replace('\\', '/')
        fl = []
        for f in p.flows:
            base = None
            for r_, _, names in os.walk(res['archive_dir']):
                if os.path.basename(r_) == f.id:
                    base = rel(r_)
                    break
            fl.append({'id': f.id, 'name': f.name, 'functionality': f.functionality, 'module': f.module, 'kind': f.entry.kind,
                       'entry': f.entry.route if f.entry.kind != 'page' else f.entry.file, 'up': f.upstream, 'down': f.downstream,
                       'tables': f.tables[:8], 'dir': base})
        job['result'] = {'flows': fl, 'archive_zip': rel(res['archive_zip']), 'working_zip': rel(res['working_zip']),
                         'cover': rel(os.path.join(res['archive_dir'], '00_Archive_cover_sheet.pdf')),
                         'counts': {'files': len(p.files), 'flows': len(p.flows), 'functionalities': len({f.functionality for f in p.flows}),
                                    'modules': len({f.module for f in p.flows}), 'pdfs': res['pdfs'],
                                    'tools': sum(t.kind != 'Dependency' for t in p.tools), 'dependencies': sum(t.kind == 'Dependency' for t in p.tools)}}
        job['log'] += [time.strftime('%H:%M:%S ') + l for l in p.log[-6:]]
        job['status'] = 'done'
    except Exception as e:
        job['log'].append(f'Stopped: {type(e).__name__}: {e}')
        job['log'].append(traceback.format_exc()[-1500:])
        job['status'] = 'failed'
    save(job)
