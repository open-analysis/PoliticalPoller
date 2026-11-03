"""probe_site.py: the tool for checking a config against a real page."""
import json
import os

import pytest

import probe_site

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def read(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


class TestProbeHtml:
    def test_reports_records_and_samples(self):
        report = probe_site.probe_html("ky", read("ky_candidate_list.html"), url="u", show=2)
        assert report["records"] == 4 and len(report["sample"]) == 2
        assert report["verification"] == "layout_observed" and report["diagnostics"] == []
        assert report["tables"][0]["first_row"][0] == "Name / Running Mate"

    def test_no_table_suggests_the_browser(self):
        report = probe_site.probe_html("ky", "<html><div id='app'></div></html>")
        assert report["records"] == 0
        assert any("JavaScript" in d and "--browser" in d for d in report["diagnostics"])

    def test_captcha_pages_are_recognised(self):
        report = probe_site.probe_html("ky", "<html><p>Please complete the CAPTCHA</p></html>")
        assert any("CAPTCHA" in d for d in report["diagnostics"])

    def test_tables_without_matching_headers_list_the_labels_seen(self):
        report = probe_site.probe_html("ky", "<table><tr><th>Aspirant</th><th>Seat</th></tr><tr><td>A</td><td>B</td></tr></table>")
        (diag,) = [d for d in report["diagnostics"] if "header labels" in d.lower()]
        assert "Aspirant" in diag and "header_aliases" in diag

    def test_missing_office_column_is_called_out(self):
        html = "<table><tr><th>Name</th><th>Party</th></tr><tr><td>A B</td><td>X</td></tr></table>"
        report = probe_site.probe_html("ky", html)
        assert report["records"] == 1 and any("no office" in d for d in report["diagnostics"])

    def test_paged_pages_are_called_out(self):
        report = probe_site.probe_html("wa", read("wa_candidate_list.html"))
        assert report["records"] == 6
        assert any("215 items over 3 pages" in d for d in report["diagnostics"])

    def test_unknown_site_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown election site"):
            probe_site.probe_html("nope", "<html></html>")


class TestFetchHtml:
    def test_plain_fetch_uses_requests(self, monkeypatch):
        import requests
        seen = {}

        class Resp:
            text = "<html>ok</html>"
            def raise_for_status(self): pass

        monkeypatch.setattr(requests, "get", lambda url, headers=None, timeout=None: seen.update(url=url, headers=headers) or Resp())
        assert probe_site.fetch_html("https://a.test/x") == "<html>ok</html>"
        assert seen["url"] == "https://a.test/x" and "User-Agent" in seen["headers"]

    def test_http_errors_propagate(self, monkeypatch):
        import requests

        class Resp:
            text = ""
            def raise_for_status(self): raise requests.HTTPError("403")

        monkeypatch.setattr(requests, "get", lambda *a, **k: Resp())
        with pytest.raises(requests.HTTPError):
            probe_site.fetch_html("https://a.test/")


class TestCli:
    def fixture_path(self, name):
        return os.path.join(FIXTURES, name)

    def test_html_file_mode_prints_json_and_exits_zero(self, capsys):
        code = probe_site.main(["sd", "--html", self.fixture_path("sd_candidate_list.html")])
        out = json.loads(capsys.readouterr().out)
        assert code == 0 and out["records"] == 4 and out["site"] == "sd"

    def test_exit_status_is_nonzero_when_nothing_parses(self, tmp_path, capsys):
        empty = tmp_path / "empty.html"
        empty.write_text("<html></html>")
        assert probe_site.main(["sd", "--html", str(empty)]) == 1
        assert json.loads(capsys.readouterr().out)["diagnostics"]

    def test_default_url_is_the_first_start_url_and_save_writes_the_html(self, monkeypatch, tmp_path, capsys):
        fetched = {}
        monkeypatch.setattr(probe_site, "fetch_html",
                            lambda url, browser=False, headless=True: fetched.update(url=url, browser=browser) or read("sd_candidate_list.html"))
        saved = tmp_path / "page.html"
        assert probe_site.main(["sd", "--save", str(saved)]) == 0
        assert fetched == {"url": "https://vip.sdsos.gov/candidatelist.aspx?eid=774", "browser": False}
        assert "Kai Example" in saved.read_text()

    def test_browser_is_used_for_browser_only_sites_and_when_asked(self, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(probe_site, "fetch_html",
                            lambda url, browser=False, headless=True: calls.append((browser, headless)) or "<html></html>")
        probe_site.main(["mn"])                              # requires_browser site
        probe_site.main(["sd", "--browser", "--headed"])
        assert calls == [(True, True), (True, False)]
