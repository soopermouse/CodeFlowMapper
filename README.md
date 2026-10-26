# Code Flow Mapper

Author: Simona Diana Thrussell PhD
Version: 1.0.0

Code Flow Mapper maps a legacy codebase into an as-is archive: one functional flow and one architectural flow per
flow, a cover sheet per flow, functionality and module, the flow tracker, the database tables and calls, and the
tooling (tools used by several flows, dependencies used by one or two).

It reads three kinds of source, separately or together:

- source code: a folder, a .zip / .tar archive, or a git URL (PHP, Java, C#, JavaScript; HTML, templates and SQL files
  are read for links and statements);
- photos or screenshots of the code (.png, .jpg, ...): the code is read with OCR, page by page, and the pages of the
  same file are joined by their line numbers;
- SonarQube exports: issue lists, source line exports, component and measure trees, scanner logs.

The analysis is static: the code is read, never executed.

---

## 1. Setup

### Requirements

- Python 3.10 or later
- Tesseract OCR 5, only to read photos or screenshots of code
- git, only to read a repository by its URL

### Install on Linux or macOS

```bash
unzip code-flow-mapper-1.0.0.zip
cd code-flow-mapper-1.0.0
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pip install .
```

Tesseract:

- Debian / Ubuntu: `sudo apt-get install tesseract-ocr git`
- RHEL / Rocky / Fedora: `sudo dnf install tesseract git`
- macOS (Homebrew): `brew install tesseract git`

### Install on Windows

```powershell
cd code-flow-mapper-1.0.0
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install .
```

Install Tesseract from the installer of the UB Mannheim build and add its folder (for example
`C:\Program Files\Tesseract-OCR`) to the PATH.

### Check the installation

```bash
codemapper --version
codemapper run tests/sample_app -o sample_out --project "Sample"
```

