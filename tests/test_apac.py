import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import Editor_APAC as app
from apac_report import generate_report, load_descriptions
from sigtap_tables import load_sigtap_folder


NUM = "1234567890123"
OTHER = "1234567890124"


def record(schema, **items):
    line = " " * max(field.end for field in schema)
    for field in schema:
        if field.key in items:
            value = str(items[field.key]).ljust(field.size)
            line = line[:field.start - 1] + value + line[field.end:]
    return line


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "teste.JUL"
        body = record(app.BODY_FIELDS, apa_corpo="14", apa_cmp="202607", apa_num=NUM,
                      apa_nomepcnte="PACIENTE <script> & TESTE", apa_datanascim="20051219",
                      apa_cpfpcnte="01234567890", apa_dtiinval="20260618")
        proc = record(app.PROC_FIELDS, pap_corpo="13", pap_cmp="202607", pap_num=NUM,
                      pap_codproc="0901010103", pap_cbo="225255", pap_qtdprod="0000001",
                      pap_CGC="12345678901234", pap_NF="ABC123", pap_SRV="001",
                      pap_CLF="002", pap_cnes_terc="2082527", pap_CIDP="N63", pap_CIDS="Z00")
        variable = record(app.VARIABLE_LAYOUTS["06"][1], apa_varia="06", apa_cmp="202607",
                          apa_num=NUM, apa_cidpri="N63", apa_dtiden="20260625")
        another = record(app.BODY_FIELDS, apa_corpo="14", apa_cmp="202607", apa_num=OTHER,
                         apa_nomepcnte="OUTRO PACIENTE")
        # Mesmo número em outra competência: procedimentos não podem se misturar.
        later = record(app.BODY_FIELDS, apa_corpo="14", apa_cmp="202608", apa_num=NUM,
                       apa_nomepcnte="OUTRA COMPETENCIA")
        self.source.write_bytes(("\r\n".join([body, proc, variable, another, later]) + "\r\n").encode("cp850"))
        self.file = app.ApacFile(str(self.source))

    def test_all_pages_read_only_and_source_unchanged(self):
        before = self.source.read_bytes()
        lines = list(self.file.lines)
        index, pages = generate_report(self.file, app.BODY_FIELDS, app.PROC_FIELDS,
                                       app.VARIABLE_LAYOUTS, {"0901010103": "PROCEDIMENTO TESTE"}, self.root / "html")
        self.assertEqual(len(pages), 3)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.file.lines, lines)
        self.assertIn("3 APAC(s)", index.read_text(encoding="utf-8"))
        html = pages[0][1].read_text(encoding="utf-8")
        for value in ["PROCEDIMENTO TESTE", "225255", "0000001", "12345678901234", "ABC123",
                      "001", "002", "2082527", "N63", "Z00", "25/06/2026", "19/12/2005", "01234567890"]:
            self.assertIn(value, html)
        self.assertIn("&lt;script&gt; &amp;", html)
        titles = [
            "Identificação do usuário", "Endereço e contato", "Procedimentos",
            "Dados complementares", "Laudo Geral", "Identificação da APAC",
            "Solicitação e autorização", "Outras informações",
        ]
        positions = [html.index(f">{title}</h2>") for title in titles]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("<input", html)
        self.assertNotIn("<form", html)
        self.assertNotIn("contenteditable", html)
        self.assertIn('<dt>CPF do médico responsável</dt><dd class="muted"></dd>', html)
        for _, page in pages:
            rendered = page.read_text(encoding="utf-8")
            self.assertNotIn("Não informado", rendered)
            self.assertNotIn("Não disponível", rendered)
            self.assertNotIn("Nenhum procedimento informado", rendered)
            self.assertNotIn("Nenhum registro complementar informado", rendered)
        for _, path in pages:
            self.assertTrue(path.is_file())

    def test_csv_leading_zeros_and_escaped_description(self):
        csv = self.root / "tabela.csv"
        csv.write_text('codigo;descricao\n02.01.01.060-7;"PUNÇÃO; TESTE"\n', encoding="utf-8-sig")
        self.assertEqual(load_descriptions(csv), {"0201010607": "PUNÇÃO; TESTE"})
        csv.write_text("codigo;descricao\n123;ERRO\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_descriptions(csv)

    def test_empty_file(self):
        self.file.lines = []
        with self.assertRaisesRegex(ValueError, "não possui"):
            generate_report(self.file, app.BODY_FIELDS, app.PROC_FIELDS, app.VARIABLE_LAYOUTS, output_dir=self.root / "empty")

    def test_installed_sigtap_report_and_competence_notice(self):
        catalog = load_sigtap_folder(Path(app.__file__).parent / "Tabelas_Sigtap")
        if "202608" not in catalog.competences:
            self.skipTest("Tabela SIGTAP 08/2026 não instalada neste computador")
        self.assertIn("PUNÇÃO", catalog.description("0201010607", "202608"))
        _, pages = generate_report(self.file, app.BODY_FIELDS, app.PROC_FIELDS,
                                    app.VARIABLE_LAYOUTS, catalog, self.root / "sigtap_html")
        html = pages[0][1].read_text(encoding="utf-8")
        self.assertIn("OCI PROGRESSÃO DA AVALIAÇÃO DIAGNÓSTICA", html)
        self.assertIn("SIGTAP 08/2026", html)
        if "202607" not in catalog.competences:
            self.assertIn("APAC (07/2026)", html)


class WindowTests(ReportTests):
    def setUp(self):
        super().setUp()
        # Elimina a duplicidade proposital usada nos testes de relatório.
        self.file.lines = self.file.lines[:-1]
        self.gui = app.StartApp()
        self.gui.withdraw()
        self.gui.file = self.file
        self.addCleanup(self.gui.destroy)
        self.dialogs = patch.multiple(app.messagebox, showinfo=lambda *a, **k: None,
                                      showerror=lambda *a, **k: None, showwarning=lambda *a, **k: None)
        self.dialogs.start()
        self.addCleanup(self.dialogs.stop)

    # ReportTests são executados separadamente; apenas reaproveita a fixture.
    test_all_pages_read_only_and_source_unchanged = None
    test_csv_leading_zeros_and_escaped_description = None
    test_empty_file = None
    test_installed_sigtap_report_and_competence_notice = None

    def test_single_window_navigation_and_return(self):
        self.gui.deiconify()
        editor = app.EditorWindow(self.gui, self.file, NUM)
        self.gui.update()
        self.assertEqual(self.gui.state(), "withdrawn")
        self.assertEqual(editor.state(), "normal")
        editor.switch_apac(OTHER)
        self.gui.update()
        editors = [w for w in self.gui.winfo_children() if isinstance(w, app.EditorWindow)]
        self.assertEqual(len(editors), 1)
        self.assertEqual(editors[0].original_apac_num, OTHER)
        self.assertEqual(self.gui.state(), "withdrawn")
        editors[0].close()
        self.gui.update()
        self.assertEqual(self.gui.state(), "normal")

    def test_cancel_and_discard_edits(self):
        editor = app.EditorWindow(self.gui, self.file, NUM)
        editor.body_form.entries["apa_nomepcnte"].set("ALTERADO")
        with patch.object(app.messagebox, "askyesnocancel", return_value=None):
            editor.switch_apac(OTHER)
        self.assertTrue(editor.winfo_exists())
        with patch.object(app.messagebox, "askyesnocancel", return_value=False):
            editor.switch_apac(OTHER)
        self.assertIn("PACIENTE <script>", self.file.lines[0])

    def test_rename_saved_and_propagated(self):
        editor = app.EditorWindow(self.gui, self.file, NUM)
        new_num = "1234567890999"
        editor.body_form.entries["apa_num"].set(new_num)
        self.assertTrue(editor.save())
        self.assertEqual([line[8:21] for line in self.file.lines[:3]], [new_num] * 3)
        self.assertFalse(editor.has_changes())
        self.assertEqual(len(list(self.root.glob("*.backup_*"))), 1)


if __name__ == "__main__":
    unittest.main()
