"""Relatórios HTML locais e somente para leitura, sem dependências externas."""
from __future__ import annotations

import csv
from datetime import datetime
from html import escape
from pathlib import Path
import tempfile

from sigtap_tables import ProcedureCatalog


TITLE = "Dados para digitação da APAC"
MISSING = ""
UNAVAILABLE = ""

CSS = """
:root{font-family:Segoe UI,Arial,sans-serif;color:#172b46;background:#edf2f8;font-size:15px}
*{box-sizing:border-box}body{margin:0}header{background:#123f82;color:white;padding:24px max(24px,calc((100% - 1280px)/2))}
header p{margin:6px 0;opacity:.88}h1{font-size:25px;margin:0 0 10px}h2{font-size:18px;color:#123f82;margin:0 0 18px}
main{max-width:1328px;margin:auto;padding:24px}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:20px}
a{color:#174e9b}a.button,button{display:inline-block;background:white;border:1px solid #aabdd6;color:#123f82;border-radius:6px;padding:10px 16px;text-decoration:none;font:inherit;cursor:pointer}
a.button:hover,button:hover{background:#e3edfa}a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #e79816;outline-offset:3px}
.badge{display:inline-block;background:#dceaff;color:#123f82;border-radius:4px;padding:5px 10px;font-size:13px;font-weight:600}
section{background:white;border:1px solid #d4dfec;border-radius:8px;padding:24px;margin-bottom:20px}
dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px 28px;margin:0}dl div{min-width:0}
dt{font-size:12px;color:#556982;margin-bottom:5px;text-transform:uppercase;letter-spacing:.035em}dd{margin:0;font-weight:600;white-space:pre-wrap;overflow-wrap:anywhere}
.muted{color:#64748b;font-weight:400}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:11px 12px;border-bottom:1px solid #dce4ef;vertical-align:top}th{background:#eff4fb;color:#274b78;font-size:12px}
tbody tr:nth-child(even){background:#f8fafd}td.code{white-space:nowrap;font-variant-numeric:tabular-nums}
.note{font-size:13px;color:#586d86;line-height:1.6}.summary{font-size:18px}.search{width:min(600px,100%);padding:12px;border:1px solid #aabdd6;border-radius:6px;font:inherit}
footer{font-size:12px;color:#64748b;padding:0 24px 24px;text-align:center}.empty{padding:20px;color:#64748b}
@media(max-width:760px){dl{grid-template-columns:repeat(2,minmax(0,1fr))}main{padding:12px}section{padding:16px}header{padding:20px}}
@media(max-width:460px){dl{grid-template-columns:1fr}}
@media print{@page{size:A4 landscape;margin:12mm}:root{background:white;font-size:11px}header{background:white;color:#123f82;padding:0 0 14px;border-bottom:2px solid #123f82}main{padding:12px 0}.toolbar,.no-print{display:none!important}section{padding:12px;margin-bottom:12px;border-radius:0}h1{font-size:20px}h2{font-size:15px}dl{gap:12px}dl div,tr{break-inside:avoid}table{font-size:10px}th,td{padding:7px 5px}.table-scroll{overflow:visible}thead{display:table-header-group}footer{padding:12px}}
"""


def text(value):
    return escape(str(value), quote=True)


def values(line, fields):
    return {field.key: line[field.start - 1:field.end].strip() for field in fields}


def date(value):
    if not value or value == "00000000":
        return MISSING
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def competence(value):
    if len(value) == 6 and value.isdigit() and 1 <= int(value[4:]) <= 12:
        return f"{value[4:]}/{value[:4]}"
    return value or MISSING


def load_descriptions(path):
    """CSV opcional: codigo;descricao. Códigos nunca são convertidos em números."""
    raw = Path(path).read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252")
    if not content.strip():
        raise ValueError("A tabela está vazia.")
    delimiter = ";" if ";" in content.splitlines()[0] else ","
    reader = csv.DictReader(content.splitlines(), delimiter=delimiter)
    if not reader.fieldnames or not {"codigo", "descricao"} <= set(reader.fieldnames):
        raise ValueError("A tabela deve ter as colunas codigo e descricao.")
    result = {}
    for row in reader:
        code = "".join(c for c in (row.get("codigo") or "") if c.isdigit())
        description = (row.get("descricao") or "").strip()
        if len(code) != 10 or not description:
            raise ValueError("Cada procedimento deve ter código de 10 dígitos e descrição.")
        result[code] = description
    if not result:
        raise ValueError("A tabela não contém procedimentos.")
    return result


def fields_section(title, pairs):
    cells = []
    for label, value in pairs:
        value = value or MISSING
        css = ' class="muted"' if value in (MISSING, UNAVAILABLE) else ""
        cells.append(f"<div><dt>{text(label)}</dt><dd{css}>{text(value)}</dd></div>")
    return f"<section><h2>{text(title)}</h2><dl>{''.join(cells)}</dl></section>"


