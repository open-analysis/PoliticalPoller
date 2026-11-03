"""spider_runner.py: subprocess/browser orchestration, with everything external mocked."""
import json
import subprocess

import pytest

pytest.importorskip("playwright", reason="spider_runner imports utils, which needs playwright")
pytest.importorskip("playwright_stealth")
from bs4 import BeautifulSoup  # noqa: E402

import spider_runner as sr  # noqa: E402
from conftest import PKG, make_record  # noqa: E402


class FakeRun:
    """Stand-in for subprocess.run that writes JSONL where scrapy would."""

    def __init__(self, rows=(), returncode=0, stderr="", raises=None):
        self.rows, self.returncode, self.stderr, self.raises = list(rows), returncode, stderr, raises
        self.cmd = self.kwargs = None

    def __call__(self, cmd, **kwargs):
        self.cmd, self.kwargs = cmd, kwargs
        if self.raises:
            raise self.raises
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as f:
            for row in self.rows:
                f.write(json.dumps(row) + "\n")
            f.write("\n")  # trailing blank line must be tolerated
        return subprocess.CompletedProcess(cmd, self.returncode, "", self.stderr)


ARTICLES = [
    {"title": "Jane Doe leads Minnesota 2026 midterms poll", "url": "u1"},
    {"title": "Jane Doe rally in Iowa", "url": "u2"},
    {"title": "Weather today", "url": "u3"},
]


# ---------------------------------------------------------------- _article_matches
class TestArticleMatches:
    def test_no_filters_matches_everything(self):
        assert sr._article_matches({"title": "anything"})

    def test_case_insensitive_title_match(self):
        assert sr._article_matches({"title": "JANE DOE wins"}, candidate="jane doe")

    def test_all_filters_must_match(self):
        art = {"title": "Jane Doe in Minnesota"}
        assert sr._article_matches(art, candidate="Jane", location="Minnesota")
        assert not sr._article_matches(art, candidate="Jane", election="2026")

    def test_missing_or_none_title(self):
        assert not sr._article_matches({}, candidate="Jane")
        assert not sr._article_matches({"title": None}, candidate="Jane")
        assert sr._article_matches({"title": None})


# ---------------------------------------------------------------- run_news_spider
class TestRunNewsSpider:
    def test_command_and_cwd(self, monkeypatch):
        fake = FakeRun(ARTICLES)
        monkeypatch.setattr(sr.subprocess, "run", fake)
        sr.run_news_spider("cnn", project_dir="/proj", timeout=5)
        assert fake.cmd[:5] == ["scrapy", "crawl", "news", "-a", "site=cnn"]
        assert fake.kwargs["cwd"] == "/proj" and fake.kwargs["timeout"] == 5

    def test_returns_all_articles_without_filters(self, monkeypatch):
        monkeypatch.setattr(sr.subprocess, "run", FakeRun(ARTICLES))
        assert sr.run_news_spider("cnn") == ARTICLES

    def test_filters_are_applied(self, monkeypatch):
        monkeypatch.setattr(sr.subprocess, "run", FakeRun(ARTICLES))
        got = sr.run_news_spider("cnn", candidate="Jane Doe", location="Minnesota")
        assert [a["url"] for a in got] == ["u1"]

    def test_nonzero_exit_raises_with_stderr(self, monkeypatch):
        monkeypatch.setattr(sr.subprocess, "run", FakeRun(returncode=2, stderr="boom"))
        with pytest.raises(RuntimeError, match="boom"):
            sr.run_news_spider("cnn")

    def test_timeout_raises_runtime_error(self, monkeypatch):
        monkeypatch.setattr(sr.subprocess, "run", FakeRun(raises=subprocess.TimeoutExpired("scrapy", 1)))
        with pytest.raises(RuntimeError, match="did not finish"):
            sr.run_news_spider("cnn", timeout=1)


