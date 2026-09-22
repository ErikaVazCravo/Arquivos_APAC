"""Aplicativo web local do Editor APAC. Escuta apenas na interface de loopback."""
from __future__ import annotations

import copy
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import sys
import tempfile
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

from Editor_APAC import ApacFile, BODY_FIELDS, HEADER_FIELDS, PROC_FIELDS, VARIABLE_LAYOUTS, extract_field, set_field
from apac_report import generate_report, load_descriptions
from sigtap_tables import load_sigtap_folder


def application_directory():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


class WebEditor:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else application_directory()
        self.file = None
        self.version = 0
        self.lock = threading.RLock()
        self.catalog = {}
        self.table_status = ""
        self.reports = tempfile.TemporaryDirectory(prefix="editor_apac_web_")
        self.report_cache = None
        self.reload_tables()

    def close(self):
        self.reports.cleanup()

    def reload_tables(self):
        try:
            self.catalog = load_sigtap_folder(self.directory / "Tabelas_Sigtap")
            months = ", ".join(f"{m[4:]}/{m[:4]}" for m in self.catalog.competences)
            self.table_status = (f"SIGTAP: {len(self.catalog)} procedimentos · {months}" if self.catalog
                                 else "Adicione as tabelas na pasta Tabelas_Sigtap para carregar as descrições.")
        except (ValueError, OSError) as exc:
            self.catalog = {}
            self.table_status = f"Não foi possível carregar o SIGTAP: {exc}"
        self.report_cache = None

    def open_file(self, path):
        candidate = ApacFile(str(path))
        if not any(line.startswith("14") and len(line) >= 21 for line in candidate.lines):
            raise ValueError("O arquivo selecionado não possui registros de APAC.")
        self.file = candidate
        self.version += 1
        self.report_cache = None
        return self.state()

    def rows(self):
        if self.file is None:
            return []
        return [dict(index=i, number=line[8:21], competence=line[2:8], patient=line[57:87].strip(),
                     cnes=line[23:30].strip())
                for i, line in enumerate(self.file.lines) if line.startswith("14") and len(line) >= 21]

    def state(self):
        return dict(version=self.version, filename=self.file.path.name if self.file else "",
                    path=str(self.file.path) if self.file else "", apacs=self.rows(), table_status=self.table_status)

    def related(self, body_index):
        if self.file is None:
            raise ValueError("Selecione primeiro um arquivo APAC.")
        if not isinstance(body_index, int) or body_index < 0 or body_index >= len(self.file.lines):
            raise ValueError("APAC não encontrada.")
        body = self.file.lines[body_index]
        if not body.startswith("14") or len(body) < 21:
            raise ValueError("APAC não encontrada.")
        key = body[2:21]
        result = {body_index: BODY_FIELDS}
        header = next((i for i, line in enumerate(self.file.lines) if line.startswith("01")), None)
        if header is not None:
            result[header] = HEADER_FIELDS
        for i, line in enumerate(self.file.lines):
            if len(line) < 21 or line[2:21] != key:
                continue
            if line.startswith("13"):
                result[i] = PROC_FIELDS
            elif line[:2] in VARIABLE_LAYOUTS:
                result[i] = VARIABLE_LAYOUTS[line[:2]][1]
        return result

    def detail(self, body_index):
        schemas = self.related(body_index)
        records = []
        for index, fields in schemas.items():
            line = self.file.lines[index]
            typ = line[:2]
            title = {"14": "Dados da APAC", "01": "Cabeçalho do arquivo", "13": "Procedimento"}.get(typ)
            if typ in VARIABLE_LAYOUTS:
                title = VARIABLE_LAYOUTS[typ][0]
            description = ""
            if typ == "13":
                description = (self.catalog.description(line[21:31], line[2:8]) if hasattr(self.catalog, "description")
                               else self.catalog.get(line[21:31], ""))
            records.append(dict(index=index, type=typ, title=title, description=description,
                                fields=[asdict(field) | {"size": field.size, "value": extract_field(line, field)} for field in fields]))
        return dict(version=self.version, body_index=body_index, records=records)

    def save(self, payload, target=None):
        if payload.get("version") != self.version:
            raise ValueError("O arquivo mudou em outra aba. Recarregue a página antes de editar.")
        body_index = payload.get("body_index")
        schemas = self.related(body_index)
        changes = payload.get("changes", {})
        if not isinstance(changes, dict):
            raise ValueError("Alterações inválidas.")
        candidate = copy.copy(self.file)
        candidate.lines = list(self.file.lines)
        for raw_index, fields in changes.items():
            try:
                index = int(raw_index)
            except (ValueError, TypeError):
                raise ValueError("Registro inválido.") from None
            if index not in schemas or not isinstance(fields, dict):
                raise ValueError("O registro não pertence à APAC selecionada.")
            definitions = {field.key: field for field in schemas[index]}
            for key, value in fields.items():
                if key not in definitions or not isinstance(value, str):
                    raise ValueError("Campo inválido.")
                field = definitions[key]
                old = extract_field(self.file.lines[index], field)
                if value == old:
                    continue
                if field.read_only:
                    raise ValueError(f"{field.label}: campo somente para leitura.")
                if "\r" in value or "\n" in value or "\x00" in value:
                    raise ValueError(f"{field.label}: conteúdo inválido.")
                if field.kind == "NUM" and value.strip() and not re.fullmatch(r"[0-9]+", value.strip()):
                    raise ValueError(f"{field.label}: utilize apenas números.")
                if index == body_index and key == "apa_num" and not re.fullmatch(r"[0-9]{13}", value.strip()):
                    raise ValueError("O número da APAC deve conter exatamente 13 dígitos.")
                candidate.lines[index] = set_field(candidate.lines[index], field, value)
        before_body = self.file.lines[body_index]
        after_body = candidate.lines[body_index]
        new_num, new_month = after_body[8:21], after_body[2:8]
        if not re.fullmatch(r"[0-9]{13}", new_num):
            raise ValueError("O número da APAC deve conter exatamente 13 dígitos.")
        if after_body[2:21] != before_body[2:21]:
            duplicates = [i for i, line in enumerate(self.file.lines)
                          if i != body_index and line.startswith("14") and line[2:21] == before_body[2:21]]
            if duplicates:
                raise ValueError("Há registros duplicados desta APAC na mesma competência. Não é possível mudar seu número ou competência.")
            if any(i != body_index and line.startswith("14") and line[8:21] == new_num and line[2:8] == new_month
                   for i, line in enumerate(candidate.lines)):
                raise ValueError("Já existe uma APAC com esse número e competência.")
            for index in schemas:
                if index == body_index or candidate.lines[index].startswith("01"):
                    continue
                line = candidate.lines[index]
                candidate.lines[index] = line[:2] + new_month + new_num + line[21:]
        # Impede que procedimentos/laudos se desvinculem da competência do corpo.
        for index in schemas:
            if not candidate.lines[index].startswith("01") and candidate.lines[index][2:21] != candidate.lines[body_index][2:21]:
                raise ValueError("A competência dos procedimentos e laudos deve ser igual à da APAC. Altere a competência em Dados da APAC.")
        if self.file.path.read_bytes() != self.file.raw:
            raise ValueError("O arquivo foi alterado fora do editor. Abra-o novamente antes de salvar.")
        destination = Path(target).resolve() if target else self.file.path.resolve()
        candidate.recalc_header()
        try:
            data = candidate.newline.join(line.encode(candidate.encoding, errors="strict") for line in candidate.lines)
        except UnicodeEncodeError:
            raise ValueError("Há caracteres que não podem ser gravados no formato deste arquivo.") from None
        data += candidate.newline
        if candidate.has_ctrl_z:
            data += b"\x1a"
        same_file = destination == self.file.path.resolve()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".apac_", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if same_file:
                candidate.create_backup()
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        candidate.path = destination
        candidate.raw = data
        if not same_file:
            candidate.backup_created = False
        self.file = candidate
        self.version += 1
        self.report_cache = None
        return self.state()

    def report(self):
        if self.file is None:
            raise ValueError("Selecione primeiro um arquivo APAC.")
        if self.report_cache:
            return self.report_cache
        folder = Path(self.reports.name) / secrets.token_hex(8)
        _, pages = generate_report(self.file, BODY_FIELDS, PROC_FIELDS, VARIABLE_LAYOUTS, self.catalog, folder)
        self.report_cache = dict(directory=folder.name, pages=[path.name for _, path in pages])
        return self.report_cache


