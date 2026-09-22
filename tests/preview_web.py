"""Servidor temporário de QA: usa exclusivamente registros fictícios."""
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apac_web import WebEditor, create_server
from test_web import sample_lines


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="qa_apac_") as temporary:
        folder = Path(temporary)
        source = folder / "EXEMPLO_FICTICIO.AGO"
        source.write_bytes(("\r\n".join(sample_lines()) + "\r\n").encode("cp850"))
        editor = WebEditor()
        class Dialogs:
            def call(self, kind, initial=None):
                if kind == "quit":
                    threading.Thread(target=server.shutdown, daemon=True).start()
                    return True
                return str(folder / "COPIA_FICTICIA.AGO") if kind == "save" else str(source)
        server = create_server(editor, Dialogs())
        print(server.session_url, flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()
            editor.close()