# ---------------------------------------------------------------- run_election_spider
class TestRunElectionSpider:
    def test_scrapy_path_for_open_sites(self, monkeypatch):
        rows = [make_record("Jo Park")]
        fake = FakeRun(rows)
        monkeypatch.setattr(sr.subprocess, "run", fake)
        got = sr.run_election_spider("example_open_state", project_dir=PKG)
        assert got == rows
        assert fake.cmd[:5] == ["scrapy", "crawl", "elections", "-a", "site=example_open_state"]

    def test_scrapy_failure_raises(self, monkeypatch):
        monkeypatch.setattr(sr.subprocess, "run", FakeRun(returncode=1, stderr="bad"))
        with pytest.raises(RuntimeError, match="bad"):
            sr.run_election_spider("example_open_state", project_dir=PKG)

    def test_scrapy_timeout_raises(self, monkeypatch):
        monkeypatch.setattr(sr.subprocess, "run", FakeRun(raises=subprocess.TimeoutExpired("scrapy", 1)))
        with pytest.raises(RuntimeError, match="did not finish"):
            sr.run_election_spider("example_open_state", project_dir=PKG)

    def test_browser_path_for_protected_sites(self, monkeypatch, mn_html):
        seen = {}

        def fake_fetch(url, headless=True, **kw):
            seen.update(url=url, headless=headless)
            return BeautifulSoup(mn_html, "html.parser")

        monkeypatch.setattr(sr, "fetch_soup_persistent_browser", fake_fetch)
        monkeypatch.setattr(sr.subprocess, "run", lambda *a, **k: pytest.fail("scrapy must not run"))
        got = sr.run_election_spider("mn", project_dir=PKG, headless=False)
        assert seen == {"url": "https://candidates.sos.mn.gov/", "headless": False}
        assert [(r["candidate_name"], r["office"]) for r in got] == [
            ("Jane Doe", "U.S. Senator"), ("John Roe", "U.S. Senator"), ("Jane Doe", "Governor")]
        assert all(r["site"] == "mn" and r["state"] == "Minnesota" and r["scraped_at"] for r in got)

    @pytest.mark.parametrize("override,expected", [(None, "table"), ("div#results", "div#results")])
    def test_the_sites_ready_selector_is_passed_to_the_browser(self, monkeypatch, mn_html, override, expected):
        import election_site_configs as esc
        seen = {}

        def fake_fetch(url, headless=True, **kw):
            seen.update(kw)
            return BeautifulSoup(mn_html, "html.parser")

        monkeypatch.setattr(sr, "fetch_soup_persistent_browser", fake_fetch)
        config = dict(esc.ELECTION_SITE_CONFIGS["mn"])
        if override:
            config["ready_selector"] = override
        else:
            config.pop("ready_selector", None)           # falls back to the "table" default
        monkeypatch.setitem(esc.ELECTION_SITE_CONFIGS, "mn", config)
        sr.run_election_spider("mn", project_dir=PKG)
        assert seen == {"ready_selector": expected}

    def test_unknown_site(self):
        with pytest.raises(ValueError, match="Unknown election site"):
            sr.run_election_spider("nope", project_dir=PKG)


# ---------------------------------------------------------------- sync_election_candidates
class TestSyncElectionCandidates:
    def stub(self, monkeypatch, batches):
        it = iter(batches)
        monkeypatch.setattr(sr, "run_election_spider", lambda *a, **k: next(it))

    def test_saves_and_summarizes(self, monkeypatch, store_dir, capsys):
        self.stub(monkeypatch, [[make_record("Jane Doe")]])
        summary = sr.sync_election_candidates("mn", project_dir=PKG, store_dir=store_dir)
        out = capsys.readouterr().out
        assert summary["new_candidates"] == ["Jane Doe"]
        assert "1 new candidates" in out and "+ Jane Doe" in out

    def test_prints_updates_collisions_and_review_flags(self, monkeypatch, store_dir, capsys):
        self.stub(monkeypatch, [
            [make_record("Al Kim", "Governor", party="DFL", website="https://a.com", file_date="05/01/2022")],
            [make_record("Al Kim", "Senator", party="GOP", website="https://a.com", file_date="05/01/2024")],
            [make_record("Pat Lee", "Governor"), make_record("Pat Lee", "Senator")],
        ])
        for _ in range(3):
            sr.sync_election_candidates("mn", project_dir=PKG, store_dir=store_dir)
        out = capsys.readouterr().out
        assert "» Al Kim -- Senator" in out
        assert "? review [party_changed]" in out
        assert "! possible same-name collision" in out
        assert "earlier review flag(s) still open" in out  # the party_changed flag, seen again on run 3

    def test_default_store_dir_is_used_when_none_given(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        self.stub(monkeypatch, [[make_record("Jane Doe")]])
        sr.sync_election_candidates("mn", project_dir=PKG)
        assert (tmp_path / "candidate_data" / "candidates_mn.json").exists()
