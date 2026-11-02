"""site_reader.py: read_page() dispatch and find_politician() cache/refresh logic."""
import json

import pytest

pytest.importorskip("playwright", reason="site_reader imports utils, which needs playwright")
pytest.importorskip("playwright_stealth")
from bs4 import BeautifulSoup  # noqa: E402

import candidate_store  # noqa: E402
import site_reader as sr  # noqa: E402
from conftest import PKG, make_record  # noqa: E402


# ---------------------------------------------------------------- read_page
class TestReadPage:
    @pytest.fixture
    def fetchers(self, monkeypatch, mn_html):
        calls = []

        def make(name):
            def fetch(*args, **kwargs):
                calls.append((name, args, kwargs))
                return BeautifulSoup(mn_html, "html.parser")
            return fetch

        monkeypatch.setattr(sr, "fetch_soup_persistent_browser", make("persistent_browser"))
        monkeypatch.setattr(sr, "fetch_soup_playwright", make("playwright"))
        monkeypatch.setattr(sr, "fetch_soup", make("requests"))
        return calls

    @pytest.mark.parametrize("method", ["persistent_browser", "playwright", "requests"])
    def test_dispatches_to_the_chosen_fetcher(self, fetchers, method):
        sr.read_page("https://candidates.sos.mn.gov/", method=method)
        assert [c[0] for c in fetchers] == [method]

    def test_default_method_is_the_persistent_browser(self, fetchers):
        sr.read_page("https://candidates.sos.mn.gov/")
        assert fetchers[0][0] == "persistent_browser"

    def test_headless_and_profile_dir_are_forwarded(self, fetchers):
        sr.read_page("https://x.gov/", headless=False, user_data_dir="/tmp/prof")
        _, args, kwargs = fetchers[0]
        assert kwargs == {"user_data_dir": "/tmp/prof", "headless": False}

    def test_returns_grouped_candidates(self, fetchers):
        grouped = sr.read_page("https://candidates.sos.mn.gov/", method="requests")
        assert [c["name"] for c in grouped["Federal Offices"]["U.S. Senator"]] == ["Jane Doe", "John Roe"]
        assert grouped["State Offices"]["Governor"][0]["file_date"] == "06/01/2026"

    @pytest.mark.parametrize("method", ["cached_session", "bogus"])
    def test_unknown_methods_are_rejected(self, fetchers, method):
        with pytest.raises(ValueError, match="Unknown method"):
            sr.read_page("https://x.gov/", method=method)
        assert fetchers == []


# ---------------------------------------------------------------- _print_candidate_matches
def test_print_candidate_matches_emits_one_json_block_per_office(capsys):
    match = {"candidate_name": "Jane Doe", "offices": {
        "Governor": {"office_level": "State", "party": "DFL", "website": "w", "file_date": "d"},
        "Senator": {"office_level": "Fed", "party": "DFL", "website": "w", "file_date": "d"}}}
    sr._print_candidate_matches([match])
    out = capsys.readouterr().out
    decoder, idx, blocks = json.JSONDecoder(), 0, []
    while idx < len(out):
        while idx < len(out) and out[idx].isspace():
            idx += 1
        if idx >= len(out):
            break
        obj, idx = decoder.raw_decode(out, idx)
        blocks.append(obj)
    assert [b["office"] for b in blocks] == ["Governor", "Senator"]
    assert all(b["candidate_name"] == "Jane Doe" for b in blocks)


# ---------------------------------------------------------------- find_politician
class TestFindPolitician:
    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)  # find_politician writes candidate_results_<date>.json to the cwd

    def seed(self, store_dir, *names):
        candidate_store.upsert_candidates("mn", [make_record(n) for n in names], store_dir=store_dir)

    def no_scrape(self, monkeypatch):
        monkeypatch.setattr(sr, "sync_election_candidates",
                            lambda *a, **k: pytest.fail("must not scrape when the cache answers"))

    def test_cache_hit_skips_the_live_scrape(self, monkeypatch, store_dir, capsys):
        self.seed(store_dir, "Jane Doe")
        self.no_scrape(monkeypatch)
        matches = sr.find_politician("jane", project_dir=PKG, store_dir=store_dir)
        assert [m["candidate_name"] for m in matches] == ["Jane Doe"]
        assert "cached match" in capsys.readouterr().out

    def test_cache_hit_writes_no_results_file(self, monkeypatch, store_dir, tmp_path):
        self.seed(store_dir, "Jane Doe")
        self.no_scrape(monkeypatch)
        sr.find_politician("jane", project_dir=PKG, store_dir=store_dir)
        assert list(tmp_path.glob("candidate_results_*.json")) == []

    def test_cache_miss_scrapes_then_saves_results(self, monkeypatch, store_dir, tmp_path):
        calls = {}

        def fake_sync(site, project_dir=None, store_dir=None, headless=None):
            calls.update(site=site, headless=headless)
            return candidate_store.upsert_candidates(site, [make_record("Jane Doe")], store_dir=store_dir)

        monkeypatch.setattr(sr, "sync_election_candidates", fake_sync)
        matches = sr.find_politician("Jane", site="mn", project_dir=PKG, store_dir=store_dir, headless=True)
        assert calls == {"site": "mn", "headless": True}
        assert [m["candidate_name"] for m in matches] == ["Jane Doe"]
        (results,) = tmp_path.glob("candidate_results_*.json")
        assert json.loads(results.read_text())[0]["candidate_name"] == "Jane Doe"

    def test_force_refresh_ignores_the_cache(self, monkeypatch, store_dir):
        self.seed(store_dir, "Jane Doe")
        scraped = []

        def fake_sync(site, **kw):
            scraped.append(site)
            return candidate_store.upsert_candidates(site, [make_record("Jane Doe")], store_dir=kw["store_dir"])

        monkeypatch.setattr(sr, "sync_election_candidates", fake_sync)
        sr.find_politician("Jane", project_dir=PKG, store_dir=store_dir, force_refresh=True)
        assert scraped == ["mn"]

    def test_no_match_anywhere_returns_empty_and_writes_nothing(self, monkeypatch, store_dir, tmp_path, capsys):
        monkeypatch.setattr(
            sr, "sync_election_candidates",
            lambda site, **kw: candidate_store.upsert_candidates(site, [make_record("Someone Else")],
                                                                 store_dir=kw["store_dir"]))
        assert sr.find_politician("Nobody", project_dir=PKG, store_dir=store_dir) == []
        assert "No candidate matching" in capsys.readouterr().out
        assert list(tmp_path.glob("candidate_results_*.json")) == []