class NativeDialogs:
    """Os seletores nativos são executados na thread principal do Tkinter."""
    def __init__(self, root):
        self.root = root
        self.requests = queue.Queue()
        root.after(80, self.pump)

    def call(self, kind, initial=None):
        result = queue.Queue(maxsize=1)
        self.requests.put((kind, initial, result))
        value = result.get()
        if isinstance(value, Exception):
            raise value
        return value

    def pump(self):
        from tkinter import filedialog
        try:
            kind, initial, result = self.requests.get_nowait()
        except queue.Empty:
            self.root.after(80, self.pump)
            return
        try:
            if kind == "quit":
                result.put(True)
                self.root.quit()
                return
            self.root.attributes("-topmost", True)
            if kind == "save":
                selected = filedialog.asksaveasfilename(parent=self.root, title="Salvar arquivo APAC como",
                    initialdir=str(Path(initial).parent), initialfile=Path(initial).name, filetypes=[("Arquivo APAC", "*.*")])
            else:
                selected = filedialog.askopenfilename(parent=self.root,
                    title="Importar tabela CSV" if kind == "csv" else "Selecione o arquivo APAC",
                    filetypes=[("Tabela CSV", "*.csv")] if kind == "csv" else [("Arquivo APAC", "*.*")])
            result.put(selected)
        except Exception as exc:
            result.put(exc)
        finally:
            self.root.attributes("-topmost", False)
        self.root.after(80, self.pump)


