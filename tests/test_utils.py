"""utils.py: HTML parsing helpers, block detection, and the requests fetcher.

The Playwright-based fetchers (fetch_soup_persistent_browser /
fetch_soup_playwright) need a real browser and are not unit-tested here.
"""
import pytest
from bs4 import BeautifulSoup

pytest.importorskip("playwright", reason="utils.py imports playwright at module load")
pytest.importorskip("playwright_stealth", reason="utils.py imports playwright_stealth at module load")

import utils  # noqa: E402


def td(html):
    return BeautifulSoup(f"<table><tr>{html}</tr></table>", "html.parser").find("td")


# ---------------------------------------------------------------- cell helpers
class TestCellHelpers:
    def test_cell_text_strips(self):
        assert utils._cell_text(td("<td>  hello \n</td>")) == "hello"

    def test_cell_text_none(self):
        assert utils._cell_text(None) == ""

    @pytest.mark.parametrize("html,expected", [
        ('<td><a href="https://a.com">link</a></td>', "https://a.com"),
        ('<td><a href="  https://a.com  ">link</a></td>', "https://a.com"),
        ('<td><a href="javascript:void(0)">visit</a></td>', "visit"),
        ('<td><a href="JavaScript:x()"></a></td>', ""),
        ('<td><a href="http://">here</a></td>', "here"),
        ('<td><a href="">here</a></td>', "here"),
        ("<td>plain.com</td>", "plain.com"),
        ("<td></td>", ""),
    ])
    def test_extract_website(self, html, expected):
        assert utils._extract_website(td(html)) == expected

    def test_extract_website_none(self):
        assert utils._extract_website(None) == ""

    @pytest.mark.parametrize("attr,expected", [('colspan="5"', 5), ("", 1), ('colspan="x"', 1), ('colspan=""', 1)])
    def test_colspan(self, attr, expected):
        assert utils._colspan(td(f"<td {attr}></td>")) == expected


# ---------------------------------------------------------------- parse_candidates / group_by_office
class TestParseCandidates:
    def parse(self, html):
        return utils.parse_candidates(BeautifulSoup(html, "html.parser"))

    def test_levels_offices_and_candidates(self, mn_html):
        recs = self.parse(mn_html)
        assert [(r["level"], r["office"], r["name"]) for r in recs] == [
            ("Federal Offices", "U.S. Senator", "Jane Doe"),
            ("Federal Offices", "U.S. Senator", "John Roe"),
            ("State Offices", "Governor", "Jane Doe"),
        ]

    def test_record_fields(self, mn_html):
        rec = self.parse(mn_html)[0]
        assert rec == {"level": "Federal Offices", "office": "U.S. Senator", "name": "Jane Doe",
                       "party": "DFL", "website": "https://janedoe.com", "file_date": "05/26/2026"}

    def test_header_and_nameless_rows_skipped(self, mn_html):
        assert all(r["name"] not in ("", "Candidate Name") for r in self.parse(mn_html))

    def test_rows_before_any_header_get_none_level_and_office(self):
        recs = self.parse('<table><tr><td colspan="2"></td><td>Zed</td><td>GRN</td><td>w.com</td><td>1/1/26</td></tr></table>')
        assert [(r["level"], r["office"], r["name"]) for r in recs] == [(None, None, "Zed")]

    def test_empty_and_unrelated_pages(self):
        assert self.parse("<html></html>") == []
        assert self.parse("<p>nothing here</p>") == []

    def test_agrees_with_the_shared_parser(self, mn_html):
        """utils.parse_candidates is a legacy copy of the colspan parser; they should not drift apart."""
        from parsel import Selector
        import election_table_parsers as ep
        legacy = [(r["level"], r["office"], r["name"], r["party"], r["website"], r["file_date"])
                  for r in self.parse(mn_html)]
        shared = [(r["office_level"], r["office"], r["candidate_name"], r["party"], r["website"], r["file_date"])
                  for r in ep.parse_table(Selector(text=mn_html), "colspan_hierarchy", {})]
        assert legacy == shared


class TestGroupByOffice:
    def test_nested_grouping(self):
        recs = [
            {"level": "Fed", "office": "Senator", "name": "A", "party": "X", "website": "w", "file_date": "d"},
            {"level": "Fed", "office": "Senator", "name": "B", "party": "Y", "website": "", "file_date": "d"},
            {"level": "State", "office": "Governor", "name": "C", "party": "Z", "website": "", "file_date": "d"},
        ]
        grouped = utils.group_by_office(recs)
        assert list(grouped) == ["Fed", "State"]
        assert [c["name"] for c in grouped["Fed"]["Senator"]] == ["A", "B"]
        assert grouped["State"]["Governor"][0] == {"name": "C", "party": "Z", "website": "", "file_date": "d"}

    def test_missing_level_and_office_get_placeholders(self):
        grouped = utils.group_by_office([{"level": None, "office": None, "name": "A",
                                          "party": "", "website": "", "file_date": ""}])
        assert "Unknown Office" in grouped["Unknown Level"]

    def test_empty(self):
        assert utils.group_by_office([]) == {}


