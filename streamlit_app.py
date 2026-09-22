from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
import tempfile

import streamlit as st

from apac_web import WebEditor


st.set_page_config(page_title="Editor APAC", page_icon="A", layout="wide")

st.markdown(
    """
    <style>
    :root { --apac-blue: #164887; --apac-line: #d9e2ee; --apac-muted: #61748c; }
    .block-container { padding: 1.25rem 2rem 3rem; max-width: 1500px; }
    .apac-header { background: #113e7a; color: white; padding: 1.25rem 1.6rem; margin: 0 -2rem 1.25rem; border-bottom: 4px solid #eead3d; }
    .apac-header h1 { margin: 0; font-size: 1.55rem; }
    .apac-header p { margin: .25rem 0 0; color: #c5d7ed; font-size: .8rem; }
    .record-title { border-bottom: 1px solid var(--apac-line); padding: .5rem 0 .9rem; margin-bottom: 1rem; }
    .record-title h2 { margin: .2rem 0; color: #1c304b; }
    .record-title p { margin: 0; color: var(--apac-muted); }
    div[data-testid="stSidebar"] { background: #f8fafd; border-right: 1px solid var(--apac-line); }
    div[data-testid="stForm"] { border: 1px solid var(--apac-line); border-radius: 8px; padding: 1rem; }
    div[data-testid="stSidebar"] h2 { color: var(--apac-blue); }
    div[data-testid="stVerticalBlockBorderWrapper"] { border-color: var(--apac-line); background: white; }
    div[data-testid="stVerticalBlockBorderWrapper"] h3 { color: var(--apac-blue); margin-top: 0; }
    </style>
    <div class="apac-header"><h1>Editor APAC</h1><p>Edicao e consulta de arquivos APAC</p></div>
    """,
    unsafe_allow_html=True,
)


def normalize(value):
    return str(value).casefold()


def load_file(uploaded_file):
    data = uploaded_file.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    if st.session_state.get("file_digest") == digest:
        return st.session_state.editor

    suffix = Path(uploaded_file.name).suffix or ".apac"
    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temporary.write(data)
    temporary.close()
    editor = WebEditor(Path(__file__).resolve().parent)
    editor.open_file(temporary.name)
    st.session_state.editor = editor
    st.session_state.file_digest = digest
    st.session_state.file_name = uploaded_file.name
    st.session_state.selected_index = editor.state()["apacs"][0]["index"]
    return editor


