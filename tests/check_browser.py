"""QA opcional com Selenium: executar apenas contra tests/preview_web.py."""
from pathlib import Path
import subprocess
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


url = sys.argv[1]
driver_path = sys.argv[2] if len(sys.argv) > 2 else None
output = Path(__file__).resolve().parents[1] / "build" / "qa_web"
output.mkdir(parents=True, exist_ok=True)
options = webdriver.ChromeOptions()
options.add_argument("--headless=new")
options.add_argument("--window-size=1440,1100")
options.add_argument("--disable-gpu")
options.add_argument("--no-first-run")
options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
service = Service(executable_path=driver_path) if driver_path else Service()
service.creation_flags = subprocess.CREATE_NO_WINDOW
browser = webdriver.Chrome(service=service, options=options)
wait = WebDriverWait(browser, 20)


def find(identifier):
    return browser.find_element(By.ID, identifier)


def idle():
    wait.until(EC.invisibility_of_element_located((By.ID, "busy")))


def click(identifier):
    wait.until(EC.element_to_be_clickable((By.ID, identifier))).click()


def fill(identifier, value):
    node = find(identifier)
    node.clear()
    node.send_keys(value)


try:
    browser.get(url)
    idle()
    assert "active" in find("editor-view").get_attribute("class")
    assert find("empty-state").is_displayed()
    browser.save_screenshot(str(output / "inicio.png"))
    click("open-file")
    idle()
    assert len(browser.find_elements(By.CSS_SELECTOR, ".apac-card")) == 2
    assert find("patient-name").text == "PACIENTE EXEMPLO A"
    fill("field-1-apa_nomepcnte", "PACIENTE EDITADO WEB")
    click("next")
    wait.until(EC.visibility_of_element_located((By.ID, "leave-dialog")))
    browser.find_element(By.CSS_SELECTOR, '#leave-dialog [data-choice="cancel"]').click()
    idle()
    assert find("field-1-apa_nomepcnte").get_attribute("value") == "PACIENTE EDITADO WEB"
    click("report-view")
    wait.until(EC.visibility_of_element_located((By.ID, "leave-dialog")))
    browser.find_element(By.CSS_SELECTOR, '#leave-dialog [data-choice="save"]').click()
    idle()
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "report-frame")))
    wait.until(lambda d: "PACIENTE EDITADO WEB" in d.find_element(By.TAG_NAME, "body").text)
    assert not browser.find_elements(By.CSS_SELECTOR, "input,textarea,select,[contenteditable]")
    assert "PUNÇÃO DE MAMA POR AGULHA GROSSA" in browser.find_element(By.TAG_NAME, "body").text
    assert "Não disponível" not in browser.find_element(By.TAG_NAME, "body").text
    browser.switch_to.default_content()
    browser.save_screenshot(str(output / "consulta.png"))
    click("back-editor")
    browser.find_element(By.CSS_SELECTOR, '[data-section="procedures"]').click()
    fill("field-2-pap_qtdprod", "4")
    browser.find_element(By.CSS_SELECTOR, '[data-section="body"]').click()
    browser.find_element(By.CSS_SELECTOR, '[data-section="procedures"]').click()
    assert find("field-2-pap_qtdprod").get_attribute("value") == "4"
    click("save")
    idle()
    assert find("field-2-pap_qtdprod").get_attribute("value") == "0000004"
    fill("search", "EXEMPLO B")
    assert len(browser.find_elements(By.CSS_SELECTOR, ".apac-card")) == 1
    browser.find_element(By.CSS_SELECTOR, ".apac-card").click()
    idle()
    assert find("patient-name").text == "PACIENTE EXEMPLO B"
    fill("search", "")
    click("first")
    idle()
    click("save-as")
    idle()
    assert find("file-name").text == "COPIA_FICTICIA.AGO"
    browser.find_element(By.CSS_SELECTOR, '[data-section="body"]').click()
    browser.save_screenshot(str(output / "editor.png"))
    browser.set_window_size(680, 1000)
    assert browser.execute_script("return document.documentElement.scrollWidth <= window.innerWidth")
    browser.save_screenshot(str(output / "editor_estreito.png"))
    browser.set_window_size(1440, 1100)
    click("report-view")
    idle()
    click("all-reports")
    idle()
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "report-frame")))
    wait.until(EC.visibility_of_element_located((By.ID, "search")))
    fill("search", "EXEMPLO B")
    assert "1 APAC(s)" in find("count").text
    browser.switch_to.default_content()
    failures = [entry for entry in browser.get_log("browser") if entry["level"] == "SEVERE"]
    assert not failures, failures
    print("OK: abertura, edicao, cancelar, salvar, navegacao, busca, procedimentos, salvar como, consulta somente leitura, SIGTAP e tela estreita.", flush=True)
finally:
    browser.quit()
