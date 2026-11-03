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

    def query_selector(self, selector):
        return BeautifulSoup(self._content, "html.parser").select_one(selector)


class TestBlockDetection:
    @pytest.mark.parametrize("text,expected", [
        ("Please solve the CAPTCHA", True), ("protected by Radware", True),
        ("<table>results</table>", False), ("", False),
    ])
    def test_looks_blocked(self, text, expected):
        assert utils._looks_blocked(text) is expected

    HOST = "candidates.sos.mn.gov"

    def test_solved_on_the_expected_host_with_a_results_table(self):
        page = FakePage("https://candidates.sos.mn.gov/", "<table><tr></tr></table>")
        assert utils._looks_solved(page, self.HOST)

    def test_works_for_any_site_not_just_minnesota(self):
        page = FakePage("https://voter.votewa.gov/CandidateList.aspx?e=899", "<table></table>")
        assert utils._looks_solved(page, "voter.votewa.gov")
        assert not utils._looks_solved(page, self.HOST)

    def test_subdomains_of_the_expected_host_count(self):
        assert utils._looks_solved(FakePage("https://www.example.gov/x", "<table></table>"), "example.gov")

    def test_a_lookalike_host_does_not_count(self):
        assert not utils._looks_solved(FakePage("https://evilexample.gov/x", "<table></table>"), "example.gov")
        assert not utils._looks_solved(FakePage("https://example.gov.evil.test/x", "<table></table>"), "example.gov")

    def test_not_solved_on_another_host(self):
        assert not utils._looks_solved(FakePage("https://elsewhere.example/", "<table></table>"), self.HOST)

    def test_host_match_ignores_case_and_port(self):
        assert utils._looks_solved(FakePage("https://CANDIDATES.sos.mn.gov:443/", "<table></table>"), self.HOST.upper())

    def test_not_solved_while_captcha_is_showing(self):
        assert not utils._looks_solved(FakePage("https://candidates.sos.mn.gov/", "captcha <table></table>"), self.HOST)

    def test_not_solved_without_the_ready_element(self):
        assert not utils._looks_solved(FakePage("https://candidates.sos.mn.gov/", "<p>loading</p>"), self.HOST)

    def test_a_site_can_name_its_own_ready_selector(self):
        page = FakePage("https://a.example.gov/", "<div id='results'>rows</div>")
        assert not utils._looks_solved(page, "a.example.gov")                   # default is "table"
        assert utils._looks_solved(page, "a.example.gov", ready_selector="div#results")

    def test_an_empty_expected_host_never_matches(self):
        assert not utils._looks_solved(FakePage("https://a.example.gov/", "<table></table>"), "")


# ---------------------------------------------------------------- fetch_soup_persistent_browser
class FakeContext:
    def __init__(self, page):
        self.pages, self.closed = [page], False

    def close(self):
        self.closed = True


class ScriptedPage(FakePage):
    """A page whose HTML changes as the 'human' works: each time.sleep() call advances one step."""

    def __init__(self, steps):
        super().__init__(steps[0][0], steps[0][1])
        self.steps, self.step, self.goto_url = steps, 0, None

    def goto(self, url, **kwargs):
        self.goto_url = url

    def advance(self):
        self.step = min(self.step + 1, len(self.steps) - 1)
        self.url, self._content = self.steps[self.step]


@pytest.fixture
def browser(monkeypatch):
    """Replaces Playwright, the stealth patch, and sleeping; returns a function that scripts one run."""
    state = {"sleeps": 0}

    class FakeStealth:
        def apply_stealth_sync(self, context):
            pass

    def run(steps, **kwargs):
        page = ScriptedPage(steps)
        context = FakeContext(page)

        class Chromium:
            def launch_persistent_context(self, *a, **kw):
                state["launch"] = kw
                return context

        class PW:
            chromium = Chromium()

        class Manager:
            def __enter__(self):
                return PW()
            def __exit__(self, *exc):
                return False

        def fake_sleep(_):
            state["sleeps"] += 1
            page.advance()

        monkeypatch.setattr(utils, "sync_playwright", lambda: Manager())
        monkeypatch.setattr(utils, "Stealth", FakeStealth)
        monkeypatch.setattr(utils.time, "sleep", fake_sleep)
        state.update(page=page, context=context)
        return state, lambda url="https://candidates.sos.mn.gov/", **kw: utils.fetch_soup_persistent_browser(url, **{**kwargs, **kw})
    return run


RESULTS = "<html><table><tr><td>Jane Doe</td></tr></table></html>"
CAPTCHA = "<html>Please solve the CAPTCHA</html>"
MN = "https://candidates.sos.mn.gov/"