def field_width(field):
    """Dá mais espaço aos campos longos sem deixar os curtos ocuparem a linha toda."""
    return min(12, max(3, (field["size"] + 7) // 8 + 2))


def is_date_field(field):
    description = field.get("desc", "").upper()
    label = field.get("label", "").upper()
    return "AAAAMMDD" in description or "YYYYMMDD" in description or label.startswith("DATA ")


def display_value(field):
    value = field["value"]
    if not is_date_field(field) or not value:
        return value
    if len(value) == 8 and value.isdigit():
        try:
            return datetime.strptime(value, "%Y%m%d").strftime("%d/%m/%Y")
        except ValueError:
            pass
    return value


def export_value(field, value):
    if not is_date_field(field) or not value.strip():
        return value
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").strftime("%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field['label']}: informe uma data válida no formato DD/MM/AAAA.") from exc


def render_record(record, title=None):
    if title:
        st.markdown(f"### {title}")
    fields = record["fields"]
    for start in range(0, len(fields), 3):
        row = fields[start:start + 3]
        columns = st.columns([field_width(field) for field in row])
        for column, field in zip(columns, row):
            key = f"field_{record['index']}_{field['key']}"
            with column:
                st.text_input(
                    field["label"],
                    value=display_value(field),
                    max_chars=field["size"],
                    disabled=field["read_only"],
                    help=field["desc"] or f"Tamanho: {field['size']}",
                    key=key,
                )


def collect_changes(detail):
    changes = {}
    for record in detail["records"]:
        for field in record["fields"]:
            key = f"field_{record['index']}_{field['key']}"
            shown = display_value(field)
            value = st.session_state.get(key, shown)
            exported = field["value"] if value == shown else export_value(field, value)
            if exported != field["value"]:
                changes.setdefault(str(record["index"]), {})[field["key"]] = exported
    return changes


uploaded_file = st.file_uploader("Abrir arquivo APAC", type=None)
if uploaded_file is None:
    st.info("Selecione um arquivo APAC para comecar.")
    st.stop()

try:
    editor = load_file(uploaded_file)
    state = editor.state()
except (OSError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

rows = state["apacs"]
query = st.sidebar.text_input("Pesquisar APAC ou paciente", placeholder="Numero, nome ou CNES")
filtered = [
    row for row in rows
    if normalize(query) in normalize(f"{row['number']} {row['patient']} {row['cnes']} {row['competence']}")
]
st.sidebar.subheader(f"APACs do arquivo ({len(rows)})")
if not filtered:
    st.sidebar.info("Nenhuma APAC encontrada.")
    st.stop()

labels = {row["index"]: f"{row['patient'] or row['number']} | {row['number']}" for row in filtered}
current = st.session_state.get("selected_index", filtered[0]["index"])
if current not in labels:
    current = filtered[0]["index"]
selected = st.sidebar.radio("Registros", [row["index"] for row in filtered], index=[row["index"] for row in filtered].index(current), format_func=labels.get)
st.session_state.selected_index = selected

detail = editor.detail(selected)
row = next(item for item in rows if item["index"] == selected)
position = next(index for index, item in enumerate(rows) if item["index"] == selected)
st.markdown(
    f"<div class='record-title'><small>APAC {position + 1} de {len(rows)}</small>"
    f"<h2>{row['patient'] or 'Dados da APAC'}</h2><p>Numero {row['number']} | Competencia {row['competence'][4:]}/{row['competence'][:4]}</p></div>",
    unsafe_allow_html=True,
)

previous, next_record, save, download = st.columns([1, 1, 2, 2])
with previous:
    if st.button("Anterior", disabled=position == 0, use_container_width=True):
        st.session_state.selected_index = rows[position - 1]["index"]
        st.rerun()
with next_record:
    if st.button("Proxima", disabled=position == len(rows) - 1, use_container_width=True):
        st.session_state.selected_index = rows[position + 1]["index"]
        st.rerun()

body_records = [record for record in detail["records"] if record["type"] == "14"]
variable_records = [record for record in detail["records"] if record["type"] not in {"01", "13", "14"}]
procedure_records = [record for record in detail["records"] if record["type"] == "13"]

with st.container(border=True):
    st.markdown("### Dados da APAC")
    for record in body_records:
        render_record(record)

with st.container(border=True):
    st.markdown("### Dados complementares")
    if variable_records:
        for record in variable_records:
            render_record(record, record["title"])
    else:
        st.caption("Esta APAC nao possui dados complementares.")

with st.container(border=True):
    st.markdown(f"### Procedimentos ({len(procedure_records)})")
    if procedure_records:
        for number, record in enumerate(procedure_records, 1):
            st.markdown(f"**Procedimento {number}**  {record['description'] or 'Descricao nao encontrada'}")
            render_record(record)
    else:
        st.caption("Esta APAC nao possui procedimentos.")

with save:
    if st.button("Salvar alteracoes", type="primary", use_container_width=True):
        try:
            editor.save({"version": state["version"], "body_index": selected, "changes": collect_changes(detail)})
            st.success("Arquivo salvo com sucesso.")
            st.rerun()
        except (OSError, ValueError) as exc:
            st.error(str(exc))

with download:
    content = Path(editor.file.path).read_bytes()
    st.download_button("Baixar arquivo atualizado", content, file_name=st.session_state.file_name, mime="application/octet-stream", use_container_width=True)

st.caption(editor.table_status)
