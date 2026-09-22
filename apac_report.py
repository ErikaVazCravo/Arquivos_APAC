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
:root{font-family:"Aptos","Segoe UI",Arial,sans-serif;color:#26364d;background:#f4f7fb;font-size:14px;line-height:1.45;--ink:#26364d;--navy:#193b63;--blue:#2e628f;--muted:#708096;--line:#dce4ed;--soft:#f7f9fc}
*{box-sizing:border-box}body{margin:0}header{background:linear-gradient(135deg,#183b63,#285b82);color:white;padding:28px max(24px,calc((100% - 1280px)/2));box-shadow:0 2px 12px #183b6326}
header p{margin:7px 0 12px;color:#dbe9f5;letter-spacing:.01em}h1{font-size:26px;letter-spacing:-.02em;margin:0 0 4px}h2{font-size:18px;line-height:1.2;color:var(--navy);letter-spacing:-.01em;margin:0 0 18px}
main{max-width:1328px;margin:auto;padding:26px 24px 12px}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:22px}
a{color:#245d8c}a.button,button{display:inline-block;background:white;border:1px solid #c5d2df;color:var(--navy);border-radius:7px;padding:9px 14px;text-decoration:none;font:inherit;cursor:pointer;box-shadow:0 1px 2px #193b630d}
a.button:hover,button:hover{background:#f0f6fb;border-color:#91aec7;transform:translateY(-1px)}a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #e9ad4b;outline-offset:3px}
.badge{display:inline-block;background:#e5f0f8;color:#1e527c;border-radius:999px;padding:5px 11px;font-size:12px;font-weight:700;letter-spacing:.02em}
section{background:white;border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin-bottom:18px;box-shadow:0 2px 8px #193b6308}
dl{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0 28px;margin:0}dl div{min-width:0;padding:0 0 15px;margin-bottom:15px;border-bottom:1px solid #edf1f5}
dt{font-size:11px;color:var(--muted);margin-bottom:4px;letter-spacing:.01em}dd{margin:0;color:var(--ink);font-weight:600;white-space:pre-wrap;overflow-wrap:anywhere}
.muted{color:#a0aab7;font-weight:400}.table-scroll{overflow:auto}table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{text-align:left;padding:11px 12px;border-bottom:1px solid #e7edf3;vertical-align:top}th{background:#f2f6fa;color:#506b86;font-size:11px;font-weight:700;letter-spacing:.02em}tbody tr:last-child td{border-bottom:0}
tbody tr:nth-child(even){background:#fbfcfe}tbody tr:hover{background:#f3f8fc}td.code{white-space:nowrap;font-variant-numeric:tabular-nums}
.note{font-size:12px;color:#718096;line-height:1.6;margin:16px 0 0}.summary{font-size:18px;color:var(--navy)}.search{width:min(600px,100%);padding:11px 12px;border:1px solid #c5d2df;border-radius:7px;font:inherit;background:white}
footer{font-size:11px;color:#7b899b;padding:4px 24px 24px;text-align:center}.empty{padding:20px;color:#718096}
@media(max-width:760px){dl{grid-template-columns:repeat(2,minmax(0,1fr))}main{padding:16px 12px 8px}section{padding:18px 16px}header{padding:22px 18px}h1{font-size:23px}}
@media(max-width:460px){dl{grid-template-columns:1fr}section{border-radius:8px}table{font-size:12px}th,td{padding:9px 8px}}
@media print{@page{size:A4 landscape;margin:12mm}:root{background:white;font-size:11px}header{background:white;color:var(--navy);padding:0 0 14px;border-bottom:2px solid var(--navy);box-shadow:none}header p{color:var(--muted)}main{padding:12px 0}.toolbar,.no-print{display:none!important}section{padding:12px;margin-bottom:12px;border-radius:0;box-shadow:none}h1{font-size:20px}h2{font-size:15px}dl{gap:0 18px}dl div{padding-bottom:8px;margin-bottom:8px}dl div,tr{break-inside:avoid}table{font-size:10px;box-shadow:none}th,td{padding:7px 5px}.table-scroll{overflow:visible}thead{display:table-header-group}footer{padding:12px}}
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


def fields_content(title, pairs):
    cells = []
    for label, value in pairs:
        value = value or MISSING
        css = ' class="muted"' if value in (MISSING, UNAVAILABLE) else ""
        cells.append(f"<div><dt>{text(label)}</dt><dd{css}>{text(value)}</dd></div>")
    return f'<h2 style="margin-top:24px">{text(title)}</h2><dl>{"".join(cells)}</dl>'


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
        content += fields_section("Identificação do usuário", [
            ("Nome do paciente", get("apa_nomepcnte")), ("Nome da mãe", get("apa_nomemae")),
            ("Data de nascimento", date(get("apa_datanascim"))), ("CNS do paciente", get("apa_cnspct")),
            ("Raça/Cor", get("apa_raca")), ("Responsável pelo paciente", get("apa_nomeresp_pac")),
            ("Nacionalidade", get("apa_nascpcnte")), ("Etnia", get("apa_etnia")),
            ("CPF do paciente", get("apa_cpfpcnte")), ("Pessoa em situação de rua", get("apa_strua")),
            ("Pessoa sem CPF/Registro Civil", get("apa_semcpf")),
        ])
        content += fields_section("Endereço e contato", [
            ("Logradouro", get("apa_logpcnte")), ("Número do endereço", get("apa_numpcnte")),
            ("Complemento", get("apa_cplpcnte")), ("CEP", get("apa_ceppcnte")),
            ("Município (IBGE)", get("apa_munpcnte")), ("Bairro", get("apa_bairro")),
            ("Telefone", get("apa_telcontato")), ("E-mail", get("apa_email")),
            ("DDD", get("apa_dddtelcontato")),
        ])
        records = related.get(key, [])
        procs = [values(record, proc_fields) for record in records if record.startswith("13")]
        content += '<section><h2>Procedimentos</h2>'
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
        variables = [record for record in records if record[:2] in variable_layouts]
        content += '<section><h2>Dados complementares</h2>'
        for record in variables:
            name, schema = variable_layouts[record[:2]]
            v = values(record, schema)
            content += fields_content(name, [
                (field.label, date(v[field.key]) if "AAAAMMDD" in field.desc or "YYYYMMDD" in field.desc else v[field.key])
                for field in schema if field.key not in {"apa_varia", "apa_cmp", "apa_num"}
            ])
        content += '</section>'
        content += fields_section("Identificação da APAC", [
            ("Número da APAC", get("apa_num")), ("CNES executante", get("apa_codcnes")),
            ("Início da validade", date(get("apa_dtiinval"))), ("Fim da validade", date(get("apa_dtfimval"))),
            ("Tipo de APAC", apac_type), ("Motivo saída/permanência", get("apa_motsaida")),
            ("Data alta/transf./óbito", date(get("apa_dtobitoalta"))), ("CNES solicitante", get("apa_codsol")),
            ("APAC anterior", get("apa_apacant")),
        ])
        content += fields_section("Solicitação e autorização", [
            ("Caráter do atendimento (código)", get("apa_carate")),
            ("Médico responsável", get("apa_nomeresp_med")), ("CNS do médico responsável", get("apa_cnsres")),
            ("CPF do médico responsável", UNAVAILABLE), ("Data da solicitação", date(get("apa_datsol"))),
            ("Profissional autorizador", get("apa_nomediretor")), ("CNS do autorizador", get("apa_cnsdir")),
            ("CPF do autorizador", UNAVAILABLE), ("Data da autorização", date(get("apa_dataut"))),
            ("Código do órgão emissor", get("apa_codemis")),
        ])
        content += fields_section("Outras informações", [
            ("UF (IBGE)", get("apa_coduf")), ("Data do processamento", date(get("apa_pr"))),
            ("Tipo de atendimento", get("apa_tipate")), ("Sexo", get("apa_sexopcnte")),
            ("Procedimento principal", get("apa_codprinc")), ("CID causas associadas", get("apa_cidca")),
            ("Prontuário", get("apa_npront")), ("Código do logradouro", get("apa_cdlogr")),
            ("CNS executante", get("apa_cnsexec")), ("INE", get("apa_ine")),
            ("Fonte orçamentária", get("apa_fntorca")), ("Emenda parlamentar", get("apa_emenpar")),
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
