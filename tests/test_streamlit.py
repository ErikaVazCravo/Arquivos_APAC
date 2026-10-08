import unittest
import gc
from pathlib import Path

from streamlit.testing.v1 import AppTest

from Editor_APAC import BODY_FIELDS
from test_apac import record
from test_web import sample_lines


class PatientSelectionTests(unittest.TestCase):
    def setUp(self):
        # Libera objetos dos testes Tkinter na thread principal antes do AppTest.
        gc.collect()
        lines = sample_lines() + [
            record(BODY_FIELDS, apa_corpo="14", apa_cmp="202608", apa_num="0000000000003", apa_nomepcnte="PACIENTE C"),
            record(BODY_FIELDS, apa_corpo="14", apa_cmp="202608", apa_num="0000000000004", apa_nomepcnte="PACIENTE D"),
        ]
        data = ("\r\n".join(lines) + "\r\n").encode("cp850")
        app_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"
        source = f'''
import io
from pathlib import Path
from unittest.mock import patch
import streamlit as st
uploaded = io.BytesIO({data!r})
uploaded.name = "teste.AGO"
__file__ = {str(app_path)!r}
with patch.object(type(st.sidebar), "file_uploader", return_value=uploaded):
    exec(compile(Path(__file__).read_text(encoding="utf-8"), __file__, "exec"))
'''
        self.app = AppTest.from_string(source, default_timeout=30).run()
        self.assertFalse(self.app.exception)
        self.addCleanup(self.app.session_state.editor.close)
        self.addCleanup(self.app.session_state.editor.file.path.unlink, missing_ok=True)

    def assert_selected(self, index):
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.radio[0].value, index)
        self.assertEqual(self.app.session_state.selected_index, index)
        patient = next(row["patient"] for row in self.app.session_state.editor.rows() if row["index"] == index)
        self.assertTrue(any(f"<h2>{patient}</h2>" in item.value for item in self.app.markdown))

    def click(self, label):
        next(button for button in self.app.button if button.label == label).click().run()

    def test_repeated_sidebar_selections_survive_rerun(self):
        selector_id = self.app.radio[0].proto.id
        for index in [4, 5, 6, 4, 1, 6, 5, 1]:
            self.app.radio[0].set_value(index).run()
            self.assert_selected(index)
            self.app.run()
            self.assert_selected(index)
            self.assertEqual(self.app.radio[0].proto.id, selector_id)

    def test_navigation_and_sidebar_stay_in_sync(self):
        for label, index in [("Próxima", 4), ("Última", 6), ("Anterior", 5), ("Primeira", 1)]:
            self.click(label)
            self.assert_selected(index)
        self.app.radio[0].set_value(5).run()
        self.assert_selected(5)
        self.click("Próxima")
        self.assert_selected(6)

    def test_search_and_edit_mode_do_not_restore_previous_patient(self):
        self.app.radio[0].set_value(5).run()
        self.click("Editar APAC")
        self.app.radio[0].set_value(6).run()
        self.assert_selected(6)
        self.assertFalse(self.app.session_state.editing_procedures)
        self.app.text_input[0].set_value("PACIENTE C").run()
        self.assert_selected(5)
        self.app.text_input[0].set_value("").run()
        self.assert_selected(5)
