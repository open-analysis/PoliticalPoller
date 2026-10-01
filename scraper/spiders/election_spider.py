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

import scrapy

from PoliticalPoller.items import ElectionCandidateItem
from PoliticalPoller.election_site_configs import get_election_site_config
from PoliticalPoller.election_table_parsers import build_candidate_records, parse_table


class ElectionSpider(scrapy.Spider):
    """
    Description: Scrapy spider for government candidate/ballot pages that
        don't sit behind bot protection -- see the module docstring for
        why bot-protected sites are refused rather than attempted here.
    """
    name = "elections"

    # Government sites are often lower-capacity and more sensitive to
    # scraping traffic than commercial news sites; crawl them more gently
    # than the defaults in settings.py.
    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 3,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
    }

    """
    Description: Loads `site`'s config, refuses to proceed if that site
        requires the browser path, and sets up this spider instance's
        allowed_domains/start_urls/table_parser from the config.
    Param[in] site:  Election site key, e.g. "example_open_state"
    Owner: @opnanalysis
    LLM: claude-sonnet-5
    """
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

    """
    Description: Scrapy's callback for each start_url response; parses
        the candidate table via the configured strategy and yields one
        ElectionCandidateItem per record found.
    Param[in] response:  The downloaded Response for a start_url
    Owner: @opnanalysis
    LLM: claude-sonnet-5
    """
    def parse(self, response):
        raw_records = parse_table(response.selector, self.table_parser, self.table_parser_config)

        # Shared with run_election_spider()'s browser-fetch path in
        # site_reader.py, so a Scrapy-crawled site and a browser-fetched
        # site yield identically-shaped records.
        records = build_candidate_records(raw_records, self.site, self.state, response.url)
        for record in records:
            yield ElectionCandidateItem(**record)
