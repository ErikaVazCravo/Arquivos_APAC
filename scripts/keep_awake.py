"""Visita a tela inicial e desperta o Streamlit sem enviar arquivos APAC."""
import os
import re
import time
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright


def wait_for_app(page, timeout=240):
    deadline = time.monotonic() + timeout
    wake_clicked = False
    while time.monotonic() < deadline:
        # Community Cloud pode envolver o aplicativo em um iframe.
        for frame in list(page.frames):
            try:
                title = frame.get_by_role("heading", name="Editor APAC", exact=True)
                uploader = frame.get_by_text("Abrir arquivo APAC", exact=True)
                if title.is_visible() and uploader.first.is_visible():
                    print("Editor APAC carregado e disponível.", flush=True)
                    return
                wake = frame.get_by_role("button", name=re.compile(r"Yes, get this app back up", re.I))
                if not wake_clicked and wake.first.is_visible():
                    wake.first.click(timeout=10000)
                    wake_clicked = True
                    print("Despertar solicitado. Aguardando o aplicativo.", flush=True)
            except Error:
                # O iframe pode ser substituído durante o despertar.
                continue
        page.wait_for_timeout(2000)
    raise TimeoutError("Não foi possível confirmar a tela do Editor APAC no prazo esperado.")


def visit(url, timeout=240):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".streamlit.app"):
        raise ValueError("Configure STREAMLIT_APP_URL com o endereço HTTPS do app em streamlit.app.")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            wait_for_app(page, timeout)
        finally:
            browser.close()


if __name__ == "__main__":
    visit(os.environ.get("STREAMLIT_APP_URL", "").strip())