def create_server(editor, dialogs, port=0, token=None):
    token = token or secrets.token_urlsafe(32)
    assets = Path(__file__).resolve().parent / "web_ui"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Evita gravar dados de pacientes e URLs de sessão em logs.

        def respond(self, content, mime="application/json; charset=utf-8", status=200):
            body = json.dumps(content, ensure_ascii=False).encode("utf-8") if isinstance(content, dict) else content
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(body)

        def route(self):
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                raise PermissionError("Endereço não autorizado.")
            parsed = urlsplit(self.path)
            prefix = f"/{token}/"
            if not parsed.path.startswith(prefix):
                raise PermissionError("Sessão inválida. Abra o Editor_APAC.exe novamente.")
            return parsed.path[len(prefix):], parse_qs(parsed.query)

        def do_GET(self):
            try:
                route, query = self.route()
                if route in ("", "app.js", "style.css"):
                    filename = route or "index.html"
                    mime = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8", "style.css": "text/css; charset=utf-8"}[filename]
                    return self.respond((assets / filename).read_bytes(), mime)
                with editor.lock:
                    if route == "api/state":
                        return self.respond(editor.state())
                    if route == "api/detail":
                        return self.respond(editor.detail(int(query.get("index", ["-1"])[0])))
                    if re.fullmatch(r"reports/[a-f0-9]{16}/(?:index|apac_[0-9]+)\.html", route):
                        relative = route.removeprefix("reports/")
                        return self.respond((Path(editor.reports.name) / relative).read_bytes(), "text/html; charset=utf-8")
                self.respond({"error": "Página não encontrada."}, status=404)
            except PermissionError as exc:
                self.respond({"error": str(exc)}, status=403)
            except (ValueError, OSError) as exc:
                self.respond({"error": str(exc)}, status=400)

        def do_POST(self):
            try:
                route, _ = self.route()
                origin = self.headers.get("Origin")
                if (origin and origin != f"http://127.0.0.1:{self.server.server_port}") or self.headers.get("X-APAC-Request") != "1":
                    raise PermissionError("Solicitação não autorizada.")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("Formato de solicitação inválido.")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2_000_000:
                    raise ValueError("Solicitação vazia ou muito grande.")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Solicitação inválida.")
                with editor.lock:
                    if route == "api/open":
                        path = dialogs.call("open")
                        return self.respond(editor.open_file(path) if path else {"cancelled": True})
                    if route == "api/save":
                        target = None
                        if payload.get("save_as"):
                            if editor.file is None:
                                raise ValueError("Selecione primeiro um arquivo APAC.")
                            target = dialogs.call("save", str(editor.file.path))
                            if not target:
                                return self.respond({"cancelled": True})
                        return self.respond(editor.save(payload, target))
                    if route == "api/report":
                        return self.respond(editor.report())
                    if route == "api/reload-tables":
                        editor.reload_tables()
                        return self.respond(editor.state())
                    if route == "api/import-table":
                        path = dialogs.call("csv")
                        if not path:
                            return self.respond({"cancelled": True})
                        catalog = load_descriptions(path)
                        editor.catalog = catalog
                        editor.table_status = f"CSV: {len(catalog)} descrições · {Path(path).name}"
                        editor.report_cache = None
                        return self.respond(editor.state())
                    if route == "api/quit":
                        self.respond({"closed": True})
                        threading.Thread(target=lambda: dialogs.call("quit"), daemon=True).start()
                        return
                self.respond({"error": "Ação não encontrada."}, status=404)
            except PermissionError as exc:
                self.respond({"error": str(exc)}, status=403)
            except (ValueError, OSError) as exc:
                self.respond({"error": str(exc)}, status=400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.session_url = f"http://127.0.0.1:{server.server_port}/{token}/"
    return server


def run():
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    editor = WebEditor()
    dialogs = NativeDialogs(root)
    server = create_server(editor, dialogs)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not webbrowser.open(server.session_url):
        messagebox.showinfo("Editor APAC", f"Abra este endereço no navegador:\n{server.session_url}", parent=root)
    try:
        root.mainloop()
    finally:
        server.shutdown()
        server.server_close()
        editor.close()
        root.destroy()
