from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile

import streamlit as st

from Editor_APAC import ApacFile, BODY_FIELDS, extract_field, set_field


def load_uploaded_file(uploaded_file):
    data = uploaded_file.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    if st.session_state.get("file_digest") == digest:
        return st.session_state.apac_file

    suffix = Path(uploaded_file.name).suffix or ".apac"
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temporary.write(data)
    temporary.close()
    apac_file = ApacFile(temporary.name)
    if not any(line.startswith("14") and len(line) >= 21 for line in apac_file.lines):
        raise ValueError("O arquivo selecionado não possui registros de APAC.")
    st.session_state.file_digest = digest
    st.session_state.apac_file = apac_file
    st.session_state.file_name = uploaded_file.name
    return apac_file


def apac_rows(apac_file):
    return [
        (index, line[8:21], line[57:87].strip(), line[23:30].strip())
        for index, line in enumerate(apac_file.lines)
        if line.startswith("14") and len(line) >= 21
    ]


def edit_apac(apac_file, index):
    line = apac_file.lines[index]
    st.subheader("Dados da APAC")
    changes = {}
    columns = st.columns(2)
    for position, field in enumerate(BODY_FIELDS):
        value = extract_field(line, field)
        with columns[position % 2]:
            edited = st.text_input(
                field.label,
                value=value,
                max_chars=field.size,
                disabled=field.read_only,
                help=f"Posições {field.start}-{field.end}. {field.desc}",
                key=f"field_{index}_{field.key}",
            )
        if edited != value:
            changes[field.key] = edited

    if st.button("Salvar alterações", type="primary"):
        candidate = list(apac_file.lines)
        definitions = {field.key: field for field in BODY_FIELDS}
        for key, value in changes.items():
            field = definitions[key]
            if field.kind == "NUM" and value.strip() and not value.strip().isdigit():
                st.error(f"{field.label}: utilize apenas números.")
                return
            if "\r" in value or "\n" in value or "\x00" in value:
                st.error(f"{field.label}: conteúdo inválido.")
                return
            candidate[index] = set_field(candidate[index], field, value)

        if not candidate[index][8:21].isdigit() or len(candidate[index][8:21]) != 13:
            st.error("O número da APAC deve conter exatamente 13 dígitos.")
            return
        apac_file.lines = candidate
        st.success("Alterações aplicadas. Baixe o arquivo atualizado abaixo.")
        st.rerun()


st.set_page_config(page_title="Editor APAC", page_icon="📄", layout="wide")
st.title("Editor de Arquivo APAC")
st.caption("Envie um arquivo APAC, edite os dados e baixe uma cópia atualizada.")

uploaded_file = st.file_uploader("Arquivo APAC", type=None)
if uploaded_file is None:
    st.info("Selecione um arquivo APAC para começar.")
    st.stop()

try:
    apac_file = load_uploaded_file(uploaded_file)
except (OSError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

rows = apac_rows(apac_file)
labels = {index: f"{number} | {patient or 'Paciente sem nome'} | CNES {cnes}" for index, number, patient, cnes in rows}
selected_index = st.selectbox("APAC", [index for index, *_ in rows], format_func=labels.get)
edit_apac(apac_file, selected_index)

content = apac_file.newline.join(line.encode(apac_file.encoding, errors="strict") for line in apac_file.lines)
content += apac_file.newline
if apac_file.has_ctrl_z:
    content += b"\x1a"
st.download_button(
    "Baixar arquivo atualizado",
    data=content,
    file_name=st.session_state.file_name,
    mime="application/octet-stream",
)