# ---------------------------------------------------------------- block detection
class FakePage:
    def __init__(self, url, content):
        self.url, self._content = url, content

    def content(self):
        return self._content


class TestBlockDetection:
    @pytest.mark.parametrize("text,expected", [
        ("Please solve the CAPTCHA", True), ("protected by Radware", True),
        ("<table>results</table>", False), ("", False),
    ])
    def test_looks_blocked(self, text, expected):
        assert utils._looks_blocked(text) is expected

    def test_looks_solved_on_results_page(self):
        assert utils._looks_solved(FakePage("https://candidates.sos.mn.gov/", "<table><tr></tr></table>"))

    def test_not_solved_on_another_host(self):
        assert not utils._looks_solved(FakePage("https://elsewhere.example/", "<table></table>"))

    def test_not_solved_while_captcha_is_showing(self):
        assert not utils._looks_solved(FakePage("https://candidates.sos.mn.gov/", "captcha <table></table>"))

    def test_not_solved_without_a_results_table(self):
        assert not utils._looks_solved(FakePage("https://candidates.sos.mn.gov/", "<p>loading</p>"))

    def test_candidate_name_text_counts_as_results(self):
        assert utils._looks_solved(FakePage("https://candidates.sos.mn.gov/", "Candidate Name"))


# ---------------------------------------------------------------- get_base_url
class TestGetBaseUrl:
    @pytest.mark.xfail(strict=True, reason=(
        "BUG: get_base_url() splits AT the TLD and drops it, so "
        "'https://candidates.sos.mn.gov/x' becomes 'https://candidates.sos.mn' -- "
        "not a usable warm-up URL for make_session()."))
    def test_returns_scheme_and_host_including_tld(self):
        assert utils.get_base_url("https://candidates.sos.mn.gov/results") == "https://candidates.sos.mn.gov"

    @pytest.mark.xfail(strict=True, reason=(
        "BUG: utils.get_base_url() calls UnableToFindBaseUrlError(url, domain_names) but the "
        "exception's __init__ also requires `message`, so a TypeError is raised instead."))
    def test_unknown_tld_raises_the_documented_error(self):
        import custom_exceptions
        with pytest.raises(custom_exceptions.UnableToFindBaseUrlError):
            utils.get_base_url("https://example.xyz/page")

    def test_current_behaviour_truncates_at_first_known_tld(self):
        # Characterization of today's behaviour (see the xfail above).
        assert utils.get_base_url("https://example.org/page") == "https://example"


# ---------------------------------------------------------------- make_session / fetch_soup
class FakeResponse:
    def __init__(self, text="<html><body><table></table></body></html>", status=200):
        self.text, self.content, self.status_code = text, text.encode(), status

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code}")


class FakeSession:
    def __init__(self, response):
        self.response, self.calls = response, []

    def get(self, url, timeout=None):
        self.calls.append((url, timeout))
        return self.response


class TestFetchSoup:
    def test_returns_parsed_soup(self):
        session = FakeSession(FakeResponse("<html><p id='x'>hi</p></html>"))
        soup = utils.fetch_soup("https://a.test/page", session=session)
        assert soup.find(id="x").text == "hi" and session.calls == [("https://a.test/page", 30)]

    @pytest.mark.parametrize("body", ["Please solve this CAPTCHA", "Incident ID: 123"])
    def test_block_pages_raise(self, body):
        with pytest.raises(RuntimeError, match="CAPTCHA"):
            utils.fetch_soup("https://a.test/", session=FakeSession(FakeResponse(body)))

    def test_http_errors_propagate(self):
        import requests
        with pytest.raises(requests.HTTPError):
            utils.fetch_soup("https://a.test/", session=FakeSession(FakeResponse(status=403)))

    def test_builds_a_session_when_none_given(self, monkeypatch):
        built = {}
        session = FakeSession(FakeResponse())
        monkeypatch.setattr(utils, "get_base_url", lambda url: "BASE")
        monkeypatch.setattr(utils, "make_session", lambda base: built.setdefault("base", base) and session)
        utils.fetch_soup("https://a.test/page")
        assert built["base"] == "BASE" and session.calls


class TestMakeSession:
    def test_sets_browser_headers_and_warms_up(self, monkeypatch):
        import requests
        warm = {}

        def fake_get(self, url, timeout=None):
            warm["url"] = url
            return FakeResponse()

        monkeypatch.setattr(requests.Session, "get", fake_get)
        session = utils.make_session("https://a.test")
        assert warm["url"] == "https://a.test"
        assert session.headers["User-Agent"] == utils.HEADERS["User-Agent"]

    def test_warm_up_failure_is_not_fatal(self, monkeypatch):
        import requests

        def boom(self, url, timeout=None):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(requests.Session, "get", boom)
        assert utils.make_session("https://a.test") is not None
