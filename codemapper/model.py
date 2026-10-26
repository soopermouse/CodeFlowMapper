"""Data model shared by the ingesters, analyzers, flow builder and renderers."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SourceFile:
    path: str                      # project-relative path, forward slashes
    text: str
    language: str                  # php, java, csharp, js, html, template, sql, other
    origin: str = 'code'           # code | ocr | sonar
    size: int = 0
    images: list = field(default_factory=list)   # source images when origin == 'ocr'
    issues: list = field(default_factory=list)   # SonarQube issues attached to this file


@dataclass
class Param:
    name: str
    source: str                    # GET, POST, REQUEST, query, body, path, form, cookie, session
    line: int = 0


@dataclass
class Option:
    value: str
    label: str
    selected: bool = False


@dataclass
class Field_:
    name: str
    kind: str                      # text, select, checkbox, radio, hidden, textarea, submit, file, date, password ...
    label: str = ''
    required: bool = False
    options: list = field(default_factory=list)   # [Option]
    options_source: str = ''       # when the options are filled by code (loop over a call / variable)
    default: str = ''
    maxlength: str = ''
    pattern: str = ''
    file: str = ''
    line: int = 0


@dataclass
class Form:
    name: str
    action: str
    method: str
    fields: list = field(default_factory=list)
    file: str = ''
    line: int = 0


@dataclass
class SqlStmt:
    kind: str                      # SELECT, INSERT, UPDATE, DELETE, EXEC (stored procedure), CALL, MERGE, DDL
    text: str
    tables: list = field(default_factory=list)
    procedure: str = ''
    params: list = field(default_factory=list)
    file: str = ''
    line: int = 0
    function: str = ''


@dataclass
class Call:
    name: str                      # Class::method, obj->method, func, Service.method
    args: str = ''
    file: str = ''
    line: int = 0
    kind: str = 'call'             # call | middle_layer | http | db | auth | render | redirect
    target: str = ''               # resolved function key when known


@dataclass
class Function:
    key: str                       # Class::method or function name, unique within the project
    name: str
    cls: str
    file: str
    line: int
    end_line: int
    body: str
    params: str = ''
    visibility: str = ''
    calls: list = field(default_factory=list)
    sql: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    branches: list = field(default_factory=list)
    params_read: list = field(default_factory=list)
    links: list = field(default_factory=list)
    connections: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    annotations: str = ''


@dataclass
class Branch:
    """A decision in the code: switch on a request parameter, or if / else on a condition."""
    subject: str                   # e.g. $_GET['action'], req.query.mode, condition text
    kind: str                      # switch | if
    cases: list = field(default_factory=list)   # [(label, body_text, line)]
    file: str = ''
    line: int = 0


@dataclass
class EntryPoint:
    key: str                       # unique id inside the project (file or file#handler)
    file: str
    kind: str                      # page | route | controller_action | servlet | endpoint | script
    name: str                      # display name
    method: str = ''               # HTTP method(s)
    route: str = ''                # URL / route pattern
    handler: str = ''              # function key handling the entry
    body: str = ''                 # code of the entry (page body or handler body)
    line: int = 1


@dataclass
class Flow:
    id: str
    entry: EntryPoint
    name: str
    module: str = ''
    submodule: str = ''
    functionality: str = ''
    params: list = field(default_factory=list)
    roles: list = field(default_factory=list)
    forms: list = field(default_factory=list)
    branches: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    functions: list = field(default_factory=list)   # function keys reached
    files: list = field(default_factory=list)       # includes / imports / classes reached
    templates: list = field(default_factory=list)
    sql: list = field(default_factory=list)
    procedures: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    middle_layer: list = field(default_factory=list)
    connections: list = field(default_factory=list)  # database / connection names seen
    messages: list = field(default_factory=list)    # validation and user messages
    outputs: list = field(default_factory=list)     # rendered templates, redirects, JSON, downloads
    links: list = field(default_factory=list)       # URLs / routes this flow links or posts to
    upstream: list = field(default_factory=list)    # flow ids
    downstream: list = field(default_factory=list)
    tools: list = field(default_factory=list)       # tool ids used
    dependencies: list = field(default_factory=list)
    issues: list = field(default_factory=list)      # SonarQube issues on the files of the flow
    unresolved: list = field(default_factory=list)  # names called but not found (working report only)
    origin: str = 'code'
    business: str = ''
    branch_detail: list = field(default_factory=list)
    case: Optional[tuple] = None                    # (switch subject, case label) when the flow is one case of a switch


@dataclass
class Tool:
    id: str
    name: str
    kind: str                      # Platform tool | Tool | Dependency
    functions: list = field(default_factory=list)
    flows: list = field(default_factory=list)
    functionalities: list = field(default_factory=list)


@dataclass
class Project:
    name: str
    files: dict = field(default_factory=dict)       # path -> SourceFile
    functions: dict = field(default_factory=dict)   # key -> Function
    entries: list = field(default_factory=list)
    flows: list = field(default_factory=list)
    tools: list = field(default_factory=list)
    file_dependencies: list = field(default_factory=list)
    log: list = field(default_factory=list)          # working notes (never in the archive)
    sonar: dict = field(default_factory=dict)        # measures, scanner info
    facts: dict = field(default_factory=dict)        # path -> FileFacts
    class_parent: dict = field(default_factory=dict) # class -> parent class
    implementations: dict = field(default_factory=dict)  # interface -> [classes]
    entities: dict = field(default_factory=dict)     # entity / model class -> table name
    edges: list = field(default_factory=list)        # (from flow, to flow, type, via)

    def note(self, msg: str):
        self.log.append(msg)
