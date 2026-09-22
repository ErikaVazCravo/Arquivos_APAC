# -*- coding: utf-8 -*-
"""
EDITOR DE ARQUIVO APAC (layout interno SIA/APAC - versão consultada em 08/07/2026)

Funções principais:
- Solicita o arquivo APAC, independentemente da extensão (.JUL, .AGO, etc.).
- Permite pesquisar por número ou navegar pelas APACs do arquivo.
- Localiza e exibe, em uma única janela com abas:
    * Cabeçalho do arquivo (registro 01)
    * Corpo da APAC (registro 14)
    * Parte variável existente (06, 07, 08, 09, 10, 11, 12, 17, 18, 19 ou 20)
    * Registros de procedimentos (registro 13)
- Permite editar os campos e salvar novamente no arquivo.
- Se o número da APAC for alterado, propaga o novo número para todos os registros daquela APAC.
- Recalcula automaticamente o campo de controle do cabeçalho.
- Cria backup automático antes do primeiro salvamento sobre o arquivo original.
- Gera fichas HTML locais, somente para leitura, com todos os dados para digitação.

Observação: o programa edita campos existentes. Ele não inclui/exclui APACs nem procedimentos.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ModuleNotFoundError:
    class _TkUnavailable:
        class Frame:
            pass

        class Toplevel:
            pass

        class Tk:
            pass

        def __getattr__(self, _name):
            return 0

    tk = _TkUnavailable()
    ttk = _TkUnavailable()
    filedialog = messagebox = simpledialog = _TkUnavailable()

from apac_report import generate_report, load_descriptions
from sigtap_tables import load_sigtap_folder

APP_TITLE = "Editor de Arquivo APAC"
ENCODINGS_TO_TRY = ["cp850", "cp1252", "latin-1"]


def show_readonly_report(parent, apac_file, descriptions, apac_num=None):
    try:
        parent.configure(cursor="watch")
        parent.update_idletasks()
        index, pages = generate_report(apac_file, BODY_FIELDS, PROC_FIELDS, VARIABLE_LAYOUTS, descriptions)
        target = next((path for number, path in pages if number == apac_num), index)
        if not webbrowser.open(target.as_uri()):
            messagebox.showinfo(APP_TITLE, f"Consulta criada. Abra este arquivo no navegador:\n{target}", parent=parent)
    except Exception as exc:
        messagebox.showerror(APP_TITLE, f"Não foi possível abrir a consulta:\n{exc}", parent=parent)
    finally:
        parent.configure(cursor="")


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    start: int  # posição 1-based inclusiva
    end: int    # posição 1-based inclusiva
    required: str = ""
    desc: str = ""
    kind: str = "CHAR"
    read_only: bool = False

    @property
    def size(self) -> int:
        return self.end - self.start + 1


# ----------------------------
# Layouts
# ----------------------------
HEADER_FIELDS = [
    FieldDef("cbc_hdr", "Indicador do registro", 1, 2, "SIM", "01 = cabeçalho", "NUM", True),
    FieldDef("cbc_apac", "Identificador", 3, 7, "SIM", "#APAC", "CHAR", True),
    FieldDef("cbc_cmp", "Competência", 8, 13, "SIM", "AAAAMM", "NUM"),
    FieldDef("cbc_lin", "Quantidade de APAC", 14, 19, "SIM", "Quantidade de APAC gravadas", "NUM", True),
    FieldDef("cbc_smt_vrf", "Campo de controle", 20, 23, "SIM", "Calculado automaticamente", "NUM", True),
    FieldDef("cbc_rsp", "Órgão de origem", 24, 53, "SIM", "Nome do órgão responsável pela informação", "CHAR"),
    FieldDef("cbc_sgl", "Sigla/código do órgão", 54, 59, "SIM", "Órgão de origem responsável pela digitação", "CHAR"),
    FieldDef("cbc_cgccpf", "CNPJ/CGC do responsável", 60, 73, "SIM", "Completar com zeros à esquerda", "NUM"),
    FieldDef("cbc_dst", "Órgão de destino", 74, 113, "SIM", "Nome do órgão de destino", "CHAR"),
    FieldDef("cbc_dst_in", "Destino M/E", 114, 114, "SIM", "M = Municipal; E = Estadual", "CHAR"),
    FieldDef("cbc_dtger", "Data de geração", 115, 122, "SIM", "AAAAMMDD", "NUM"),
    FieldDef("cbc_versao", "Versão", 123, 137, "SIM", "Versão do arquivo", "CHAR"),
]

BODY_FIELDS = [
    FieldDef("apa_corpo", "Indicador do registro", 1, 2, "SIM", "14 = corpo da APAC", "NUM", True),
    FieldDef("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"),
    FieldDef("apa_num", "Número da APAC", 9, 21, "SIM", "13 dígitos, incluindo DV", "NUM"),
    FieldDef("apa_coduf", "UF (IBGE)", 22, 23, "SIM", "Código da UF", "NUM"),
    FieldDef("apa_codcnes", "CNES executante", 24, 30, "SIM", "Unidade prestadora", "NUM"),
    FieldDef("apa_pr", "Data do processamento", 31, 38, "SIM", "YYYYMMDD", "NUM"),
    FieldDef("apa_dtiinval", "Início da validade", 39, 46, "SIM", "YYYYMMDD", "NUM"),
    FieldDef("apa_dtfimval", "Fim da validade", 47, 54, "SIM", "YYYYMMDD", "NUM"),
    FieldDef("apa_tipate", "Tipo de atendimento", 55, 56, "SIM", "Código do tipo de atendimento", "NUM"),
    FieldDef("apa_tipapac", "Tipo de APAC", 57, 57, "SIM", "1 = Inicial; 2 = Continuidade; 3 = Única", "NUM"),
    FieldDef("apa_nomepcnte", "Nome do paciente", 58, 87, "SIM", "Nome do paciente", "CHAR"),
    FieldDef("apa_nomemae", "Nome da mãe", 88, 117, "SIM", "Nome da mãe do paciente", "CHAR"),
    FieldDef("apa_logpcnte", "Logradouro", 118, 147, "SIM", "Endereço do paciente", "CHAR"),
    FieldDef("apa_numpcnte", "Número do endereço", 148, 152, "SIM", "Número da residência", "CHAR"),
    FieldDef("apa_cplpcnte", "Complemento", 153, 162, "NÃO", "Complemento do logradouro", "CHAR"),
    FieldDef("apa_ceppcnte", "CEP", 163, 170, "SIM", "CEP do paciente", "NUM"),
    FieldDef("apa_munpcnte", "Município (IBGE)", 171, 177, "SIM", "Código do município", "NUM"),
    FieldDef("apa_datanascim", "Data de nascimento", 178, 185, "SIM", "YYYYMMDD", "NUM"),
    FieldDef("apa_sexopcnte", "Sexo", 186, 186, "SIM", "M = Masculino; F = Feminino", "CHAR"),
    FieldDef("apa_nomeresp_med", "Médico responsável", 187, 216, "SIM", "Nome do médico responsável", "CHAR"),
    FieldDef("apa_codprinc", "Procedimento principal", 217, 226, "SIM", "Código do procedimento principal", "NUM"),
    FieldDef("apa_motsaida", "Motivo saída/permanência", 227, 228, "SIM", "Código do motivo de saída/permanência", "NUM"),
    FieldDef("apa_dtobitoalta", "Data alta/transf./óbito", 229, 236, "NÃO", "Obrigatoriedade conforme motivo de saída", "CHAR"),
    FieldDef("apa_nomediretor", "Profissional autorizador", 237, 266, "SIM", "Nome do profissional autorizador", "CHAR"),
    FieldDef("apa_cnspct", "CNS do paciente", 267, 281, "SIM", "Cartão Nacional de Saúde", "NUM"),
    FieldDef("apa_cnsres", "CNS médico responsável", 282, 296, "SIM", "CNS do médico responsável", "NUM"),
    FieldDef("apa_cnsdir", "CNS do autorizador", 297, 311, "SIM", "CNS do autorizador", "NUM"),
    FieldDef("apa_cidca", "CID causas associadas", 312, 315, "NÃO", "CID de causas associadas", "CHAR"),
    FieldDef("apa_npront", "Prontuário", 316, 325, "NÃO", "Número do prontuário", "NUM"),
    FieldDef("apa_codsol", "CNES solicitante", 326, 332, "NÃO", "Código CNES do solicitante", "NUM"),
    FieldDef("apa_datsol", "Data da solicitação", 333, 340, "SIM", "YYYYMMDD", "NUM"),
    FieldDef("apa_dataut", "Data da autorização", 341, 348, "SIM", "YYYYMMDD", "NUM"),
    FieldDef("apa_codemis", "Código do emissor", 349, 358, "SIM", "Código do emissor", "CHAR"),
    FieldDef("apa_carate", "Caráter do atendimento", 359, 360, "SIM", "01 Eletivo; 02 Urgência; 03-06 acidentes/lesões", "NUM"),
    FieldDef("apa_apacant", "APAC anterior", 361, 373, "NÃO", "Número da APAC anterior", "NUM"),
    FieldDef("apa_raca", "Raça/Cor", 374, 375, "SIM", "01 Branca; 02 Preta; 03 Parda; 04 Amarela; 05 Indígena; 99 Sem informação", "NUM"),
    FieldDef("apa_nomeresp_pac", "Responsável pelo paciente", 376, 405, "SIM", "Nome do responsável", "CHAR"),
    FieldDef("apa_nascpcnte", "Nacionalidade", 406, 408, "SIM", "Código de nacionalidade", "NUM"),
    FieldDef("apa_etnia", "Etnia", 409, 412, "COND.", "Obrigatória se raça/cor = 05", "NUM"),
    FieldDef("apa_cdlogr", "Código do logradouro", 413, 415, "COND.", "Opcional a partir de 03/2013", "NUM"),
    FieldDef("apa_bairro", "Bairro", 416, 445, "COND.", "Bairro do paciente", "CHAR"),
    FieldDef("apa_dddtelcontato", "DDD", 446, 447, "NÃO", "DDD do telefone", "NUM"),
    FieldDef("apa_telcontato", "Telefone", 448, 456, "NÃO", "Telefone de contato", "NUM"),
    FieldDef("apa_email", "E-mail", 457, 496, "NÃO", "E-mail do paciente", "CHAR"),
    FieldDef("apa_cnsexec", "CNS executante", 497, 511, "COND.", "CNS do médico executante do procedimento principal", "NUM"),
    FieldDef("apa_cpfpcnte", "CPF do paciente", 512, 522, "NÃO", "CPF do indivíduo", "NUM"),
    FieldDef("apa_ine", "INE", 523, 532, "NÃO", "Identificação Nacional de Equipe", "NUM"),
    FieldDef("apa_strua", "Pessoa em situação de rua", 533, 533, "NÃO", "S = Sim; N = Não", "CHAR"),
    FieldDef("apa_fntorca", "Fonte orçamentária", 534, 535, "NÃO", "01 a 04, conforme layout", "NUM"),
    FieldDef("apa_emenpar", "Emenda parlamentar", 536, 536, "NÃO", "S = Sim; N = Não", "CHAR"),
    FieldDef("apa_semcpf", "Pessoa sem CPF/Registro Civil", 537, 537, "NÃO", "S = Sim; N = Não; válido a partir de 07/2026", "CHAR"),
]

PROC_FIELDS = [
    FieldDef("pap_corpo", "Indicador", 1, 2, "SIM", "13 = ações/procedimentos da APAC", "NUM", True),
    FieldDef("pap_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"),
    FieldDef("pap_num", "Número da APAC", 9, 21, "SIM", "13 dígitos", "NUM", True),
    FieldDef("pap_codproc", "Procedimento", 22, 31, "SIM", "Código do procedimento", "NUM"),
    FieldDef("pap_cbo", "CBO", 32, 37, "SIM", "Código CBO", "NUM"),
    FieldDef("pap_qtdprod", "Quantidade", 38, 44, "SIM", "Quantidade de procedimentos", "NUM"),
    FieldDef("pap_CGC", "CNPJ cessão de crédito", 45, 58, "NÃO", "CNPJ quando houver cessão de crédito", "NUM"),
    FieldDef("pap_NF", "Nota fiscal", 59, 64, "NÃO", "Número da nota fiscal", "CHAR"),
    FieldDef("pap_CIDP", "CID principal", 65, 68, "SIM*", "Aplicável conforme procedimento/laudo", "CHAR"),
    FieldDef("pap_CIDS", "CID secundário", 69, 72, "NÃO", "CID secundário", "CHAR"),
    FieldDef("pap_SRV", "Serviço", 73, 75, "NÃO", "Código do serviço", "NUM"),
    FieldDef("pap_CLF", "Classificação", 76, 78, "NÃO", "Código da classificação", "NUM"),
    FieldDef("pap_equipe_Seq", "Sequência da equipe", 79, 86, "NÃO", "Código da sequência da equipe", "NUM"),
    FieldDef("pap_equipe_Area", "Área da equipe", 87, 90, "NÃO", "Código da área da equipe", "NUM"),
    FieldDef("pap_cnes_terc", "CNES terceiro", 91, 97, "NÃO", "Unidade prestadora de serviços terceiro", "NUM"),
]


def F(key, label, start, end, req="", desc="", kind="CHAR", ro=False):
    return FieldDef(key, label, start, end, req, desc, kind, ro)

# Parte variável - registros APAC suportados pelo layout fornecido.
VARIABLE_LAYOUTS: dict[str, tuple[str, list[FieldDef]]] = {
    "06": ("Laudo Geral", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "06 = laudo geral", "NUM", True),
        F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"),
        F("apa_num", "Número da APAC", 9, 21, "SIM", "13 dígitos", "NUM", True),
        F("apa_cidpri", "CID principal", 22, 25, "SIM", "CID principal", "CHAR"),
        F("apa_cidsec", "CID secundário", 26, 29, "NÃO", "CID secundário", "CHAR"),
        F("apa_dtiden", "Data identificação patológica", 30, 37, "COND.", "AAAAMMDD; conforme regra do procedimento", "NUM"),
    ]),
    "07": ("Oncologia - Quimioterapia", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "07 = quimioterapia", "NUM", True),
        F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_cid10", "CID 10 topografia", 22, 25, "SIM"), F("apa_linfin", "Linfonodos regionais", 26, 26, "SIM", "S/N/3"),
        F("apa_estadi", "Estádio UICC", 27, 27, "COND.", "0 a 4", "NUM"), F("apa_grahis", "Grau histopatológico", 28, 29, "SIM", "", "NUM"),
        F("apa_dtiden", "Data identificação patológica", 30, 37, "SIM", "AAAAMMDD", "NUM"), F("apa_trante", "Tratamentos anteriores", 38, 38, "SIM", "S/N"),
        F("apa_cidini1", "CID 1º tratamento anterior", 39, 42, "NÃO"), F("apa_dtini1", "Data 1º tratamento", 43, 50, "COND.", "AAAAMMDD", "NUM"),
        F("apa_cidini2", "CID 2º tratamento anterior", 51, 54, "NÃO"), F("apa_dtini2", "Data 2º tratamento", 55, 62, "COND.", "AAAAMMDD", "NUM"),
        F("apa_cidini3", "CID 3º tratamento anterior", 63, 66, "NÃO"), F("apa_dtini3", "Data 3º tratamento", 67, 74, "COND.", "AAAAMMDD", "NUM"),
        F("apa_conttr", "Continuidade do tratamento", 75, 75, "SIM", "S/N"), F("apa_dtintr", "Início tratamento solicitado", 76, 83, "SIM", "AAAAMMDD", "NUM"),
        F("apa_totmpl", "Meses planejados", 84, 86, "SIM", "", "NUM"), F("apa_totmau", "Meses autorizados", 87, 89, "SIM", "", "NUM"),
        F("apa_cidpri", "CID principal", 90, 93, "SIM"), F("apa_cidsec", "CID secundário", 94, 97, "NÃO"),
        F("apa_esquema", "Esquema", 98, 112, "SIM", "Sigla/abreviação"),
        *[F(f"apa_codmedant{i}", f"Medicamento antineoplásico {i}", 110 + 3*i, 112 + 3*i, "SIM" if i == 1 else "NÃO", "Código com 3 posições", "NUM") for i in range(1, 11)],
    ]),
    "08": ("Oncologia - Radioterapia", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "08 = radioterapia", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"),
        F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True), F("apa_cid10", "CID 10 topografia", 22, 25, "SIM"),
        F("apa_linfin", "Linfonodos regionais", 26, 26, "SIM", "S/N/3"), F("apa_estadi", "Estádio UICC", 27, 27, "NÃO", "0 a 4", "NUM"),
        F("apa_grahis", "Grau histopatológico", 28, 29, "SIM", "", "NUM"), F("apa_dtiden", "Data identificação patológica", 30, 37, "SIM", "AAAAMMDD", "NUM"),
        F("apa_trante", "Tratamentos anteriores", 38, 38, "SIM", "S/N"), F("apa_cidini1", "CID 1º tratamento anterior", 39, 42, "NÃO"),
        F("apa_dtini1", "Data 1º tratamento", 43, 50, "COND.", "AAAAMMDD", "NUM"), F("apa_cidini2", "CID 2º tratamento anterior", 51, 54, "NÃO"),
        F("apa_dtini2", "Data 2º tratamento", 55, 62, "COND.", "AAAAMMDD", "NUM"), F("apa_cidini3", "CID 3º tratamento anterior", 63, 66, "NÃO"),
        F("apa_dtini3", "Data 3º tratamento", 67, 74, "COND.", "AAAAMMDD", "NUM"), F("apa_conttr", "Continuidade do tratamento", 75, 75, "SIM", "S/N"),
        F("apa_dtintr", "Início tratamento solicitado", 76, 83, "SIM", "AAAAMMDD", "NUM"), F("apa_finali", "Finalidade do tratamento", 84, 84, "SIM", "1 Radical; 2 Adjuvante; 3 Antiálgica; 4 Paliativa; 5 Prévia; 6 Antihemorrágica", "NUM"),
        F("apa_cidtr1", "CID topográfico 1º", 85, 88, "SIM"), F("apa_cidtr2", "CID topográfico 2º", 89, 92, "NÃO"), F("apa_cidtr3", "CID topográfico 3º", 93, 96, "NÃO"),
        F("apa_numc1", "Nº campo/inserções 1º", 97, 99, "NÃO", "", "NUM"), F("apa_iniar1", "Data início 1º", 100, 107, "SIM", "AAAAMMDD", "NUM"),
        F("apa_iniar2", "Data início 2º", 108, 115, "NÃO", "AAAAMMDD", "NUM"), F("apa_iniar3", "Data início 3º", 116, 123, "NÃO", "AAAAMMDD", "NUM"),
        F("apa_fimar1", "Data fim 1º", 124, 131, "SIM", "AAAAMMDD", "NUM"), F("apa_fimar2", "Data fim 2º", 132, 139, "NÃO", "AAAAMMDD", "NUM"),
        F("apa_fimar3", "Data fim 3º", 140, 147, "NÃO", "AAAAMMDD", "NUM"), F("apa_cidpri", "CID principal", 148, 151, "SIM"),
        F("apa_cidsec", "CID secundário", 152, 155, "NÃO"), F("apa_numc2", "Nº campo/inserções 2º", 156, 158, "NÃO", "", "NUM"),
        F("apa_numc3", "Nº campo/inserções 3º", 159, 161, "NÃO", "", "NUM"),
    ]),
    "09": ("Nefrologia - layout legado", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "09 = nefrologia", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_dtpdr", "Primeira diálise", 22, 29, "SIM", "AAAAMMDD", "NUM"), F("apa_altura", "Altura (cm)", 30, 32, "SIM", "", "NUM"), F("apa_peso", "Peso (kg)", 33, 35, "SIM", "", "NUM"),
        F("apa_diures", "Diurese (ml)", 36, 39, "SIM", "", "NUM"), F("apa_glicos", "Glicose (mg/dl)", 40, 43, "SIM", "", "NUM"), F("apa_acevas", "Acesso vascular", 44, 44, "SIM", "S/N"),
        F("apa_ulsoab", "Ultrassonografia abdominal", 45, 45, "SIM", "S/N"), F("apa_tru", "TRU", 46, 49, "NÃO", "", "NUM"), F("apa_intfis", "Intervenção de fístula", 50, 51, "SIM", "", "NUM"),
        F("apa_cncdo", "Inscrito CNCDO", 52, 52, "SIM", "S/N"), F("apa_albumi", "Albumina", 53, 54, "NÃO", "", "NUM"), F("apa_hcv", "HCV", 55, 55, "SIM", "P/N"),
        F("apa_hbsag", "HBsAg", 56, 56, "SIM", "P/N"), F("apa_hiv", "HIV", 57, 57, "SIM", "P/N"), F("apa_hb", "HB", 58, 59, "SIM", "", "NUM"),
        F("apa_cidpri", "CID principal", 60, 63, "SIM"), F("apa_cidsec", "CID secundário", 64, 67, "NÃO"),
    ]),
    "10": ("Medicamentos", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "10 = medicamentos", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_peso", "Peso (kg)", 22, 24, "SIM", "", "NUM"), F("apa_altura", "Altura (cm)", 25, 27, "SIM", "", "NUM"), F("apa_transp", "Transplantado", 28, 28, "SIM", "S/N"),
        F("apa_qtdtra", "Qtd. transplantes", 29, 30, "SIM", "Informar se transplantado = S", "NUM"), F("apa_filler1", "Espaços", 31, 32, "SIM", "", "CHAR", True), F("apa_gestan", "Gestante", 33, 33, "SIM", "S/N"),
    ]),
    "11": ("Pós-cirurgia bariátrica", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "11 = pós-bariátrica", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_imc", "IMC", 22, 24, "SIM", "", "NUM"), F("apa_peso_perd", "% excesso peso perdido", 25, 27, "SIM", "", "NUM"), F("apa_kg_perd", "Kg perdidos", 28, 30, "SIM", "", "NUM"),
        F("apa_0407010122", "Gastrectomia c/ ou s/ desvio duodenal", 31, 31, "SIM", "S/N"), F("apa_0407010360", "Gastrectomia vertical em manga", 32, 32, "SIM", "S/N"),
        F("apa_0407010173", "Gastroplastia com derivação intestinal", 33, 33, "SIM", "S/N"), F("apa_0407010181", "Gastroplastia vertical com banda", 34, 34, "SIM", "S/N"),
        F("apa_dtcirurg", "Data da cirurgia", 35, 42, "SIM", "AAAAMMDD", "NUM"), F("apa_numaih", "Número da AIH", 43, 55, "SIM", "", "NUM"), F("apa_filler", "Brancos", 56, 56, "SIM", "", "CHAR", True),
        F("apa_comorb", "Comorbidades", 57, 57, "SIM", "S/N"), F("apa_i10", "Hipertensão", 58, 58, "SIM", "S/N"), F("apa_o243", "Diabetes", 59, 59, "SIM", "S/N"), F("apa_e780", "Dislipidemia", 60, 60, "SIM", "S/N"), F("apa_m199", "Artrose", 61, 61, "SIM", "S/N"), F("apa_g473", "Apneia", 62, 62, "SIM", "S/N"),
        F("apa_outros", "Outros CID10", 63, 66, "NÃO"), F("apa_medicam", "Uso de medicamentos", 67, 67, "SIM", "S/N"), F("apa_atv_fisica", "Atividade física", 68, 68, "SIM", "S/N"), F("apa_polivit", "Polivitamínico", 69, 69, "SIM", "S/N"), F("apa_reganho", "Reganho de peso", 70, 70, "SIM", "S/N"), F("apa_adesao", "Adesão alimentar", 71, 71, "SIM", "S/N"),
        F("apa_0413040054", "Dermolipectomia abdominal", 72, 72, "SIM", "S/N"), F("apa_0413040054_meses", "Meses pós-cirurgia", 73, 75, "NÃO", "", "NUM"), F("apa_0413040089", "Mamoplastia", 76, 76, "SIM", "S/N"), F("apa_0413040089_meses", "Meses pós-cirurgia", 77, 79, "NÃO", "", "NUM"),
        F("apa_0413040062", "Dermolipectomia braquial", 80, 80, "SIM", "S/N"), F("apa_0413040062_meses", "Meses pós-cirurgia", 81, 83, "NÃO", "", "NUM"), F("apa_0413040070", "Dermolipectomia crural", 84, 84, "SIM", "S/N"), F("apa_0413040070_meses", "Meses pós-cirurgia", 85, 87, "NÃO", "", "NUM"),
        F("apa_0414040267", "Dermolipectomia abdominal circunferencial", 88, 88, "SIM", "S/N"), F("apa_0414040267_meses", "Meses pós-cirurgia", 89, 91, "NÃO", "", "NUM"), F("apa_filler2", "Brancos", 92, 96, "SIM", "", "CHAR", True),
        F("apa_mesacomp", "Meses acompanhamento", 97, 98, "NÃO", "", "NUM"), F("apa_anoacomp", "Ano acompanhamento", 99, 102, "NÃO", "", "NUM"), F("apa_cidp", "CID principal", 103, 106, "SIM"), F("apa_cids", "CID secundário", 107, 110, "NÃO"), F("apa_0407010386", "Bariátrica videolaparoscopia", 111, 111, "SIM", "S/N"),
    ]),
    "12": ("Prótese de mama", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "12 = prótese de mama", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_mprt", "Marca da prótese", 22, 22, "SIM", "1 = PIP; 2 = ROFIL", "NUM"), F("apa_anoprt", "Ano implantação", 23, 26, "SIM", "Conforme layout", "NUM"), F("apa_cnesprt", "CNES do implante", 27, 33, "SIM", "", "NUM"),
    ]),
    "17": ("Pré-cirurgia bariátrica", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "17 = pré-bariátrica", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_imc_atu", "IMC atual", 22, 24, "SIM", "", "NUM"), F("apa_dt_atu", "Data avaliação atual", 25, 32, "SIM", "AAAAMMDD", "NUM"), F("apa_peso", "Peso (kg)", 33, 35, "SIM", "", "NUM"), F("apa_imc_privez", "IMC 1ª avaliação", 36, 38, "SIM", "", "NUM"), F("apa_dt_privez", "Data 1ª avaliação", 39, 46, "SIM", "AAAAMMDD", "NUM"),
        F("apa_223710", "Nutricionista", 47, 47, "SIM", "S/N"), F("apa_225133", "Psiquiatra", 48, 48, "SIM", "S/N"), F("apa_225225", "Cirurgião geral", 49, 49, "SIM", "S/N"), F("apa_251510", "Psicólogo", 50, 50, "SIM", "S/N"), F("apa_225155", "Endócrino", 51, 51, "SIM", "S/N"), F("apa_225125", "Clínico", 52, 52, "SIM", "S/N"), F("apa_225220", "Cirurgião aparelho digestivo", 53, 53, "SIM", "S/N"),
        F("apa_reunioes", "Reuniões multiprofissionais", 54, 54, "SIM", "S/N"), F("apa_risco_cir", "Risco cirúrgico", 55, 55, "SIM", "S/N"), F("apa_exam_lab", "Exames laboratoriais", 56, 56, "SIM", "S/N"), F("apa_comorb", "Comorbidades", 57, 57, "SIM", "S/N"), F("apa_i10", "Hipertensão", 58, 58, "SIM", "S/N"), F("apa_o243", "Diabetes", 59, 59, "SIM", "S/N"), F("apa_e780", "Dislipidemia", 60, 60, "SIM", "S/N"), F("apa_m199", "Artrose", 61, 61, "SIM", "S/N"), F("apa_g473", "Apneia", 62, 62, "SIM", "S/N"), F("apa_outros", "Outros CID10", 63, 66, "NÃO"),
        F("apa_medicam", "Uso de medicamentos", 67, 67, "SIM", "S/N"), F("apa_atv_fisica", "Atividade física", 68, 68, "SIM", "S/N"), F("apa_perda", "Perda ponderal pré-operatória", 69, 69, "SIM", "S/N"), F("apa_0209010037", "Esofagogastroduodenoscopia", 70, 70, "SIM", "S/N"), F("apa_0205020046", "US abdômen total", 71, 71, "SIM", "S/N"), F("apa_0205010032", "Ecocardiografia", 72, 72, "SIM", "S/N"), F("apa_0205010040", "Doppler colorido", 73, 73, "SIM", "S/N"), F("apa_0211080055", "Espirometria", 74, 74, "SIM", "S/N"), F("apa_apto", "Apto para cirurgia", 75, 75, "SIM", "S/N/A"), F("apa_cidp", "CID principal", 76, 79, "SIM"), F("apa_cids", "CID secundário", 80, 83, "NÃO"),
    ]),
    "18": ("Tratamento dialítico", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "18 = tratamento dialítico", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_cidpri", "CID principal", 22, 25, "SIM"), F("apa_cidsec", "CID secundário", 26, 29, "NÃO"), F("apa_caract", "Característica tratamento", 30, 30, "SIM", "1 Novo; 2 Continuidade; 3 Trânsito; 4 Transferência", "NUM"),
        F("apa_dtpdr", "Início primeira diálise", 31, 38, "SIM", "AAAAMMDD", "NUM"), F("apa_dtcli", "Início diálise nesta clínica", 39, 46, "SIM", "AAAAMMDD", "NUM"), F("apa_acevas", "Acesso vascular", 47, 47, "SIM", "1 FAV; 2 Cateter curta; 3 Cateter longa", "NUM"),
        F("apa_maisne", "> 1 ano nefrologia", 48, 48, "SIM", "S/N/I"), F("apa_sitini", "Situação inicial", 49, 49, "SIM", "A/H/I"), F("apa_sittra", "Situação transplante", 50, 50, "SIM", "1 Apto; 2 Inapto; 3 Recusa; 4 N/A", "NUM"), F("apa_seapto", "Se apto", 51, 51, "COND.", "1 a 4", "NUM"),
        F("apa_hb", "HB", 52, 55, "SIM", "Pode conter decimal", "NUM"), F("apa_fosfor", "Fósforo", 56, 59, "SIM", "Pode conter decimal", "NUM"), F("apa_ktvsem", "Kt/V semanal", 60, 63, "NÃO", "", "NUM"), F("apa_tru", "TRU", 64, 67, "NÃO", "", "NUM"), F("apa_albumi", "Albumina", 68, 71, "NÃO", "", "NUM"), F("apa_pth", "PTH", 72, 75, "NÃO", "", "NUM"),
        F("apa_hiv", "HIV", 76, 76, "NÃO", "P/N"), F("apa_hcv", "HCV", 77, 77, "NÃO", "P/N"), F("apa_hbsag", "HBsAg", 78, 78, "NÃO", "P/N"), F("apa_interc", "Internação por intercorrência", 79, 79, "SIM", "S/N/I"), F("apa_seperi", "Peritonite no mês", 80, 80, "SIM", "S/N/I"),
    ]),
    "19": ("Acompanhamento multiprofissional em DRC", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "19 = acompanhamento DRC", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_cidpri", "CID principal", 22, 25, "SIM"), F("apa_cidsec", "CID secundário", 26, 29, "NÃO"), F("apa_caract", "Característica tratamento", 30, 30, "SIM", "1 Novo; 2 Continuidade; 3 Trânsito; 4 Transferência", "NUM"), F("apa_dtinic", "Início do tratamento", 31, 38, "", "AAAAMMDD", "NUM"),
        F("apa_encfav", "Encaminhado para FAV", 39, 39, "SIM", "S/N"), F("apa_enccat", "Encaminhado para cateter", 40, 40, "SIM", "S/N"), F("apa_altura", "Altura (cm)", 41, 43, "NÃO", "", "NUM"), F("apa_peso", "Peso (kg)", 44, 46, "NÃO", "", "NUM"), F("apa_sitvac", "Situação vacinal", 47, 47, "SIM", "R/N"), F("apa_anthbs", "Anti HBS", 48, 48, "SIM", "R/N"), F("apa_influe", "Influenza", 49, 49, "SIM", "S/N/I"), F("apa_diftet", "Dupla adulto dT", 50, 50, "SIM", "S/N/I"), F("apa_pneumo", "Pneumocócica", 51, 51, "SIM", "S/N/I"),
        F("apa_hb", "HB", 52, 55, "NÃO", "", "NUM"), F("apa_fosfor", "Fósforo", 56, 59, "NÃO", "", "NUM"), F("apa_albumi", "Albumina", 60, 63, "NÃO", "", "NUM"), F("apa_pth", "PTH", 64, 67, "NÃO", "", "NUM"), F("apa_hiv", "HIV", 68, 68, "SIM", "P/N"), F("apa_hcv", "HCV", 69, 69, "SIM", "P/N"), F("apa_hbsag", "HBsAg", 70, 70, "SIM", "P/N"), F("apa_ieca", "Uso IECA", 71, 71, "SIM", "S/N/I"), F("apa_bra", "Uso BRA", 72, 72, "SIM", "S/N/I"),
    ]),
    "20": ("Confecção de fístula arteriovenosa", [
        F("apa_varia", "Indicador", 1, 2, "SIM", "20 = confecção de FAV", "NUM", True), F("apa_cmp", "Competência", 3, 8, "SIM", "AAAAMM", "NUM"), F("apa_num", "Número da APAC", 9, 21, "SIM", "", "NUM", True),
        F("apa_cidpri", "CID principal", 22, 25, "SIM"), F("apa_cidsec", "CID secundário", 26, 29, "NÃO"), F("apa_duplex", "Duplex prévio", 30, 30, "SIM", "S/N"), F("apa_usocat", "Cateter/acesso venoso prévio", 31, 31, "SIM", "S/N"), F("apa_prefav", "FAV prévia", 32, 32, "SIM", "S/N"), F("apa_flebit", "Flebites", 33, 33, "SIM", "S/N"), F("apa_hemato", "Hematomas", 34, 34, "SIM", "S/N"), F("apa_veiavi", "Veia visível", 35, 35, "SIM", "S/N"), F("apa_pulso", "Presença de pulso", 36, 36, "SIM", "S/N"), F("apa_veidia", "Diâmetro da veia (mm)", 37, 40, "NÃO", "", "NUM"), F("apa_artdia", "Diâmetro da artéria (mm)", 41, 44, "NÃO", "", "NUM"), F("apa_fremit", "Frêmito no trajeto da FAV", 45, 45, "SIM", "1 a 4", "NUM"), F("apa_pulfre", "Pulso sem frêmito", 46, 46, "SIM", "S/N"),
    ]),
}


# ----------------------------
# Utilidades de arquivo
# ----------------------------
def detect_encoding(raw: bytes) -> str:
    for enc in ENCODINGS_TO_TRY:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            pass
    return "latin-1"


def clean_apac_number(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def extract_field(line: str, field: FieldDef) -> str:
    if field.start > len(line):
        return ""
    return line[field.start - 1:min(field.end, len(line))].rstrip()


def fit_value(value: str, field: FieldDef) -> str:
    value = (value or "").replace("\r", " ").replace("\n", " ")
    if len(value) > field.size:
        raise ValueError(f"{field.label}: máximo de {field.size} caracteres.")
    # O arquivo do SIA usa posições fixas. NUM é completado à esquerda somente
    # quando já houver valor; CHAR é completado à direita.
    if field.kind.upper() == "NUM" and value.strip():
        return value.strip().rjust(field.size, "0")
    return value.ljust(field.size, " ")


def set_field(line: str, field: FieldDef, value: str) -> str:
    fitted = fit_value(value, field)
    # Evita alongar registros variáveis apenas para gravar campo vazio no final.
    if field.start > len(line) and not value.strip():
        return line
    if len(line) < field.end:
        line = line.ljust(field.end, " ")
    return line[:field.start - 1] + fitted + line[field.end:]


class ApacFile:
    def __init__(self, path: str):
        self.path = Path(path)
        self.raw = self.path.read_bytes()
        self.encoding = detect_encoding(self.raw)
        self.newline = b"\r\n" if b"\r\n" in self.raw else (b"\n" if b"\n" in self.raw else os.linesep.encode())
        self.has_ctrl_z = self.raw.endswith(b"\x1a") or self.raw.rstrip(b"\r\n").endswith(b"\x1a")

        content = self.raw
        # Retira Ctrl-Z terminal sem perder informação para a gravação posterior.
        if self.has_ctrl_z:
            content = content.rstrip(b"\r\n")
            if content.endswith(b"\x1a"):
                content = content[:-1]

        raw_lines = content.split(self.newline)
        if raw_lines and raw_lines[-1] == b"":
            raw_lines.pop()
        self.lines = [x.decode(self.encoding, errors="replace") for x in raw_lines]
        self.backup_created = False

    def record_type(self, line: str) -> str:
        return line[:2] if len(line) >= 2 else ""

    def find_apac_indices(self, apac_num: str) -> dict[str, list[int]]:
        result: dict[str, list[int]] = {"14": [], "13": [], "var": []}
        for idx, line in enumerate(self.lines):
            typ = self.record_type(line)
            if typ == "14" and line[8:21] == apac_num:
                result["14"].append(idx)
            elif typ == "13" and line[8:21] == apac_num:
                result["13"].append(idx)
            elif typ in VARIABLE_LAYOUTS and len(line) >= 21 and line[8:21] == apac_num:
                result["var"].append(idx)
        return result

    def all_apac_numbers(self) -> list[str]:
        return [line[8:21] for line in self.lines if self.record_type(line) == "14" and len(line) >= 21]

    def recalc_header(self):
        # Quantidade de APAC = número de registros 14.
        count = sum(1 for line in self.lines if self.record_type(line) == "14")

        # Regra confirmada pelo layout: somar uma vez cada número de APAC +
        # código e quantidade de todos os procedimentos; resto por 1111 + 1111.
        apac_numbers = set()
        total = 0
        for line in self.lines:
            typ = self.record_type(line)
            if typ == "14" and len(line) >= 21:
                n = line[8:21].strip()
                if n.isdigit():
                    apac_numbers.add(int(n))
            elif typ == "13" and len(line) >= 44:
                proc = line[21:31].strip()
                qtd = line[37:44].strip()
                if proc.isdigit():
                    total += int(proc)
                if qtd.isdigit():
                    total += int(qtd)
        total += sum(apac_numbers)
        control = (total % 1111) + 1111

        for i, line in enumerate(self.lines):
            if self.record_type(line) == "01":
                # Campos por posição; preserva o restante do cabeçalho exatamente como está.
                if len(line) < 23:
                    line = line.ljust(23)
                line = line[:13] + str(count).zfill(6) + str(control).zfill(4) + line[23:]
                self.lines[i] = line
                break

    def create_backup(self):
        if self.backup_created:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = self.path.with_name(f"{self.path.name}.backup_{stamp}")
        shutil.copy2(self.path, backup)
        self.backup_created = True

    def save(self, target: Path | None = None):
        if target is None:
            self.create_backup()
            target = self.path
        self.recalc_header()
        data = self.newline.join(line.encode(self.encoding, errors="replace") for line in self.lines)
        data += self.newline
        if self.has_ctrl_z:
            data += b"\x1a"
        target.write_bytes(data)


# ----------------------------
# Interface
# ----------------------------
class ScrollableForm(ttk.Frame):
    def __init__(self, master, fields, line_getter, title=""):
        super().__init__(master)
        self.fields = fields
        self.line_getter = line_getter
        self.entries: dict[str, tk.StringVar] = {}
        self.original_values: dict[str, str] = {}

        canvas = tk.Canvas(self, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas, padding=10)
        self.inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        if title:
            ttk.Label(self.inner, text=title, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
            start_row = 1
        else:
            start_row = 0

        ttk.Label(self.inner, text="Campo", font=("Segoe UI", 9, "bold")).grid(row=start_row, column=0, sticky="w")
        ttk.Label(self.inner, text="Valor", font=("Segoe UI", 9, "bold")).grid(row=start_row, column=1, sticky="w")
        ttk.Label(self.inner, text="Tam.", font=("Segoe UI", 9, "bold")).grid(row=start_row, column=2, sticky="w")
        ttk.Label(self.inner, text="Descrição / regra", font=("Segoe UI", 9, "bold")).grid(row=start_row, column=3, sticky="w")

        line = line_getter()
        for r, fld in enumerate(fields, start=start_row + 1):
            ttk.Label(self.inner, text=fld.label).grid(row=r, column=0, sticky="nw", padx=(0, 8), pady=3)
            var = tk.StringVar(value=extract_field(line, fld))
            self.entries[fld.key] = var
            self.original_values[fld.key] = var.get()
            ent = ttk.Entry(self.inner, textvariable=var, width=max(12, min(45, fld.size + 3)))
            ent.grid(row=r, column=1, sticky="ew", padx=(0, 8), pady=3)
            if fld.read_only:
                ent.state(["readonly"])
            ttk.Label(self.inner, text=str(fld.size)).grid(row=r, column=2, sticky="nw", padx=(0, 8), pady=3)
            req = f"[{fld.required}] " if fld.required else ""
            ttk.Label(self.inner, text=req + fld.desc, wraplength=430, justify="left").grid(row=r, column=3, sticky="nw", pady=3)
        self.inner.columnconfigure(1, weight=1)
        self.inner.columnconfigure(3, weight=1)

    def apply_to_line(self, line: str) -> str:
        for fld in self.fields:
            if fld.read_only:
                continue
            current = self.entries[fld.key].get()
            # Preserva exatamente a linha original quando o campo não foi alterado.
            # Isso é importante porque alguns emissores omitem espaços finais, embora
            # o layout apresente tamanho máximo fixo.
            if current == self.original_values.get(fld.key, ""):
                continue
            line = set_field(line, fld, current)
        return line

    def get(self, key: str) -> str:
        return self.entries[key].get() if key in self.entries else ""


class EditorWindow(tk.Toplevel):
    def __init__(self, master, apac_file: ApacFile, apac_num: str):
        super().__init__(master)
        self.file = apac_file
        self.saved_lines = list(self.file.lines)
        self.original_apac_num = apac_num
        self.indices = self.file.find_apac_indices(apac_num)
        self.title(f"{APP_TITLE} - APAC {apac_num}")
        self.geometry("1250x820")
        self.minsize(1000, 650)

        if not self.indices["14"]:
            raise ValueError("APAC não encontrada no arquivo.")
        if len(self.indices["14"]) > 1:
            messagebox.showwarning(APP_TITLE, "Há mais de um registro 14 com esse número. O primeiro será exibido.", parent=self)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text=f"Arquivo: {self.file.path.name}", font=("Segoe UI", 10, "bold")).pack(side="left")
        self.apac_label = ttk.Label(top, text=f"   APAC: {apac_num}")
        self.apac_label.pack(side="left")

        numbers = list(dict.fromkeys(self.file.all_apac_numbers()))
        position = numbers.index(apac_num)
        navigation = ttk.Frame(self, padding=(10, 0, 10, 8))
        navigation.pack(fill="x")
        for label, target in (("Primeira", 0), ("Anterior", position - 1),
                              ("Próxima", position + 1), ("Última", len(numbers) - 1)):
            button = ttk.Button(navigation, text=label,
                                command=lambda i=target: self.switch_apac(numbers[i]))
            button.pack(side="left", padx=4)
            if target == position or not 0 <= target < len(numbers):
                button.state(["disabled"])
        ttk.Label(navigation, text=f"APAC {position + 1} de {len(numbers)}").pack(side="left", padx=12)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Cabeçalho
        hidx = next((i for i, l in enumerate(self.file.lines) if l.startswith("01")), None)
        self.header_form = None
        if hidx is not None:
            self.header_idx = hidx
            self.header_form = ScrollableForm(self.nb, HEADER_FIELDS, lambda: self.file.lines[hidx], "Cabeçalho do arquivo")
            self.nb.add(self.header_form, text="Cabeçalho (01)")

        # Corpo
        self.body_idx = self.indices["14"][0]
        self.body_form = ScrollableForm(self.nb, BODY_FIELDS, lambda: self.file.lines[self.body_idx], "Dados principais da APAC")
        self.nb.add(self.body_form, text="Dados da APAC (14)")

        # Variáveis
        self.variable_forms = []
        for n, idx in enumerate(self.indices["var"], start=1):
            typ = self.file.lines[idx][:2]
            name, fields = VARIABLE_LAYOUTS[typ]
            form = ScrollableForm(self.nb, fields, lambda idx=idx: self.file.lines[idx], f"Parte variável: {name} ({typ})")
            self.variable_forms.append((idx, typ, form))
            suffix = f" #{n}" if len(self.indices["var"]) > 1 else ""
            self.nb.add(form, text=f"Laudo {typ}{suffix}")

        # Procedimentos
        self.proc_frame = ttk.Frame(self.nb, padding=8)
        self.nb.add(self.proc_frame, text=f"Procedimentos (13) - {len(self.indices['13'])}")
        self._build_proc_tab()
        self.nb.select(self.body_form)

        bottom = ttk.Frame(self, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Salvar alterações", command=self.save).pack(side="right", padx=4)
        ttk.Button(bottom, text="Salvar como...", command=self.save_as).pack(side="right", padx=4)
        ttk.Button(bottom, text="Fechar", command=self.close).pack(side="right", padx=4)
        ttk.Button(bottom, text="Consultar outra APAC", command=self.open_other).pack(side="left", padx=4)
        ttk.Button(bottom, text="Dados para digitação da APAC", command=self.view_report).pack(side="left", padx=4)
        self.protocol("WM_DELETE_WINDOW", self.close)
        master.withdraw()
        self.grab_set()

    def view_report(self):
        if self.has_changes():
            if not messagebox.askyesno(APP_TITLE, "Salve as alterações antes de gerar a consulta. Salvar agora?", parent=self):
                return
            if not self.save():
                return
        show_readonly_report(self, self.file, self.master.procedure_descriptions, self.original_apac_num)

    def has_changes(self):
        if self.file.lines != self.saved_lines:
            return True
        forms = [self.body_form] + [form for _, _, form in self.variable_forms]
        if self.header_form is not None:
            forms.append(self.header_form)
        if any(var.get() != form.original_values[key]
               for form in forms for key, var in form.entries.items()):
            return True
        selection = self.tree.selection()
        return bool(selection) and any(
            self.proc_vars[field.key].get() != extract_field(self.file.lines[int(selection[0])], field)
            for field in PROC_FIELDS if not field.read_only
        )

    def confirm_leave(self):
        if not self.has_changes():
            return True
        answer = messagebox.askyesnocancel(
            APP_TITLE, "Há alterações não salvas. Deseja salvar antes de continuar?\n"
            "Sim: salvar. Não: descartar. Cancelar: permanecer nesta APAC.", parent=self)
        if answer is None:
            return False
        if answer:
            return self.save()
        self.file.lines[:] = self.saved_lines
        return True

    def switch_apac(self, num):
        if num == self.original_apac_num or not self.confirm_leave():
            return
        EditorWindow(self.master, self.file, num)
        self.destroy()

    def close(self):
        if self.confirm_leave():
            self.destroy()
            self.master.deiconify()
            self.master.lift()

    def mark_saved(self):
        self.saved_lines = list(self.file.lines)
        self.apac_label.config(text=f"   APAC: {self.original_apac_num}")
        self.refresh_proc_tree()
        forms = [self.body_form] + [form for _, _, form in self.variable_forms]
        if self.header_form is not None:
            forms.append(self.header_form)
        for form in forms:
            for field in form.fields:
                value = extract_field(form.line_getter(), field)
                form.entries[field.key].set(value)
                form.original_values[field.key] = value
        self.on_proc_select()

    def _build_proc_tab(self):
        left = ttk.Frame(self.proc_frame)
        left.pack(side="left", fill="both", expand=True)
        right = ttk.LabelFrame(self.proc_frame, text="Editar procedimento selecionado", padding=8)
        right.pack(side="right", fill="y", padx=(8, 0))

        cols = ("n", "proc", "cbo", "qtd", "cidp", "cids", "srv", "clf", "cnes3")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=25)
        headings = {"n":"#", "proc":"Procedimento", "cbo":"CBO", "qtd":"Qtd", "cidp":"CID P", "cids":"CID S", "srv":"Serv.", "clf":"Class.", "cnes3":"CNES 3º"}
        widths = {"n":40, "proc":120, "cbo":80, "qtd":60, "cidp":70, "cids":70, "srv":60, "clf":60, "cnes3":85}
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="center")
        y = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(left, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self.proc_vars: dict[str, tk.StringVar] = {}
        for r, fld in enumerate(PROC_FIELDS):
            ttk.Label(right, text=fld.label).grid(row=r, column=0, sticky="w", padx=(0, 6), pady=2)
            var = tk.StringVar()
            self.proc_vars[fld.key] = var
            ent = ttk.Entry(right, textvariable=var, width=25)
            ent.grid(row=r, column=1, sticky="ew", pady=2)
            if fld.read_only:
                ent.state(["readonly"])
        ttk.Button(right, text="Aplicar ao procedimento", command=self.apply_proc_edit).grid(row=len(PROC_FIELDS), column=0, columnspan=2, sticky="ew", pady=(10, 2))
        right.columnconfigure(1, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self.on_proc_select)
        self.refresh_proc_tree()
        if self.indices["13"]:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self.on_proc_select()

    def refresh_proc_tree(self):
        sel = self.tree.selection()
        selected_iid = sel[0] if sel else None
        for item in self.tree.get_children():
            self.tree.delete(item)
        for order, idx in enumerate(self.indices["13"], start=1):
            line = self.file.lines[idx]
            vals = (
                order, line[21:31].strip(), line[31:37].strip(), line[37:44].strip(),
                line[64:68].strip() if len(line) >= 68 else "",
                line[68:72].strip() if len(line) >= 72 else "",
                line[72:75].strip() if len(line) >= 75 else "",
                line[75:78].strip() if len(line) >= 78 else "",
                line[90:97].strip() if len(line) >= 97 else "",
            )
            self.tree.insert("", "end", iid=str(idx), values=vals)
        if selected_iid and self.tree.exists(selected_iid):
            self.tree.selection_set(selected_iid)

    def on_proc_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        line = self.file.lines[idx]
        for fld in PROC_FIELDS:
            self.proc_vars[fld.key].set(extract_field(line, fld))

    def apply_proc_edit(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "Selecione um procedimento.", parent=self)
            return
        idx = int(sel[0])
        line = self.file.lines[idx]
        try:
            for fld in PROC_FIELDS:
                if fld.read_only:
                    continue
                line = set_field(line, fld, self.proc_vars[fld.key].get())
            self.file.lines[idx] = line
            self.refresh_proc_tree()
            messagebox.showinfo(APP_TITLE, "Alterações aplicadas ao procedimento.\nClique em 'Salvar alterações' para gravar no arquivo.", parent=self)
        except ValueError as e:
            messagebox.showerror(APP_TITLE, str(e), parent=self)

    def _apply_forms(self):
        # Cabeçalho
        if self.header_form is not None:
            self.file.lines[self.header_idx] = self.header_form.apply_to_line(self.file.lines[self.header_idx])

        # Corpo
        new_num = clean_apac_number(self.body_form.get("apa_num"))
        if len(new_num) != 13:
            raise ValueError("O número da APAC deve conter exatamente 13 dígitos.")
        if new_num != self.original_apac_num and new_num in self.file.all_apac_numbers():
            raise ValueError("Já existe outra APAC com esse número no arquivo.")

        self.file.lines[self.body_idx] = self.body_form.apply_to_line(self.file.lines[self.body_idx])

        # Variáveis
        for idx, typ, form in self.variable_forms:
            self.file.lines[idx] = form.apply_to_line(self.file.lines[idx])

        # Garante propagação do número se o usuário alterou o número da APAC.
        if new_num != self.original_apac_num:
            targets = [self.body_idx] + self.indices["13"] + [idx for idx, _, _ in self.variable_forms]
            for idx in targets:
                line = self.file.lines[idx]
                if len(line) < 21:
                    line = line.ljust(21)
                self.file.lines[idx] = line[:8] + new_num + line[21:]
            self.original_apac_num = new_num
            self.indices = self.file.find_apac_indices(new_num)
            self.title(f"{APP_TITLE} - APAC {new_num}")

    def save(self):
        before = list(self.file.lines)
        old_num = self.original_apac_num
        try:
            self.apply_proc_edit_silent()
            self._apply_forms()
            self.file.save()
            self.mark_saved()
            messagebox.showinfo(APP_TITLE, "Arquivo salvo com sucesso.\nFoi criado backup automático antes da primeira gravação.", parent=self)
            return True
        except Exception as e:
            self.file.lines[:] = before
            self.original_apac_num = old_num
            self.indices = self.file.find_apac_indices(old_num)
            messagebox.showerror(APP_TITLE, f"Não foi possível salvar:\n{e}", parent=self)
            return False

    def save_as(self):
        before = list(self.file.lines)
        old_num = self.original_apac_num
        try:
            target = filedialog.asksaveasfilename(parent=self, title="Salvar arquivo APAC como", initialdir=str(self.file.path.parent), initialfile=self.file.path.name, filetypes=[("Arquivo APAC", "*.*")])
            if not target:
                return
            self.apply_proc_edit_silent()
            self._apply_forms()
            self.file.save(Path(target))
            self.mark_saved()
            messagebox.showinfo(APP_TITLE, f"Arquivo salvo em:\n{target}", parent=self)
        except Exception as e:
            self.file.lines[:] = before
            self.original_apac_num = old_num
            self.indices = self.file.find_apac_indices(old_num)
            messagebox.showerror(APP_TITLE, f"Não foi possível salvar:\n{e}", parent=self)

    def apply_proc_edit_silent(self):
        # Se houver procedimento selecionado, aplica os valores que estão no painel lateral.
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        line = self.file.lines[idx]
        for fld in PROC_FIELDS:
            if fld.read_only:
                continue
            line = set_field(line, fld, self.proc_vars[fld.key].get())
        self.file.lines[idx] = line

    def open_other(self):
        num = simpledialog.askstring(APP_TITLE, "Digite o número da APAC (13 dígitos):", parent=self)
        if not num:
            return
        num = clean_apac_number(num)
        if len(num) != 13:
            messagebox.showerror(APP_TITLE, "Informe exatamente 13 dígitos.", parent=self)
            return
        if not self.file.find_apac_indices(num)["14"]:
            messagebox.showerror(APP_TITLE, "APAC não encontrada no arquivo.", parent=self)
            return
        self.switch_apac(num)


class StartApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("800x480")
        self.resizable(False, False)
        self.file: ApacFile | None = None
        self.procedure_descriptions = {}

        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_TITLE, font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 18))
        ttk.Label(frame, text="1. Selecione o arquivo de APAC (a extensão pode variar conforme a competência).", wraplength=660).pack(anchor="w")
        line = ttk.Frame(frame)
        line.pack(fill="x", pady=(5, 15))
        self.path_var = tk.StringVar()
        ttk.Entry(line, textvariable=self.path_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(line, text="Selecionar arquivo...", command=self.select_file).pack(side="left", padx=(8, 0))

        ttk.Label(frame, text="2. Pesquise pelo número da APAC ou navegue pelo arquivo:").pack(anchor="w")
        self.apac_var = tk.StringVar()
        ent = ttk.Entry(frame, textvariable=self.apac_var, width=25)
        ent.pack(anchor="w", pady=(5, 15))
        ent.bind("<Return>", lambda e: self.open_editor())

        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        ttk.Button(actions, text="Navegar pelo arquivo", command=self.browse_file).pack(side="left")
        ttk.Button(actions, text="Consultar APAC", command=self.open_editor).pack(side="right")

        ttk.Separator(frame).pack(fill="x", pady=16)
        ttk.Label(frame, text="Consulta no navegador — somente leitura", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Button(frame, text="Visualizar todas as APACs — Dados para digitação", command=self.view_all).pack(anchor="w", pady=(8, 6))
        tables = ttk.Frame(frame)
        tables.pack(fill="x")
        ttk.Button(tables, text="Recarregar Tabelas_Sigtap", command=self.reload_sigtap).pack(side="left")
        ttk.Button(tables, text="Importar tabela CSV...", command=self.import_descriptions).pack(side="left", padx=8)
        self.table_status = tk.StringVar(value="Tabela opcional: código e descrição dos procedimentos.")
        ttk.Label(frame, textvariable=self.table_status, wraplength=740).pack(anchor="w", pady=6)
        self.reload_sigtap()

    def reload_sigtap(self):
        directory = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        try:
            catalog = load_sigtap_folder(directory / "Tabelas_Sigtap")
            if catalog:
                self.procedure_descriptions = catalog
                months = ", ".join(f"{value[4:]}/{value[:4]}" for value in catalog.competences)
                self.table_status.set(f"SIGTAP: {len(catalog)} procedimentos por competência — {months}")
            else:
                self.procedure_descriptions = {}
                self.table_status.set("Coloque o pacote ZIP ou os TXT do SIGTAP em Tabelas_Sigtap e clique em Recarregar.")
        except Exception as exc:
            self.procedure_descriptions = {}
            self.table_status.set(f"Não foi possível carregar o SIGTAP: {exc}")

    def import_descriptions(self):
        path = filedialog.askopenfilename(parent=self, title="Tabela de procedimentos (codigo;descricao)",
                                          filetypes=[("Tabela CSV", "*.csv"), ("Todos os arquivos", "*.*")])
        if not path:
            return
        try:
            self.procedure_descriptions = load_descriptions(path)
            self.table_status.set(f"{len(self.procedure_descriptions)} descrições carregadas — {Path(path).name}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Não foi possível importar a tabela:\n{exc}", parent=self)

    def view_all(self):
        if self.file is None:
            messagebox.showwarning(APP_TITLE, "Selecione primeiro o arquivo de APAC.", parent=self)
            return
        show_readonly_report(self, self.file, self.procedure_descriptions)

    def browse_file(self):
        if self.file is None:
            messagebox.showwarning(APP_TITLE, "Selecione primeiro o arquivo de APAC.")
            return
        numbers = self.file.all_apac_numbers()
        if not numbers:
            messagebox.showwarning(APP_TITLE, "O arquivo não possui APACs para navegar.")
            return
        EditorWindow(self, self.file, numbers[0])

    def select_file(self):
        path = filedialog.askopenfilename(title="Selecione o arquivo APAC", filetypes=[("Arquivo APAC", "*.*")])
        if not path:
            return
        try:
            af = ApacFile(path)
            if not any(line.startswith("14") for line in af.lines):
                raise ValueError("O arquivo selecionado não possui registros 14 de APAC.")
            self.file = af
            self.path_var.set(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Não foi possível abrir o arquivo:\n{e}")

    def open_editor(self):
        if self.file is None:
            messagebox.showwarning(APP_TITLE, "Selecione primeiro o arquivo de APAC.")
            return
        num = clean_apac_number(self.apac_var.get())
        if len(num) != 13:
            messagebox.showwarning(APP_TITLE, "Informe o número da APAC com 13 dígitos.")
            return
        if not self.file.find_apac_indices(num)["14"]:
            messagebox.showerror(APP_TITLE, "APAC não encontrada no arquivo selecionado.")
            return
        EditorWindow(self, self.file, num)


def main():
    # Compartilha o módulo de layouts quando este arquivo é o ponto de entrada.
    sys.modules.setdefault("Editor_APAC", sys.modules[__name__])
    from apac_web import run
    run()


if __name__ == "__main__":
    main()
