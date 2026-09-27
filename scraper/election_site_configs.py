# -*- coding: utf-8 -*-

"""
Description: Per-site crawl/parse configuration for ElectionSpider and for
    the Playwright-based government-site fetchers in site_reader.py.

Unlike news sites, government election sites split cleanly into two
groups that need different handling:

  - Plain HTML sites with no meaningful bot protection: ElectionSpider
    (a regular Scrapy spider) can crawl these directly. Set
    "requires_browser": False.

  - Sites that gate access behind a CAPTCHA/bot-protection challenge (like
    Minnesota's), where a plain HTTP client gets blocked outright. These
    need the browser-automation path in site_reader.py
    (fetch_soup_persistent_browser) instead of Scrapy's downloader. Set
    "requires_browser": True -- ElectionSpider will refuse to crawl these
    itself and point to run_election_spider() in site_reader.py, which
    routes them correctly.

Either way, the actual table parsing is shared (see
election_table_parsers.py) via "table_parser" / "table_parser_config".
LLM: claude-sonnet-5
"""

ELECTION_SITE_CONFIGS = {
    "mn": {
        "state": "Minnesota",
        "allowed_domains": ["candidates.sos.mn.gov"],
        "start_urls": ["https://candidates.sos.mn.gov/"],
        # Confirmed bot-protected in practice (see site_reader.py's
        # CAPTCHA-handling fetch functions) -- must go through the
        # browser-automation path, not this Scrapy spider directly.
        "requires_browser": True,
        "table_parser": "colspan_hierarchy",
        # Empty dict -> use parse_colspan_hierarchy_table's defaults,
        # which already match MN's markup (see election_table_parsers.py).
        "table_parser_config": {},
    },

    # Example second site, shown as a template for adding an open (i.e.
    # not bot-protected) state or county site with a flat candidate table.
    "example_open_state": {
        "state": "Example State",
        "allowed_domains": ["elections.example.gov"],
        "start_urls": ["https://elections.example.gov/candidates/2026"],
        "requires_browser": False,
        "table_parser": "simple_table",
        "table_parser_config": {
            "row_selector": "table.candidate-list tr",
            "name_selector": "td.candidate-name::text",
            "office_selector": "td.office::text",
            "party_selector": "td.party::text",
            "website_selector": "td.website a::attr(href)",
            "file_date_selector": "td.filed-date::text",
        },
    },
}


def get_election_site_config(site: str) -> dict:
    try:
        return ELECTION_SITE_CONFIGS[site]
    except KeyError:
        raise ValueError(
            f"Unknown election site {site!r}. Add a config for it in "
            f"election_site_configs.py. Known sites: "
            f"{sorted(ELECTION_SITE_CONFIGS)}"
        )
