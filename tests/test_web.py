import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from apac_web import WebEditor, create_server
from Editor_APAC import BODY_FIELDS, PROC_FIELDS, HEADER_FIELDS, VARIABLE_LAYOUTS
from test_apac import record, NUM, OTHER


def sample_lines():
    return [
        record(HEADER_FIELDS, cbc_hdr="01", cbc_apac="#APAC", cbc_cmp="202608", cbc_lin="000002", cbc_smt_vrf="1111"),
        record(BODY_FIELDS, apa_corpo="14", apa_cmp="202608", apa_num=NUM, apa_nomepcnte="PACIENTE EXEMPLO A", apa_cpfpcnte="01234567890"),
        record(PROC_FIELDS, pap_corpo="13", pap_cmp="202608", pap_num=NUM, pap_codproc="0201010607", pap_cbo="225230", pap_qtdprod="0000001"),
        record(VARIABLE_LAYOUTS["06"][1], apa_varia="06", apa_cmp="202608", apa_num=NUM, apa_cidpri="N63", apa_dtiden="20260801"),
        record(BODY_FIELDS, apa_corpo="14", apa_cmp="202608", apa_num=OTHER, apa_nomepcnte="PACIENTE EXEMPLO B"),
    ]


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.path = self.folder / "teste.AGO"
        self.path.write_bytes(("\r\n".join(sample_lines()) + "\r\n\x1a").encode("cp850"))
        self.original = self.path.read_bytes()
        self.editor = WebEditor(self.folder)
        self.addCleanup(self.editor.close)
        self.editor.open_file(self.path)

    def payload(self, changes):
        return dict(version=self.editor.version, body_index=1, changes=changes)

    def test_save_backup_format_and_reload(self):
        result = self.editor.save(self.payload({"1": {"apa_nomepcnte": "NOME EDITADO"}, "2": {"pap_qtdprod": "3"}}))
        self.assertEqual(result["apacs"][0]["patient"], "NOME EDITADO")
        self.assertEqual(self.editor.file.lines[2][37:44], "0000003")
        self.assertEqual(self.editor.file.lines[0][13:19], "000002")
        self.assertTrue(self.path.read_bytes().endswith(b"\r\n\x1a"))
        self.assertEqual(next(self.folder.glob("*.backup_*")).read_bytes(), self.original)
        self.editor.save(self.payload({"1": {"apa_nomepcnte": "OUTRO NOME"}}))
        self.assertEqual(len(list(self.folder.glob("*.backup_*"))), 1)

    def test_invalid_and_readonly_changes_are_atomic(self):
        for changes in [{"1": {"apa_nomepcnte": "X" * 31}}, {"2": {"pap_corpo": "14"}},
                        {"4": {"apa_nomepcnte": "FORA DA APAC"}}, {"1": {"apa_cpfpcnte": "ABC"}}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.editor.save(self.payload(changes))
            self.assertEqual(self.path.read_bytes(), self.original)
            self.assertEqual(self.editor.file.lines, sample_lines())

    def test_number_and_competence_propagation(self):
        self.editor.save(self.payload({"1": {"apa_num": "0000000000099", "apa_cmp": "202609"}}))
        for line in self.editor.file.lines[1:4]:
            self.assertEqual(line[2:21], "2026090000000000099")
        self.assertEqual(self.editor.file.lines[4][8:21], OTHER)

    def test_collision_is_rejected_without_changes(self):
        with self.assertRaisesRegex(ValueError, "Já existe"):
            self.editor.save(self.payload({"1": {"apa_num": OTHER}}))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_same_number_other_month_is_separate(self):
        self.editor.file.lines.append(record(BODY_FIELDS, apa_corpo="14", apa_cmp="202609", apa_num=NUM))
        self.editor.file.lines.append(record(PROC_FIELDS, pap_corpo="13", pap_cmp="202609", pap_num=NUM))
        indexes = [r["index"] for r in self.editor.detail(1)["records"]]
        self.assertNotIn(6, indexes)
        self.assertEqual(len(self.editor.rows()), 3)

    def test_stale_tab_and_external_edits_rejected(self):
        old = self.payload({"1": {"apa_nomepcnte": "ANTIGO"}})
        self.editor.save(self.payload({"1": {"apa_nomepcnte": "SALVO"}}))
        with self.assertRaisesRegex(ValueError, "outra aba"):
            self.editor.save(old)
        self.path.write_bytes(b"ALTERADO EXTERNAMENTE")
        with self.assertRaisesRegex(ValueError, "fora do editor"):
            self.editor.save(self.payload({}))

    def test_save_as_keeps_original(self):
        destination = self.folder / "copia.AGO"
        self.editor.save(self.payload({"1": {"apa_nomepcnte": "COPIA"}}), destination)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(destination.exists())
        self.assertEqual(self.editor.file.path, destination)

    def test_report_is_readonly_and_blank_for_missing_values(self):
        data = self.editor.report()
        html = (Path(self.editor.reports.name) / data["directory"] / data["pages"][0]).read_text(encoding="utf-8")
        self.assertNotIn("<input", html)
        self.assertNotIn("Não informado", html)
        self.assertNotIn("Não disponível", html)
        self.assertEqual(self.path.read_bytes(), self.original)


class HttpTests(WebTests):
    def setUp(self):
        super().setUp()
        class Dialogs:
            def call(_self, kind, initial=None):
                return ""
        self.server = create_server(self.editor, Dialogs(), token="test-session")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, route, payload=None, headers=None):
        options = {}
        if payload is not None:
            options = dict(data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "X-APAC-Request": "1"})
        options.setdefault("headers", {}).update(headers or {})
        return urlopen(Request(self.server.session_url + route, **options), timeout=5)

    def test_shell_and_api(self):
        with self.request("") as response:
            html = response.read().decode()
            self.assertLess(html.index('id="editor-view"'), html.index('id="report-view"'))
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        with self.request("api/detail?index=1") as response:
            self.assertEqual(json.load(response)["body_index"], 1)
        with self.request("api/open", {}) as response:
            self.assertTrue(json.load(response)["cancelled"])
        with self.request("api/save", self.payload({"1": {"apa_nomepcnte": "WEB"}})) as response:
            self.assertEqual(json.load(response)["apacs"][0]["patient"], "WEB")

    def test_cross_origin_and_untrusted_host_rejected(self):
        for headers in [{"Origin": "https://example.com"}, {"Host": "example.com"}, {"X-APAC-Request": "0"}]:
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as error:
                self.request("api/save", self.payload({}), headers)
            self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_report_route_and_traversal(self):
        data = self.editor.report()
        with self.request(f'reports/{data["directory"]}/{data["pages"][0]}') as response:
            self.assertIn(b"Dados para digita", response.read())
        with self.assertRaises(HTTPError) as error:
            self.request("reports/../../Editor_APAC.py")
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
