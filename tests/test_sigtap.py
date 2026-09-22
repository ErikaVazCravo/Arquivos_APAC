from pathlib import Path
import tempfile
import unittest
import zipfile

from sigtap_tables import load_sigtap_folder


LAYOUT = b"Coluna,Tamanho,Inicio,Fim,Tipo\nCO_PROCEDIMENTO,10,1,10,VARCHAR2\nNO_PROCEDIMENTO,250,11,260,VARCHAR2\nDT_COMPETENCIA,6,261,266,CHAR\n"


def row(month, name="PUNÇÃO TESTE"):
    return ("0201010607" + name.ljust(250) + month + "\r\n").encode("cp1252")


class SigtapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def test_zip_and_txt_match_by_competence(self):
        subdir = self.folder / "julho"
        subdir.mkdir()
        (subdir / "tb_procedimento.txt").write_bytes(row("202607"))
        (subdir / "tb_procedimento_layout.txt").write_bytes(LAYOUT)
        with zipfile.ZipFile(self.folder / "agosto.zip", "w") as archive:
            archive.writestr("dados/tb_procedimento.txt", row("202608", "OUTRO NOME"))
            archive.writestr("dados/tb_procedimento_layout.txt", LAYOUT)
        catalog = load_sigtap_folder(self.folder)
        self.assertEqual(len(catalog), 2)
        self.assertEqual(catalog.description("0201010607", "202607"), "PUNÇÃO TESTE")
        self.assertEqual(catalog.description("0201010607", "202608"), "OUTRO NOME")
        self.assertEqual(catalog.reference_competence("202606"), "202607")
        self.assertEqual(catalog.reference_competence("202609"), "202608")
        self.assertEqual("", catalog.description("9999999999", "202606"))

    def test_missing_layout(self):
        (self.folder / "tb_procedimento.txt").write_bytes(row("202607"))
        with self.assertRaisesRegex(ValueError, "Falta"):
            load_sigtap_folder(self.folder)

    def test_empty_folder(self):
        self.assertFalse(load_sigtap_folder(self.folder))

    def test_ambiguous_version_rejected(self):
        for name in ("primeira", "segunda"):
            subdir = self.folder / name
            subdir.mkdir()
            (subdir / "tb_procedimento.txt").write_bytes(row("202607", name))
            (subdir / "tb_procedimento_layout.txt").write_bytes(LAYOUT)
        with self.assertRaisesRegex(ValueError, "divergentes"):
            load_sigtap_folder(self.folder)


if __name__ == "__main__":
    unittest.main()
