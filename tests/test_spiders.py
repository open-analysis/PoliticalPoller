"""Scrapy spiders: callbacks exercised against canned responses (no network)."""
import pytest

pytest.importorskip("scrapy")
from scrapy.http import HtmlResponse, Request  # noqa: E402

from PoliticalPoller.items import ElectionCandidateItem, NewsArticleItem  # noqa: E402
from PoliticalPoller.spiders.election_spider import ElectionSpider  # noqa: E402
from PoliticalPoller.spiders.news_spider import NewsSpider  # noqa: E402


def response(url, body):
    return HtmlResponse(url=url, body=body.encode(), encoding="utf-8")


# ---------------------------------------------------------------- NewsSpider
class TestNewsSpider:
    def test_requires_a_site(self):
        with pytest.raises(ValueError, match="requires a site"):
            NewsSpider()

    def test_unknown_site(self):
        with pytest.raises(ValueError, match="Unknown site"):
            NewsSpider(site="nope")

    def test_config_is_loaded(self):
        spider = NewsSpider(site="example")
        assert spider.allowed_domains == ["example-news.com"]
        assert spider.article_url_contains == "/article/"

    def test_article_page_yields_item_and_follows_links(self):
        spider = NewsSpider(site="example")
        html = ('<html><head><meta property="og:title" content=" Big Story ">'
                '<meta property="article:published_time" content="2026-05-01T10:00:00Z">'
                '<title>ignored</title></head>'
                '<body><div class="sitemap"><a href="/more">m</a></div></body></html>')
        out = list(spider.parse(response("https://www.example-news.com/article/1", html)))
        items = [o for o in out if isinstance(o, NewsArticleItem)]
        requests = [o for o in out if isinstance(o, Request)]
        assert len(items) == 1
        item = items[0]
        assert item["title"] == "Big Story" and item["site"] == "example"
        assert item["url"] == "https://www.example-news.com/article/1"
        assert item["published_date"] == "2026-05-01T10:00:00Z" and item["scraped_at"]
        assert [r.url for r in requests] == ["https://www.example-news.com/more"]

    def test_title_tag_is_the_fallback(self):
        spider = NewsSpider(site="example")
        out = list(spider.parse(response("https://www.example-news.com/article/2",
                                         "<html><head><title>Fallback</title></head></html>")))
        assert out[0]["title"] == "Fallback" and out[0]["published_date"] is None

    def test_article_without_a_title_is_skipped(self):
        spider = NewsSpider(site="example")
        out = list(spider.parse(response("https://www.example-news.com/article/3", "<html></html>")))
        assert [o for o in out if isinstance(o, NewsArticleItem)] == []

    def test_index_page_only_follows_links(self):
        spider = NewsSpider(site="example")
        html = '<div class="sitemap"><a href="/a">a</a><a href="/b">b</a></div>'
        out = list(spider.parse(response("https://www.example-news.com/sitemap.html", html)))
        assert [r.url for r in out] == ["https://www.example-news.com/a", "https://www.example-news.com/b"]


# ---------------------------------------------------------------- ElectionSpider
class TestElectionSpider:
    HTML = """<table class="candidate-list">
      <tr><td class="candidate-name">Jo Park</td><td class="office">Mayor</td><td class="party">IND</td>
          <td class="website"><a href="https://jopark.org">x</a></td><td class="filed-date">05/01/2026</td></tr>
      <tr><td class="candidate-name">Al Fox</td><td class="office">Clerk</td></tr>
    </table>"""
    URL = "https://elections.example.gov/candidates/2026"

    def test_requires_a_site(self):
        with pytest.raises(ValueError, match="requires a site"):
            ElectionSpider()

    def test_refuses_browser_only_sites(self):
        with pytest.raises(ValueError, match="bot-protected"):
            ElectionSpider(site="mn")

    def test_unknown_site(self):
        with pytest.raises(ValueError, match="Unknown election site"):
            ElectionSpider(site="nope")

    def test_config_is_loaded(self):
        spider = ElectionSpider(site="example_open_state")
        assert spider.state == "Example State" and spider.table_parser == "simple_table"
        assert spider.start_urls == [self.URL]

    def test_parse_yields_stamped_items(self):
        spider = ElectionSpider(site="example_open_state")
        items = list(spider.parse(response(self.URL, self.HTML)))
        assert all(isinstance(i, ElectionCandidateItem) for i in items)
        jo, al = items
        assert (jo["candidate_name"], jo["office"], jo["party"], jo["website"], jo["file_date"]) == \
            ("Jo Park", "Mayor", "IND", "https://jopark.org", "05/01/2026")
        assert jo["site"] == "example_open_state" and jo["state"] == "Example State"
        assert jo["source_url"] == self.URL and jo["scraped_at"]
        assert al["candidate_name"] == "Al Fox" and al["party"] == ""

    def test_parse_of_an_unrelated_page_yields_nothing(self):
        spider = ElectionSpider(site="example_open_state")
        assert list(spider.parse(response(self.URL, "<html><p>maintenance</p></html>"))) == []
