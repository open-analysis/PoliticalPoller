"""
Description: This file defines the site configs for the spiders.
Each entry tells the generic spider three things about a site:
  1. Where to start (usually a sitemap/index page) and which domains it's
     allowed to follow links to.
  2. Which CSS selectors, applied at every depth of the sitemap/index
     hierarchy, point to more links to follow (sites like CNN nest their
     sitemap into year -> month -> section -> article pages, each with
     its own list markup).
  3. How to recognize an actual article URL vs. another index page, so the
     spider knows when to extract an item instead of just following links.

To add a new site: add a new key here with its own selectors/pattern. No
spider code changes are needed.
LLM: claude-sonnet-5
"""


SITE_CONFIGS = {
    "cnn": {
        "allowed_domains": ["cnn.com"],
        "start_urls": ["https://www.cnn.com/sitemap.html"],
        # Applied at every page; any that match are followed as more
        # sitemap/index links.
        "index_link_selectors": [
            "ul.sitemap-year a::attr(href)",
            "ul.sitemap-month a::attr(href)",
            "li.month a::attr(href)",
            "li.date a::attr(href)",
            "li.section a::attr(href)",
            "ul.sections-names a::attr(href)",
            "span.sitemap-link a::attr(href)",
        ],
        # A URL is treated as an article (and scraped as an item) if this
        # substring appears in it; otherwise it's treated as another index
        # page and only its links are followed.
        "article_url_contains": "article",
    },

    # Example second site, shown as a template for adding others.
    # Most modern news sites expose Open Graph / article meta tags, which
    # extract_article() in the spider already reads generically -- usually
    # only the selectors/pattern below need to change per site.
    "example": {
        "allowed_domains": ["example-news.com"],
        "start_urls": ["https://www.example-news.com/sitemap.html"],
        "index_link_selectors": [
            "div.sitemap a::attr(href)",
        ],
        "article_url_contains": "/article/",
    },
}

"""
Description: Returns a given site's configuration info for a spider to crawl.
Param[in] Site:      Website name/domain name
Param[out] dict:    Dictionary of a site's configuration 
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def get_site_config(site: str) -> dict:
    try:
        return SITE_CONFIGS[site]
    except KeyError:
        raise ValueError(
            f"Unknown site {site!r}. Add a config for it in "
            f"site_configs.py. Known sites: {sorted(SITE_CONFIGS)}"
        )
