"""Confere o pacote Windows sem abrir o navegador do usuário."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
from urllib.request import Request, urlopen


root = Path(__file__).resolve().parents[1]
session_file = root / "build" / "qa_web" / "packaged_url.txt"

if len(sys.argv) > 1 and sys.argv[1] == "--capture-url":
    session_file.write_text(sys.argv[2], encoding="utf-8")
    raise SystemExit(0)

session_file.parent.mkdir(parents=True, exist_ok=True)
session_file.unlink(missing_ok=True)
executable = root / "Editor_APAC.exe"
data = executable.read_bytes()
pe = struct.unpack_from("<I", data, 60)[0]
assert struct.unpack_from("<H", data, pe + 24 + 68)[0] == 2, "O executável não é do tipo gráfico."
environment = dict(os.environ)
pythonw = Path(sys.executable).with_name("pythonw.exe").as_posix()
environment["BROWSER"] = f'"{pythonw}" "{Path(__file__).resolve().as_posix()}" --capture-url %s'
process = subprocess.Popen([str(executable)], cwd=root, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
url = None
try:
    deadline = time.monotonic() + 35
    while not session_file.exists() and time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(f"O executável encerrou antes de iniciar: {process.returncode}")
        time.sleep(.2)
    assert session_file.exists(), "O executável não abriu o endereço do editor."
    url = session_file.read_text(encoding="utf-8").strip()
    with urlopen(url, timeout=10) as response:
        html = response.read().decode("utf-8")
        assert 'id="editor-view" class="active"' in html
        assert 'id="report-view"' in html
    with urlopen(url + "app.js", timeout=10) as response:
        assert b"saveDirect" in response.read()
    with urlopen(url + "api/state", timeout=10) as response:
        state = json.load(response)
        assert state["filename"] == ""
        assert "5023" in state["table_status"], state["table_status"]
    print("OK: executavel sem console, editor web inicial, arquivos da interface incluidos e SIGTAP carregado.", flush=True)
finally:
    if url:
        request = Request(url + "api/quit", data=b"{}", headers={"Content-Type": "application/json", "X-APAC-Request": "1"})
        with urlopen(request, timeout=10):
            pass
        process.wait(timeout=15)
        assert process.returncode == 0, process.returncode
        session_file.unlink(missing_ok=True)
