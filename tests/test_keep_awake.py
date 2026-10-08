"""Verificação da automação em páginas locais, sem depender do Community Cloud."""
import unittest

try:
    from playwright.sync_api import sync_playwright
    from scripts.keep_awake import wait_for_app, visit
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Playwright disponível no workflow keep-awake")
class KeepAwakeTests(unittest.TestCase):
    def setUp(self):
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page()

    def test_awake_app_inside_iframe(self):
        self.page.set_content('<iframe srcdoc="<h1>Editor APAC</h1><label>Abrir arquivo APAC</label>"></iframe>')
        wait_for_app(self.page, timeout=5)

    def test_sleep_button_is_clicked_and_app_is_confirmed(self):
        self.page.set_content('''
            <button onclick="document.body.innerHTML = '<iframe srcdoc=&quot;&lt;h1&gt;Editor APAC&lt;/h1&gt;&lt;label&gt;Abrir arquivo APAC&lt;/label&gt;&quot;></iframe>'">
            Yes, get this app back up!</button>
        ''')
        wait_for_app(self.page, timeout=5)
        self.assertEqual(self.page.get_by_role("button").count(), 0)

    def test_wrong_page_does_not_report_success(self):
        self.page.set_content('<h1>Downloads Sistemas</h1>')
        with self.assertRaises(TimeoutError):
            wait_for_app(self.page, timeout=.1)

    def test_invalid_destination_is_rejected(self):
        for url in ["", "http://example.streamlit.app", "https://example.com"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                visit(url)
