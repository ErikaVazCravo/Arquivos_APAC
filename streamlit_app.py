from __future__ import annotations

import hashlib
from html import escape
from datetime import datetime
from pathlib import Path
import tempfile

import streamlit as st

from apac_web import WebEditor


st.set_page_config(page_title="Editor APAC", page_icon="A", layout="wide")

st.markdown(
    """
    <style>
    :root { --apac-ink: #203d32; --apac-green: #216347; --apac-line: #d8e7de; --apac-muted: #506d5e; }
    [data-testid="stAppViewContainer"] { background: #f2f7f3; color: var(--apac-ink); }
    .block-container { padding: 5.5rem 2rem 3rem; max-width: 1380px; }
    .apac-header { background: linear-gradient(120deg, #174b38, #287657); color: white; padding: 1.8rem 2rem; border: 1px solid #ffffff20; border-radius: 20px; margin-bottom: 1.5rem; box-shadow: 0 10px 30px #174b3814; }
    .apac-header h1 { color: white; margin: .5rem 0 0; padding: 0; font-size: 1.9rem; font-weight: 700; letter-spacing: -.04em; line-height: 1.3; }
    .apac-eyebrow { display: inline-block; border: 1px solid #ffffff40; background: #ffffff12; padding: .25rem .65rem; border-radius: 20px; color: #e0f1e6; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; }
    .apac-header p { margin: .4rem 0 0; color: #e0f1e6; font-size: .9rem; }
    .record-title { padding: .5rem 0 1rem; margin-bottom: .5rem; }
    .record-title h2 { color: var(--apac-ink); margin: .25rem 0; padding: 0; font-size: 1.6rem; }
    .record-title p, .record-title small { color: var(--apac-muted); }
    [data-testid="stSidebar"] { background: #e8f2eb; border-right: 1px solid var(--apac-line); }
    [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: var(--apac-green); }
    [data-testid="stVerticalBlockBorderWrapper"] > div { border-color: var(--apac-line) !important; border-radius: 12px; }
    [data-testid="stVerticalBlockBorderWrapper"] { background: white; border-radius: 12px; box-shadow: 0 3px 16px #203d3206; }
    h3 { color: var(--apac-green); font-size: 1.1rem !important; }
    .readonly-value { min-height: 4.1rem; padding: .65rem .8rem; background: #f4f8f5; border: 1px solid #dfeae2; border-radius: 7px; margin-bottom: .25rem; }
    .readonly-label { color: var(--apac-muted); font-size: .78rem; margin-bottom: .25rem; }
    .readonly-text { color: var(--apac-ink); font-size: .95rem; font-weight: 600; overflow-wrap: anywhere; white-space: pre-wrap; }
    [data-testid="stTextInput"] input { background: #f7faf8; color: #203d32; }
    [data-testid="stWidgetLabel"] p { color: #506d5e; }
    [data-testid="stDataFrame"] { border: 1px solid var(--apac-line); border-radius: 8px; overflow: hidden; }
    button[kind="primary"] { background-color: #216347; border-color: #216347; color: white; }
    button[kind="primary"]:hover { background-color: #174e37; border-color: #174e37; color: white; }
    .apac-welcome { background: white; border: 1px solid var(--apac-line); border-radius: 18px; padding: 2rem; box-shadow: 0 6px 24px #203d3206; }
    .apac-welcome-icon { display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; background: #e8f2eb; color: #216347; border-radius: 14px; margin-bottom: 1rem; }
    .apac-welcome h2 { color: #203d32; font-size: 1.25rem; padding: 0; margin: 0 0 .5rem; }
    .apac-welcome p { color: #506d5e; margin: 0; line-height: 1.7; }
    .apac-notice { background: #e8f2eb; border-left: 3px solid #287657; border-radius: 8px; color: #216347; padding: .9rem 1rem; margin-top: 1.5rem; }
    @media (max-width: 700px) { .block-container { padding: 5rem .75rem 2rem; } .apac-header, .apac-welcome { padding: 1.25rem; } }
    </style>
    <div class="apac-header"><span class="apac-eyebrow">Gestão de arquivos APAC</span><h1>Editor APAC</h1><p>Consulte, organize e edite os dados em um só lugar.</p></div>
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

    clear_edit_fields()
    st.session_state.editing_procedures = False
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


def clear_edit_fields():
    for key in list(st.session_state):
        if key.startswith("field_"):
            del st.session_state[key]


def navigate(index):
    clear_edit_fields()
    st.session_state.editing_procedures = False
    st.session_state.selected_index = index
    st.rerun()


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


def render_readonly_record(record, title=None, fields=None):
    if title:
        st.markdown(f"### {title}")
    fields = fields if fields is not None else record["fields"]
    for start in range(0, len(fields), 3):
        row = fields[start:start + 3]
        columns = st.columns(3)
        for column, field in zip(columns, row):
            with column:
                st.markdown(
                    f"<div class='readonly-value'><div class='readonly-label'>{escape(field['label'])}</div>"
                    f"<div class='readonly-text'>{escape(display_value(field) or '—')}</div></div>",
                    unsafe_allow_html=True,
                )


def render_editable_record(record, title=None, fields=None):
    if title:
        st.markdown(f"### {title}")
    fields = fields if fields is not None else record["fields"]
    for start in range(0, len(fields), 3):
        row = fields[start:start + 3]
        columns = st.columns(3)
        for column, field in zip(columns, row):
            with column:
                st.text_input(
                    field["label"],
                    value=display_value(field),
                    max_chars=10 if is_date_field(field) else field["size"],
                    disabled=field["read_only"],
                    help=field["desc"] or f"Tamanho: {field['size']}",
                    key=f"field_{record['index']}_{field['key']}",
                )


def render_field_group(record, title, keys, editing):
    by_key = {field["key"]: field for field in record["fields"]}
    selected = [by_key[key] for key in keys if key in by_key]
    if not selected:
        return set()
    if editing:
        render_editable_record(record, title, selected)
    else:
        render_readonly_record(record, title, selected)
    return {field["key"] for field in selected}


def render_procedure_table(records):
    if not records:
        st.caption("Esta APAC não possui procedimentos.")
        return
    table = []
    for number, record in enumerate(records, 1):
        values = {field["key"]: display_value(field) for field in record["fields"]}
        table.append({
            "#": number,
            "Procedimento": values.get("pap_codproc", ""),
            "Descrição": record["description"],
            "CBO": values.get("pap_cbo", ""),
            "Qtd.": values.get("pap_qtdprod", ""),
            "CNS executante": values.get("pap_cns_terc", ""),
            "CNES terceiro": values.get("pap_cnes_terc", ""),
        })
    st.dataframe(table, hide_index=True, use_container_width=True)


def collect_changes(detail):
    changes = {}
    for record in detail["records"]:
        if record["type"] == "01":
            continue
        for field in record["fields"]:
            key = f"field_{record['index']}_{field['key']}"
            shown = display_value(field)
            value = st.session_state.get(key, shown)
            exported = field["value"] if value == shown else export_value(field, value)
            if exported != field["value"]:
                changes.setdefault(str(record["index"]), {})[field["key"]] = exported
    return changes


st.sidebar.title("Pacientes e APACs")
uploaded_file = st.sidebar.file_uploader("Abrir arquivo APAC", type=None)
if uploaded_file is None:
    st.markdown(
        """
        <div class="apac-welcome">
            <div class="apac-welcome-icon" aria-hidden="true">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <path d="M14 2v6h6M8 13h8M8 17h5"/>
                </svg>
            </div>
            <h2>Seu arquivo, pronto para editar</h2>
            <p>Abra um arquivo na barra lateral para consultar os pacientes,<br>
            conferir os procedimentos e atualizar os dados da APAC.</p>
            <div class="apac-notice">Selecione um arquivo APAC para começar.</div>
            <p style="margin-top: 1rem; font-size: .9rem;">Essa plataforma não armazena permanentemente os dados das APACs e das alterações.<br>
            Após baixar o arquivo corrigido, ele precisa ser consistido no APAC Magnético.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

try:
    editor = load_file(uploaded_file)
    state = editor.state()
except (OSError, ValueError) as exc:
    st.error(str(exc))
    st.stop()

if st.session_state.pop("saved_notice", False):
    st.success("Alterações salvas. Baixe o arquivo atualizado para guardar uma cópia no computador.")

rows = state["apacs"]
query = st.sidebar.text_input("Pesquisar APAC ou paciente", placeholder="Número, nome ou CNES")
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
if selected != st.session_state.get("selected_index"):
    clear_edit_fields()
    st.session_state.editing_procedures = False
st.session_state.selected_index = selected

detail = editor.detail(selected)
row = next(item for item in rows if item["index"] == selected)
position = next(index for index, item in enumerate(rows) if item["index"] == selected)
st.markdown(
    f"<div class='record-title'><small>APAC {position + 1} de {len(rows)}</small>"
    f"<h2>{escape(row['patient'] or 'Dados da APAC')}</h2><p>Número {escape(row['number'])} | Competência {row['competence'][4:]}/{row['competence'][:4]}</p></div>",
    unsafe_allow_html=True,
)

st.caption(f"Arquivo: {st.session_state.file_name} | CNES: {row['cnes']} | {len([r for r in detail['records'] if r['type'] == '13'])} procedimentos")
first, previous, next_record, last = st.columns(4)
with first:
    if st.button("Primeira", disabled=position == 0, use_container_width=True):
        navigate(rows[0]["index"])
with last:
    if st.button("Última", disabled=position == len(rows) - 1, use_container_width=True):
        navigate(rows[-1]["index"])
edit, save, download = st.columns([1, 1, 1.5])
with previous:
    if st.button("Anterior", disabled=position == 0, use_container_width=True):
        navigate(rows[position - 1]["index"])
with next_record:
    if st.button("Próxima", disabled=position == len(rows) - 1, use_container_width=True):
        navigate(rows[position + 1]["index"])

editing = st.session_state.get("editing_procedures", False)
with edit:
    if st.button("Cancelar edição" if editing else "Editar APAC", type="primary", use_container_width=True):
        clear_edit_fields()
        st.session_state.editing_procedures = not editing
        st.rerun()

st.caption("Edição ativa: salve para aplicar as alterações. O cabeçalho permanece somente para consulta." if editing else "Consulta: clique em Editar APAC para alterar os campos.")

body_records = [record for record in detail["records"] if record["type"] == "14"]
variable_records = [record for record in detail["records"] if record["type"] not in {"01", "13", "14"}]
procedure_records = [record for record in detail["records"] if record["type"] == "13"]

body = body_records[0] if body_records else None
used = set()

with st.container(border=True):
    if body:
        used |= render_field_group(body, "Identificação do usuário", [
            "apa_nomepcnte", "apa_nomemae", "apa_nomeresp_pac",
            "apa_cnspct", "apa_cpfpcnte", "apa_datanascim",
            "apa_sexopcnte", "apa_raca", "apa_etnia",
            "apa_nascpcnte", "apa_semcpf", "apa_strua",
        ], editing)

with st.container(border=True):
    if body:
        used |= render_field_group(body, "Endereço e contato", [
            "apa_ceppcnte", "apa_logpcnte", "apa_numpcnte", "apa_cplpcnte", "apa_bairro",
            "apa_munpcnte", "apa_telcontato", "apa_email", "apa_dddtelcontato",
        ], editing)

with st.container(border=True):
    st.markdown(f"### Procedimentos ({len(procedure_records)})")
    st.caption("Modo de edição ativo." if editing else "Somente visualização. Use Editar APAC para alterar os dados.")
    if procedure_records:
        render_procedure_table(procedure_records)
        if editing:
            for number, record in enumerate(procedure_records, 1):
                render_editable_record(record, f"Editar procedimento {number}")
    else:
        st.caption("Esta APAC não possui procedimentos.")

with st.container(border=True):
    st.markdown("### Dados complementares")
    if variable_records:
        for record in variable_records:
            if editing:
                render_editable_record(record, record["title"])
            else:
                render_readonly_record(record, record["title"])
    else:
        st.caption("Esta APAC não possui dados complementares.")

with st.container(border=True):
    if body:
        used |= render_field_group(body, "Identificação da APAC", [
            "apa_num", "apa_cmp", "apa_apacant", "apa_codsol", "apa_codcnes", "apa_dtiinval",
            "apa_dtfimval", "apa_tipapac", "apa_motsaida", "apa_dtobitoalta",
        ], editing)

with st.container(border=True):
    if body:
        used |= render_field_group(body, "Solicitação e autorização", [
            "apa_carate", "apa_nomeresp_med", "apa_cnsres", "apa_datsol", "apa_nomediretor",
            "apa_cnsdir", "apa_dataut", "apa_codemis",
        ], editing)

with st.container(border=True):
    if body:
        remaining = [field for field in body["fields"] if field["key"] not in used and field["key"] not in {"apa_corpo"}]
        if remaining:
            if editing:
                render_editable_record(body, "Outras informações", remaining)
            else:
                render_readonly_record(body, "Outras informações", remaining)

header_records = [record for record in detail["records"] if record["type"] == "01"]
if header_records:
    with st.container(border=True):
        st.markdown("### Cabeçalho do arquivo")
        st.caption("Somente consulta. Quantidade e campo de controle são recalculados automaticamente ao salvar.")
        for record in header_records:
            render_readonly_record(record)

with save:
    if st.session_state.get("editing_procedures", False) and st.button("Salvar alterações", type="primary", use_container_width=True):
        try:
            editor.save({"version": state["version"], "body_index": selected, "changes": collect_changes(detail)})
            st.session_state.editing_procedures = False
            clear_edit_fields()
            st.session_state.saved_notice = True
            st.rerun()
        except (OSError, ValueError) as exc:
            st.error(str(exc))

with download:
    content = Path(editor.file.path).read_bytes()
    st.download_button("Baixar arquivo atualizado", content, file_name=st.session_state.file_name, mime="application/octet-stream", use_container_width=True)

st.caption(editor.table_status)
