"use strict";
const $ = id => document.getElementById(id);
let state = {apacs: [], version: 0}, detail = null, changes = {}, section = "body", procedureIndex = null;
let busy = false, closed = false, report = null;
const normalize = value => String(value).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const month = value => /^\d{6}$/.test(value) ? `${value.slice(4)}/${value.slice(0, 4)}` : value;
const dirty = () => Object.keys(changes).length > 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function message(text, error = false) {
  $("message").textContent = text;
  $("message").className = error ? "error" : "";
  $("message").hidden = !text;
}
async function api(path, payload) {
  const options = payload === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-APAC-Request": "1"}, body: JSON.stringify(payload)};
  let response;
  try { response = await fetch(`api/${path}`, options); }
  catch { throw new Error("Não foi possível conectar ao editor. Abra o Editor_APAC.exe novamente."); }
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Não foi possível concluir a operação.");
  return data;
}
async function work(text, callback) {
  if (busy || closed) return;
  busy = true; $("busy-text").textContent = text; $("busy").hidden = false;
  try { return await callback(); }
  catch (error) { message(error.message, true); return false; }
  finally { busy = false; $("busy").hidden = true; }
}
function updateDirty() {
  $("dirty-status").textContent = dirty() ? "Alterações não salvas" : "Sem alterações pendentes";
  $("dirty-status").classList.toggle("dirty", dirty());
  $("save").disabled = !dirty();
}
function valueFor(record, field) {
  return changes[record.index]?.[field.key] ?? field.value;
}
function updateField(record, field, value) {
  if (value === field.value) {
    if (changes[record.index]) {
      delete changes[record.index][field.key];
      if (!Object.keys(changes[record.index]).length) delete changes[record.index];
    }
  } else {
    changes[record.index] ||= {};
    changes[record.index][field.key] = value;
  }
  updateDirty();
}
function applyState(next) {
  state = next;
  $("table-status").textContent = state.table_status;
  $("file-name").textContent = state.filename;
  $("file-name").title = state.path;
  $("total-count").textContent = state.apacs.length;
  $("empty-state").hidden = state.apacs.length > 0;
  renderList();
}
function renderList() {
  const query = normalize($("search").value).trim();
  const rows = state.apacs.filter(row => normalize(`${row.number} ${row.patient} ${row.cnes} ${month(row.competence)}`).includes(query));
  $("result-count").textContent = `${rows.length} de ${state.apacs.length} APAC(s)`;
  $("apac-list").replaceChildren();
  for (const row of rows) {
    const button = element("button", undefined, "apac-card");
    button.classList.toggle("active", row.index === detail?.body_index);
    button.setAttribute("aria-pressed", String(row.index === detail?.body_index));
    button.append(element("strong", row.patient || row.number), element("span", row.number), element("small", `Competência ${month(row.competence)}`));
    button.addEventListener("click", () => navigate(row.index));
    $("apac-list").append(button);
  }
  if (!rows.length) $("apac-list").append(element("p", "Nenhuma APAC encontrada.", "hint"));
}
function renderHeading() {
  const position = state.apacs.findIndex(row => row.index === detail.body_index);
  const row = state.apacs[position];
  $("position").textContent = `APAC ${position + 1} de ${state.apacs.length}`;
  $("patient-name").textContent = row.patient || "Dados da APAC";
  $("apac-number").textContent = `Número ${row.number}`;
  $("record-competence").textContent = `Competência ${month(row.competence)}`;
  $("first").disabled = $("previous").disabled = position === 0;
  $("last").disabled = $("next").disabled = position === state.apacs.length - 1;
}
function formCard(record, title) {
  const card = element("section", undefined, "form-card");
  card.append(element("h3", title || record.title));
  const grid = element("div", undefined, "field-grid");
  for (const field of record.fields) {
    const wrapper = element("div", undefined, "field");
    const label = element("label", field.label);
    const id = `field-${record.index}-${field.key}`;
    label.htmlFor = id;
    const input = document.createElement("input");
    input.id = id; input.type = "text"; input.value = valueFor(record, field);
    input.maxLength = field.size; input.readOnly = field.read_only; input.autocomplete = "off";
    input.spellcheck = false;
    if (field.kind === "NUM") input.inputMode = "numeric";
    input.addEventListener("input", () => updateField(record, field, input.value));
    const hint = element("small", field.desc || `${field.size} caracteres`, "field-hint");
    hint.id = `${id}-hint`; input.setAttribute("aria-describedby", hint.id);
    wrapper.append(label, input, hint); grid.append(wrapper);
  }
  card.append(grid); return card;
}
function renderProcedures(area) {
  const records = detail.records.filter(record => record.type === "13");
  const card = element("section", undefined, "form-card");
  card.append(element("h3", `Procedimentos (${records.length})`));
  if (!records.length) { card.append(element("p", "")); area.append(card); return; }
  if (!records.some(record => record.index === procedureIndex)) procedureIndex = records[0].index;
  const scroll = element("div", undefined, "table-scroll"), table = element("table"), head = element("thead"), header = element("tr");
  for (const label of ["#", "Procedimento", "Descrição", "CBO", "Qtd.", ""]) header.append(element("th", label));
  head.append(header); table.append(head);
  const body = element("tbody");
  records.forEach((record, index) => {
    const get = key => { const field = record.fields.find(item => item.key === key); return valueFor(record, field); };
    const row = element("tr"); row.classList.toggle("selected", record.index === procedureIndex);
    const originalCode = record.fields.find(field => field.key === "pap_codproc").value;
    const description = get("pap_codproc") === originalCode ? record.description : "";
    [index + 1, get("pap_codproc"), description, get("pap_cbo"), get("pap_qtdprod")].forEach(value => row.append(element("td", value)));
    const cell = element("td"), edit = element("button", "Editar");
    edit.setAttribute("aria-label", `Editar procedimento ${index + 1}`);
    edit.addEventListener("click", () => { procedureIndex = record.index; renderForms(); });
    cell.append(edit); row.append(cell); body.append(row);
  });
  table.append(body); scroll.append(table); card.append(scroll); area.append(card);
  const selected = records.find(record => record.index === procedureIndex);
  area.append(formCard(selected, `Editar procedimento ${records.indexOf(selected) + 1}`));
}
function renderForms() {
  const area = $("form-area"); area.replaceChildren();
  document.querySelectorAll("[data-section]").forEach(button => button.classList.toggle("active", button.dataset.section === section));
  if (section === "procedures") { renderProcedures(area); return; }
  const matches = detail.records.filter(record => section === "body" ? record.type === "14" : section === "header" ? record.type === "01" : !["01", "13", "14"].includes(record.type));
  matches.forEach(record => area.append(formCard(record)));
  if (!matches.length) area.append(element("section", "", "form-card"));
}
async function loadDetail(index) {
  const next = await api(`detail?index=${index}`);
  if (next.version !== state.version) throw new Error("O arquivo mudou em outra aba. Recarregue a página.");
  detail = next; changes = {}; procedureIndex = null;
  renderHeading(); renderList(); renderForms(); updateDirty();
}
function choose(dialog) {
  return new Promise(resolve => {
    dialog.returnValue = "cancel";
    const click = event => {
      const choice = event.target.closest("[data-choice]");
      if (choice) dialog.close(choice.dataset.choice);
    };
    dialog.addEventListener("click", click);
    dialog.addEventListener("close", () => { dialog.removeEventListener("click", click); resolve(dialog.returnValue); }, {once: true});
    dialog.showModal();
  });
}
async function saveDirect(saveAs = false) {
  const index = detail.body_index;
  const result = await api("save", {version: state.version, body_index: index, changes, save_as: saveAs});
  if (result.cancelled) return false;
  applyState(result); report = null; await loadDetail(index);
  message("Arquivo salvo com sucesso."); return true;
}
async function leave() {
  if (!dirty()) return true;
  // O diálogo fica acima da camada de espera.
  $("busy").hidden = true;
  const choice = await choose($("leave-dialog"));
  $("busy").hidden = !busy;
  if (choice === "save") return saveDirect();
  if (choice === "discard") { changes = {}; renderForms(); updateDirty(); return true; }
  return false;
}
async function navigate(index) {
  if (detail?.body_index === index) return;
  await work("Abrindo APAC…", async () => { if (await leave()) { await loadDetail(index); message(""); } });
}
function showEditor() {
  $("report-panel").hidden = true; $("editor-layout").hidden = !state.apacs.length;
  $("empty-state").hidden = state.apacs.length > 0;
  $("editor-view").classList.add("active"); $("editor-view").setAttribute("aria-current", "page");
  $("report-view").classList.remove("active"); $("report-view").removeAttribute("aria-current");
}
async function openFile() {
  await work("Selecione o arquivo na janela de abertura…", async () => {
    if (!await leave()) return;
    const result = await api("open", {});
    if (result.cancelled) return;
    applyState(result); report = null; section = "body"; $("search").value = "";
    await loadDetail(state.apacs[0].index); showEditor(); message("");
  });
}
async function showReport(all = false) {
  if (!state.apacs.length) { message("Abra um arquivo APAC para visualizar as fichas."); return; }
  await work("Preparando as fichas para consulta…", async () => {
    if (!await leave()) return;
    report = await api("report", {});
    const position = state.apacs.findIndex(row => row.index === detail.body_index);
    const page = all ? "index.html" : report.pages[position];
    $("report-frame").src = `reports/${report.directory}/${page}`;
    $("editor-layout").hidden = true; $("empty-state").hidden = true; $("report-panel").hidden = false;
    $("editor-view").classList.remove("active"); $("editor-view").removeAttribute("aria-current");
    $("report-view").classList.add("active"); $("report-view").setAttribute("aria-current", "page");
    message("");
  });
}
$("open-file").addEventListener("click", openFile); $("open-empty").addEventListener("click", openFile);
$("search").addEventListener("input", renderList);
$("save").addEventListener("click", () => work("Salvando arquivo…", () => saveDirect()));
$("save-as").addEventListener("click", () => work("Escolha onde salvar o arquivo…", () => saveDirect(true)));
for (const direction of ["first", "previous", "next", "last"]) {
  $(direction).addEventListener("click", () => {
    const position = state.apacs.findIndex(row => row.index === detail.body_index);
    const target = {first: 0, previous: position - 1, next: position + 1, last: state.apacs.length - 1}[direction];
    if (state.apacs[target]) navigate(state.apacs[target].index);
  });
}
document.querySelectorAll("[data-section]").forEach(button => button.addEventListener("click", () => { section = button.dataset.section; renderForms(); }));
$("editor-view").addEventListener("click", showEditor); $("back-editor").addEventListener("click", showEditor);
$("report-view").addEventListener("click", () => showReport()); $("all-reports").addEventListener("click", () => showReport(true));
for (const [id, route] of [["reload-tables", "reload-tables"], ["import-table", "import-table"]]) {
  $(id).addEventListener("click", () => work("Carregando descrições…", async () => {
    if (!await leave()) return;
    const result = await api(route, {});
    if (result.cancelled) return;
    applyState(result); report = null;
    if (detail) await loadDetail(detail.body_index);
    showEditor(); message("Tabela de procedimentos atualizada.");
  }));
}
$("quit").addEventListener("click", () => work("Encerrando…", async () => {
  if (!await leave()) return;
  $("busy").hidden = true;
  if (await choose($("quit-dialog")) !== "quit") return;
  await api("quit", {}); closed = true;
  document.querySelectorAll("button, input").forEach(node => { node.disabled = true; });
  $("report-panel").hidden = true; $("editor-layout").hidden = true; $("empty-state").hidden = true;
  message("Editor encerrado. Você pode fechar esta aba. Para usar novamente, abra o Editor_APAC.exe.");
}));
window.addEventListener("beforeunload", event => { if (dirty() && !closed) { event.preventDefault(); event.returnValue = ""; } });
work("Abrindo editor…", async () => {
  applyState(await api("state"));
  if (state.apacs.length) await loadDetail(state.apacs[0].index);
  showEditor();
});
