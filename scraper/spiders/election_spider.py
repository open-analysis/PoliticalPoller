"""
Description: Spider for government candidate/ballot pages that don't sit
    behind bot protection -- a plain, polite Scrapy crawl is enough.

Sites that DO gate access behind a CAPTCHA (config "requires_browser":
True, e.g. "mn") are refused here on purpose: Scrapy's downloader is an
HTTP client, not a browser, so it can't solve or get past that kind of
challenge, and pretending otherwise would either hang or get the crawler
IP blocked. Those sites go through the Playwright-based
fetch_soup_persistent_browser() path in site_reader.py instead, which
shares this spider's table-parsing code via election_table_parsers.py --
see run_election_spider() in site_reader.py, which routes to whichever
path a site's config calls for.

Run directly with:
    scrapy crawl elections -a site=example_open_state -o candidates.jsonl
LLM: claude-sonnet-5
"""

from datetime import datetime, timezone

import scrapy

from PoliticalPoller.items import ElectionCandidateItem
from PoliticalPoller.election_site_configs import get_election_site_config
from PoliticalPoller.election_table_parsers import parse_table


class ElectionSpider(scrapy.Spider):
    name = "elections"

    # Government sites are often lower-capacity and more sensitive to
    # scraping traffic than commercial news sites; crawl them more gently
    # than the defaults in settings.py.
    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 3,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    def __init__(self, site: str = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not site:
            raise ValueError(
                "ElectionSpider requires a site, e.g. "
                "`scrapy crawl elections -a site=example_open_state`"
            )
        config = get_election_site_config(site)

        if config.get("requires_browser"):
            raise ValueError(
                f"Site {site!r} is bot-protected (requires_browser=True) "
                "and can't be crawled by this Scrapy spider. Use "
                "run_election_spider() in site_reader.py instead -- it "
                "routes bot-protected sites through the Playwright-based "
                "fetcher and reuses this same table parser."
            )

        self.site = site
        self.state = config.get("state", "")
        self.allowed_domains = list(config["allowed_domains"])
        self.start_urls = list(config["start_urls"])
        self.table_parser = config["table_parser"]
        self.table_parser_config = config.get("table_parser_config", {})

    def parse(self, response):
        records = parse_table(response.selector, self.table_parser, self.table_parser_config)

        scraped_at = datetime.now(timezone.utc).isoformat()
        for record in records:
            yield ElectionCandidateItem(
                site=self.site,
                state=self.state,
                office_level=record.get("office_level"),
                office=record.get("office"),
                candidate_name=record.get("candidate_name"),
                party=record.get("party"),
                website=record.get("website"),
                file_date=record.get("file_date"),
                source_url=response.url,
                scraped_at=scraped_at,
            )