The second command maps the small sample application in `tests/sample_app` (PHP, Java, C# and Node pages) and writes
`sample_out/Sample_archive.zip`.

---

## 2. How to use it

### From the command line

```bash
codemapper run <source> [<source> ...] -o <output folder> --project "<application name>" --author "<author name>"
```

Sources can be mixed in one run:

```bash
codemapper run ./php-intranet ./photos_batch_1.zip ./sonar_export/ -o archive --project "Intranet" --author "Simona Diana Thrussell PhD"
codemapper run https://gitlab.example.com/group/app.git -o archive --project "App"
```

Options:

| Option | Meaning |
|---|---|
| `-o`, `--out` | output folder (default `./archive`) |
| `-c`, `--config` | configuration file (.yml or .json), see section 4 |
| `--project` | application name printed on every document |
| `--author` | author name written on every document and in the file properties |
| `--tool-min-flows` | number of flows from which a shared function counts as a tool (default 3) |
| `--call-depth` | call levels followed from each entry point (default 4) |
| `--no-split-switch` | keep an endpoint that switches on a request parameter as one flow |
| `-q`, `--quiet` | no progress lines |

### From the web interface

```bash
codemapper serve --port 8080
```

Open http://127.0.0.1:8080, then:

1. give the application name and the author;
2. add the sources: upload files or archives (code, photos, SonarQube exports), or type server paths or git URLs,
   one per line;
3. start the run; the page shows the progress;
4. when the run ends, open the flow list or download the archive and the working report.

Runs and their results are kept in the data folder (`codemapper_data` by default) and can be deleted from the job page.

### What you get

`<project>_archive.zip`:

- `00_Archive_cover_sheet.pdf`
- one folder per module with its module cover sheet, one folder per functionality with its cover sheet, and one
  folder per flow with `FLW-xxx_cover_sheet.pdf`, `FLW-xxx_functional_flow.pdf` and `FLW-xxx_architectural_flow.pdf`
- `Flow_Tracker.xlsx`: every flow with its functionality, module, submodule, upstream and downstream flows, data
  sources and tools
- `Database_Tables_And_Calls.xlsx`: every database call per flow, the tables per flow and the table list
- `Tooling_And_Dependencies.xlsx`: tools (functions used by several flows) and dependencies (used by one or two)

`<project>_working_report.zip`: the working report with everything read, including the run notes.

### Reading photos of code

- One file per batch of photos works best; keep the photos in the order they were taken (the file names sort in
  that order).
- The file name is read from the screen header (address bar or file header with its size); photos without a header
  are joined to the file whose line numbers they continue.
- Sharp, straight photos with the line numbers visible give the best result. Large photos are read in bands, small
  ones are enlarged.

---

## 3. Deployment

### On a server (Linux)

```bash
sudo useradd --system --home /opt/codemapper codemapper
sudo mkdir -p /opt/codemapper && sudo chown codemapper: /opt/codemapper
sudo -u codemapper bash -c 'cd /opt/codemapper && python3 -m venv .venv && . .venv/bin/activate && pip install -r /path/to/requirements.txt && pip install /path/to/code-flow-mapper-1.0.0 waitress'
```

`/etc/systemd/system/codemapper.service`:

```ini
[Unit]
Description=Code Flow Mapper
After=network.target

[Service]
User=codemapper
WorkingDirectory=/opt/codemapper
Environment=CODEMAPPER_HOST=0.0.0.0
Environment=CODEMAPPER_PORT=8080
Environment=CODEMAPPER_DATA=/opt/codemapper/data
Environment=CODEMAPPER_USER=mapper
Environment=CODEMAPPER_PASSWORD=change-this
ExecStart=/opt/codemapper/.venv/bin/codemapper serve
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now codemapper
```

With `waitress` installed, `codemapper serve` uses it as the web server; without it, the built-in Flask server is used.
Put a reverse proxy (nginx, Apache) with HTTPS in front of it when it is reachable from other machines, and set its
upload limit to at least the value of `CODEMAPPER_MAX_UPLOAD_MB`.

### With Docker

```bash
docker build -t codemapper:1.0.0 .
docker run -d --name codemapper -p 8080:8080 \
  -e CODEMAPPER_USER=mapper -e CODEMAPPER_PASSWORD=change-this \
  -v codemapper_data:/data \
  codemapper:1.0.0
```

The image contains Tesseract and git. Results are kept in the `/data` volume.

To run a mapping without the web interface:

```bash
docker run --rm -v "$PWD/source:/src:ro" -v "$PWD/out:/out" codemapper:1.0.0 \
  codemapper run /src -o /out --project "App" --author "Simona Diana Thrussell PhD"
```

### Settings of the web interface (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `CODEMAPPER_HOST` | `127.0.0.1` (`0.0.0.0` in Docker) | address the server listens on |
| `CODEMAPPER_PORT` | `8080` | port |
| `CODEMAPPER_DATA` | `codemapper_data` (`/data` in Docker) | folder for uploads and results |
| `CODEMAPPER_USER`, `CODEMAPPER_PASSWORD` | not set | when both are set, every page asks for this user and password |
| `CODEMAPPER_ALLOW_PATHS` | `1` | `1` lets users type server paths as sources; set `0` on a shared server |
| `CODEMAPPER_MAX_UPLOAD_MB` | `2048` | largest upload accepted |

---

## 4. Configuration

Write a starter file and adjust it:

```bash
codemapper init-config codemapper.yml
codemapper run ./src -c codemapper.yml -o archive
```

| Key | Meaning |
|---|---|
| `project`, `author`, `organisation` | names printed on the documents |
| `include_globs`, `exclude_globs` | files analysed; vendor, node_modules, build output and tests are skipped by default |
| `max_file_kb` | larger files are skipped |
| `call_depth` | call levels followed from each entry point |
| `split_switch_flows` | one flow per case of an endpoint that switches on a request parameter |
| `tool_min_flows` | flows needed for a function to count as a tool (fewer flows: a dependency) |
| `platform_share` | share of flows from which a tool counts as a platform tool |
| `tool_rules` | your own tool capabilities, for example `[{name: Quotes, match: 'getQuote\|QuotesPort'}]` |
| `modules` | module and submodule from the path: `[{match: '<regex on the path>', module: '<name>', submodule: '<name>'}]` |
| `path_noise` | folder names skipped when the module is taken from the path |
| `functionalities` | explicit functionalities: `[{name, module, submodule, match: '<regex on the entry path or route>'}]` |
| `middle_layer_patterns` | calls that reach a middle layer or remote service |
| `auth_patterns` | authorisation checks |
| `connection_patterns` | database connection names |
| `ocr` | OCR language, page segmentation mode, enlargement and band settings |
| `sonar_project_key` | prefix removed from SonarQube component keys (found automatically when empty) |
| `archive_banned_words` | words that must not appear in the archive (the working report keeps everything) |

---

## 5. Project layout

```
codemapper/
  cli.py              command line (run, init-config, serve)
  config.py           settings and their defaults
  pipeline.py         sources -> analysis -> flows -> tooling -> archive
  ingest/             code folders, archives and git; OCR of photos; SonarQube exports
  analyzers/          PHP, Java, C#, JavaScript, markup; branches and calls
  analyze.py          entry points, call chains, data access, authorisation
  flows.py            flows, functionalities, upstream and downstream links
  tooling.py          tools, platform tools and dependencies
  render/             flow charts, cover sheets, trackers and the archive
  web/                web interface (Flask)
tests/sample_app/     small PHP, Java, C# and Node application used for the installation check
```
