"""Leitura das tabelas SIGTAP pelo layout que acompanha a competência."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import io
from pathlib import Path, PurePosixPath
import zipfile


def decode(raw):
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass


def parse_layout(raw):
    content = decode(raw)
    result = {}
    for row in csv.reader(io.StringIO(content), delimiter=";" if ";" in content.splitlines()[0] else ","):
        if len(row) < 4:
            continue
        try:
            start, end = int(row[2]), int(row[3])
        except ValueError:
            continue  # Cabeçalho do arquivo de layout.
        if start < 1 or end < start:
            raise ValueError("Posições inválidas no layout SIGTAP.")
        result[row[0].strip().upper()] = (start - 1, end)
    if not {"CO_PROCEDIMENTO", "NO_PROCEDIMENTO", "DT_COMPETENCIA"} <= result.keys():
        raise ValueError("Layout SIGTAP sem CO_PROCEDIMENTO, NO_PROCEDIMENTO ou DT_COMPETENCIA.")
    return result


@dataclass
class ProcedureCatalog:
    records: dict[tuple[str, str], str] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)

    def __len__(self):
        return len(self.records)

    @property
    def competences(self):
        return sorted({competence for competence, _ in self.records})

    def description(self, code, competence):
        return self.records.get((self.reference_competence(competence), code), "")

    def reference_competence(self, competence):
        months = self.competences
        if competence in months:
            return competence
        earlier = [month for month in months if month <= competence]
        return max(earlier) if earlier else (min(months) if months else "")

    def add(self, data, layout, source):
        positions = parse_layout(layout)
        rows = decode(data).splitlines()
        added = 0
        for number, line in enumerate(rows, 1):
            if not line.strip():
                continue
            code, name, competence = (line[slice(*positions[key])].strip()
                                      for key in ("CO_PROCEDIMENTO", "NO_PROCEDIMENTO", "DT_COMPETENCIA"))
            if (len(code) != 10 or not code.isdigit() or not name or len(competence) != 6
                    or not competence.isdigit() or not 1 <= int(competence[4:]) <= 12):
                raise ValueError(f"Tabela SIGTAP inválida: {source}, linha {number}.")
            key = (competence, code)
            if key in self.records and self.records[key] != name:
                raise ValueError(f"Descrições divergentes para {code}, competência {competence}. Mantenha apenas uma versão da tabela dessa competência.")
            self.records[key] = name
            added += 1
        if not added:
            raise ValueError(f"Tabela sem procedimentos: {source}.")
        self.sources.append(source)


def load_sigtap_folder(folder):
    """Aceita tabelas extraídas em subpastas ou pacotes ZIP, sem extrair arquivos."""
    folder = Path(folder)
    catalog = ProcedureCatalog()
    if not folder.is_dir():
        return catalog
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() == "tb_procedimento.txt":
            layout = next((p for p in path.parent.iterdir() if p.name.lower() == "tb_procedimento_layout.txt"), None)
            if layout is None:
                raise ValueError(f"Falta tb_procedimento_layout.txt junto de {path.name} em {path.parent}.")
            catalog.add(path.read_bytes(), layout.read_bytes(), str(path.relative_to(folder)))
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                names = {name.lower(): name for name in archive.namelist()}
                for name in archive.namelist():
                    if PurePosixPath(name).name.lower() != "tb_procedimento.txt":
                        continue
                    layout_key = str(PurePosixPath(name).with_name("tb_procedimento_layout.txt")).lower()
                    if layout_key not in names:
                        raise ValueError(f"Falta tb_procedimento_layout.txt dentro de {path.name}.")
                    catalog.add(archive.read(name), archive.read(names[layout_key]), f"{path.name}/{name}")
    return catalog