class TestPersistentBrowser:
    def test_an_unblocked_page_is_returned_and_the_browser_closed(self, browser):
        state, fetch = browser([(MN, RESULTS)])
        soup = fetch()
        assert "Jane Doe" in soup.text and state["context"].closed and state["sleeps"] == 0
        assert state["page"].goto_url == MN

    def test_headless_runs_do_not_wait_for_a_human(self, browser):
        state, fetch = browser([(MN, CAPTCHA)], headless=True)
        with pytest.raises(RuntimeError, match="headless"):
            fetch()
        assert state["context"].closed and state["sleeps"] == 0

    def test_a_headed_run_waits_until_the_captcha_is_solved(self, browser):
        state, fetch = browser([(MN, CAPTCHA), (MN, CAPTCHA), (MN, CAPTCHA), (MN, RESULTS)], headless=False)
        soup = fetch()
        assert "Jane Doe" in soup.text and state["sleeps"] == 3 and state["context"].closed

    def test_solving_on_a_different_site_works_the_same_way(self, browser):
        votewa = "https://voter.votewa.gov/CandidateList.aspx?e=899"
        state, fetch = browser([(votewa, CAPTCHA), (votewa, RESULTS)], headless=False)
        assert "Jane Doe" in fetch(votewa).text

    def test_a_redirect_to_another_host_is_not_a_solve(self, browser):
        state, fetch = browser([(MN, CAPTCHA), ("https://login.example.test/", RESULTS)],
                               headless=False, manual_wait_seconds=3)
        with pytest.raises(TimeoutError, match="Gave up after 3s"):
            fetch()
        assert state["context"].closed

    def test_the_wait_is_bounded_by_manual_wait_seconds(self, browser):
        state, fetch = browser([(MN, CAPTCHA)], headless=False, manual_wait_seconds=5)
        with pytest.raises(TimeoutError):
            fetch()
        assert state["sleeps"] == 5

    def test_a_site_without_a_table_needs_its_own_ready_selector(self, browser):
        listing = "<html><div id='results'>Jane Doe</div></html>"
        state, fetch = browser([(MN, CAPTCHA), (MN, listing)], headless=False, manual_wait_seconds=3)
        with pytest.raises(TimeoutError):
            fetch()                                                 # default selector "table"
        state, fetch = browser([(MN, CAPTCHA), (MN, listing)], headless=False, manual_wait_seconds=3,
                               ready_selector="div#results")
        assert "Jane Doe" in fetch().text

    def test_profile_dir_and_visibility_are_forwarded_to_the_browser(self, browser):
        state, fetch = browser([(MN, RESULTS)], user_data_dir="/tmp/prof", headless=False)
        fetch()
        assert state["launch"]["headless"] is False


# ---------------------------------------------------------------- get_base_url
class TestGetBaseUrl:
    @pytest.mark.parametrize("url,expected", [
        ("https://candidates.sos.mn.gov/results", "https://candidates.sos.mn.gov"),
        ("https://candidates.sos.mn.gov", "https://candidates.sos.mn.gov"),
        ("http://example.org/a/b?x=1#frag", "http://example.org"),
        ("https://www.cnn.com/sitemap.html", "https://www.cnn.com"),
        ("https://example.net:8443/x", "https://example.net:8443"),
        ("https://user:pw@example.com/x", "https://example.com"),
        ("HTTPS://EXAMPLE.COM/X", "https://example.com"),
        ("candidates.sos.mn.gov/results", "https://candidates.sos.mn.gov"),
        ("https://example.gov.uk/page", "https://example.gov.uk"),
    ])
    def test_returns_scheme_and_full_host(self, url, expected):
        assert utils.get_base_url(url) == expected

    @pytest.mark.parametrize("url", [
        "https://example.xyz/page",
        "https://example.community/",   # ".com" only as a prefix of another label
        "https://localhost:8000/",
        "https://example.io/?next=http://other.com",  # suffix only in the query string
        "https://example.io/path.com/x",              # suffix only in the path
        "",
    ])
    def test_unrecognized_hosts_raise_the_documented_error(self, url):
        import custom_exceptions
        with pytest.raises(custom_exceptions.UnableToFindBaseUrlError) as err:
            utils.get_base_url(url)
        assert err.value.url == url and ".gov" in err.value.domain_names
        assert repr(url) in str(err.value) and "Base URL not found" in str(err.value)


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


class TestWarmUpTarget:
    def test_fetch_soup_warms_up_the_real_host_then_fetches_the_page(self, monkeypatch):
        import requests
        urls = []

        def fake_get(self, url, timeout=None):
            urls.append(url)
            return FakeResponse()

        monkeypatch.setattr(requests.Session, "get", fake_get)
        utils.fetch_soup("https://candidates.sos.mn.gov/results")
        assert urls == ["https://candidates.sos.mn.gov", "https://candidates.sos.mn.gov/results"]


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