def table(headers, rows):
    head = "".join(f'<th scope="col">{text(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{text(v or MISSING)}</td>" for v in row) + "</tr>" for row in rows)
    if not body:
        body = f'<tr><td colspan="{len(headers)}"></td></tr>'
    return f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def document(subtitle, content, source):
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{text(TITLE)} — {text(subtitle)}</title><style>{CSS}</style></head>
<body><header><h1>{TITLE}</h1><p>{text(subtitle)}</p><span class="badge">Somente leitura</span></header>
<main>{content}</main><footer>Arquivo: {text(source)} · Consulta gerada em {datetime.now():%d/%m/%Y %H:%M} · Os dados desta consulta não alteram o arquivo APAC.</footer></body></html>'''


def generate_report(apac_file, body_fields, proc_fields, variable_layouts, descriptions=None, output_dir=None):
    """Uma página por registro 14; relações por competência e número da APAC."""
    descriptions = descriptions or {}
    directory = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="consulta_apac_"))
    directory.mkdir(parents=True, exist_ok=True)
    bodies = []
    related = {}
    for line_number, line in enumerate(apac_file.lines, 1):
        if len(line) < 21:
            continue
        key = (line[2:8], line[8:21])
        if line[:2] == "14":
            bodies.append((line_number, line, key))
        elif line[:2] == "13" or line[:2] in variable_layouts:
            related.setdefault(key, []).append(line)
    if not bodies:
        raise ValueError("O arquivo não possui registros de APAC para visualizar.")
    links = []
    pages = []
    for index, (line_number, line, key) in enumerate(bodies):
        b = values(line, body_fields)
        get = lambda name: b.get(name, "")
        filename = f"apac_{index + 1:06d}.html"
        pages.append((key[1], directory / filename))
        navigation = '<a class="button" href="index.html">Todas as APACs</a>'
        if index:
            navigation += f'<a class="button" href="apac_{index:06d}.html">Anterior</a>'
        if index + 1 < len(bodies):
            navigation += f'<a class="button" href="apac_{index + 2:06d}.html">Próxima</a>'
        navigation += f'<span>{index + 1} de {len(bodies)}</span><button type="button" onclick="window.print()">Imprimir / Salvar PDF</button>'
        content = f'<nav class="toolbar" aria-label="Navegação entre APACs">{navigation}</nav>'
        apac_type = {"1": "1 — Inicial", "2": "2 — Continuidade", "3": "3 — Única", "4": "4 — Encerramento"}.get(get("apa_tipapac"), get("apa_tipapac"))
        content += fields_section("Identificação da unidade / APAC", [
            ("Número da APAC", get("apa_num")), ("Competência", competence(get("apa_cmp"))),
            ("APAC anterior", get("apa_apacant")), ("CNES solicitante", get("apa_codsol")),
            ("CNES executante", get("apa_codcnes")), ("Nome do estabelecimento", UNAVAILABLE),
            ("Início da validade", date(get("apa_dtiinval"))), ("Fim da validade", date(get("apa_dtfimval"))),
            ("Tipo de APAC", apac_type),
        ])
        content += fields_section("Identificação do usuário", [
            ("Nome", get("apa_nomepcnte")), ("Nome da mãe", get("apa_nomemae")),
            ("Responsável pelo paciente", get("apa_nomeresp_pac")), ("CPF", get("apa_cpfpcnte")),
            ("CNS", get("apa_cnspct")), ("Prontuário", get("apa_npront")),
            ("Nacionalidade (código)", get("apa_nascpcnte")), ("Sem CPF / Registro Civil", get("apa_semcpf")),
            ("Situação de rua", get("apa_strua")), ("CEP", get("apa_ceppcnte")),
            ("Tipo de logradouro (código)", get("apa_cdlogr")), ("Endereço / logradouro", get("apa_logpcnte")),
            ("Número", get("apa_numpcnte")), ("Complemento", get("apa_cplpcnte")), ("Bairro", get("apa_bairro")),
            ("Telefone com DDD", " ".join(filter(None, [get("apa_dddtelcontato"), get("apa_telcontato")]))),
            ("E-mail", get("apa_email")), ("Município (código do arquivo)", get("apa_munpcnte")),
            ("Município (nome)", UNAVAILABLE), ("Raça/cor (código)", get("apa_raca")),
            ("Data de nascimento", date(get("apa_datanascim"))), ("Sexo", get("apa_sexopcnte")),
            ("Etnia (código)", get("apa_etnia")),
        ])
        records = related.get(key, [])
        procs = [values(record, proc_fields) for record in records if record.startswith("13")]
        content += '<section><h2>Procedimentos realizados</h2>'
        description = lambda code: (descriptions.description(code, key[0]) if isinstance(descriptions, ProcedureCatalog)
                                     else descriptions.get(code, ""))
        content += table(["#", "Procedimento", "Descrição", "CBO", "Quantidade", "CID principal", "CID secundário"], [
            (n, p["pap_codproc"], description(p["pap_codproc"]),
             p["pap_cbo"], p["pap_qtdprod"], p["pap_CIDP"], p["pap_CIDS"])
            for n, p in enumerate(procs, 1)
        ])
        content += '<h2 style="margin-top:24px">Informações adicionais dos procedimentos</h2>'
        content += table(["#", "Procedimento", "CNPJ", "Nota fiscal", "Serviço", "Classificação", "CNES terceiro"], [
            (n, p["pap_codproc"], p["pap_CGC"], p["pap_NF"], p["pap_SRV"], p["pap_CLF"], p["pap_cnes_terc"])
            for n, p in enumerate(procs, 1)
        ])
        if isinstance(descriptions, ProcedureCatalog):
            reference = descriptions.reference_competence(key[0])
            table_note = f"Descrições: SIGTAP {competence(reference)}."
            if reference != key[0]:
                table_note += f" A tabela da competência da APAC ({competence(key[0])}) não foi carregada; os nomes exibidos usam a referência disponível indicada acima."
        else:
            table_note = "As descrições dependem da tabela de procedimentos importada."
        content += f'<p class="note">{text(table_note)} Os códigos e quantidades são exibidos como constam no arquivo.</p></section>'
        content += fields_section("Saída / permanência", [
            ("Motivo de saída / permanência (código)", get("apa_motsaida")),
            ("Data de alta / óbito / transferência / mudança de procedimento", date(get("apa_dtobitoalta"))),
        ])
        variables = [record for record in records if record[:2] in variable_layouts]
        for record in variables:
            name, schema = variable_layouts[record[:2]]
            v = values(record, schema)
            content += fields_section(f"Dados complementares — {name} ({record[:2]})", [
                (field.label, date(v[field.key]) if "AAAAMMDD" in field.desc or "YYYYMMDD" in field.desc else v[field.key])
                for field in schema if field.key not in {"apa_varia", "apa_cmp", "apa_num"}
            ])
        if not variables:
            content += '<section><h2>Dados complementares</h2></section>'
        content += fields_section("Solicitação / autorização", [
            ("Caráter do atendimento (código)", get("apa_carate")),
            ("Médico responsável", get("apa_nomeresp_med")), ("CNS do médico responsável", get("apa_cnsres")),
            ("CPF do médico responsável", UNAVAILABLE), ("Data da solicitação", date(get("apa_datsol"))),
            ("Profissional autorizador", get("apa_nomediretor")), ("CNS do autorizador", get("apa_cnsdir")),
            ("CPF do autorizador", UNAVAILABLE), ("Data da autorização", date(get("apa_dataut"))),
            ("Código do órgão emissor", get("apa_codemis")),
        ])
        subtitle = f'APAC {get("apa_num")} · {get("apa_nomepcnte")} · {competence(get("apa_cmp"))}'
        (directory / filename).write_text(document(subtitle, content, apac_file.path.name), encoding="utf-8")
        links.append(f'<tr><td>{index + 1}</td><td><a href="{filename}">{text(get("apa_num"))}</a></td><td>{text(get("apa_nomepcnte") or MISSING)}</td><td>{text(competence(get("apa_cmp")))}</td><td>{text(get("apa_codcnes"))}</td><td><a href="{filename}">Visualizar ficha</a></td></tr>')
    index_content = f'''<section><h2>Todas as APACs</h2><p class="summary">{len(bodies)} APAC(s) no arquivo</p>
<label for="search">Pesquisar por número, paciente, competência ou CNES</label><p><input class="search" id="search" type="search" placeholder="Digite para localizar uma APAC" autocomplete="off"></p>
<p id="count" role="status">{len(bodies)} APAC(s) exibida(s)</p><div class="table-scroll"><table>
<thead><tr><th>#</th><th>Número da APAC</th><th>Paciente</th><th>Competência</th><th>CNES executante</th><th>Consulta</th></tr></thead>
<tbody id="apacs">{''.join(links)}</tbody></table></div><p id="empty" hidden>Nenhuma APAC encontrada.</p></section>
<script>
const normalize = value => value.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
const rows = Array.from(document.querySelectorAll('#apacs tr'));
document.getElementById('search').addEventListener('input', event => {{
  const query = normalize(event.target.value).trim(); let count = 0;
  rows.forEach(row => {{row.hidden = !normalize(row.textContent).includes(query); if (!row.hidden) count++;}});
  document.getElementById('count').textContent = count + ' APAC(s) exibida(s)';
  document.getElementById('empty').hidden = count !== 0;
}});
</script>'''
    index_path = directory / "index.html"
    index_path.write_text(document("Consulta de todas as APACs do arquivo", index_content, apac_file.path.name), encoding="utf-8")
    return index_path, pages
