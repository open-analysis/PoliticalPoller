"""
Description: Generic sitemap-crawling spider for news sites.

Replaces the old CNN-only cnn_spider.py. Instead of hard-coding one site's
selectors and writing CSV rows by hand mid-parse, this spider:
  - reads its start_urls / allowed_domains / link selectors from
    site_configs.py, so it works for any registered site
  - yields proper scrapy Items instead of opening a file and exporting
    rows itself (export is handled by Scrapy's FEEDS/pipelines, which is
    the standard, crash-safe way to do it)
  - fixes the `href.count('article') is not 0` bug (comparing an int with
    `is` is never reliable) and drops the bare `except: pass` blocks that
    were silently swallowing real errors

Run it directly with:
    scrapy crawl news -a site=cnn -o cnn_articles.jsonl

Or invoke it programmatically -- see run_news_spider() in site_reader.py.
LLM: claude-sonnet-5
"""

from datetime import datetime, timezone

import scrapy

from PoliticalPoller.items import NewsArticleItem
from PoliticalPoller.site_configs import get_site_config


class NewsSpider(scrapy.Spider):
    name = "news"

    def __init__(self, site: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not site:
            raise ValueError(
                "NewsSpider requires a site, e.g. `scrapy crawl news -a site=cnn`"
            )
        self.site = site
        config = get_site_config(site)
        self.allowed_domains = list(config["allowed_domains"])
        self.start_urls = list(config["start_urls"])
        self.index_link_selectors = config["index_link_selectors"]
        self.article_url_contains = config["article_url_contains"]

    def parse(self, response):
        if self.article_url_contains in response.url:
            item = self.extract_article(response)
            if item is not None:
                yield item
            # An article page can still link to more index pages (e.g. a
            # "more from this section" sitemap link), so fall through to
            # following links rather than returning early.

        for selector in self.index_link_selectors:
            yield from response.follow_all(css=selector, callback=self.parse)

    def extract_article(self, response):
        """Best-effort, mostly site-agnostic extraction using common meta
        tags, falling back to <title> if a site doesn't set them."""
        title = (
            response.css('meta[property="og:title"]::attr(content)').get()
            or response.css("title::text").get()
        )
        if not title:
            # No usable title means this probably isn't a real article
            # page (e.g. a redirect or a stub) -- skip rather than yield
            # a useless item.
            return None

        published_date = response.css(
            'meta[property="article:published_time"]::attr(content)'
        ).get()

        return NewsArticleItem(
            site=self.site,
            title=title.strip(),
            url=response.url,
            published_date=published_date,
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )
