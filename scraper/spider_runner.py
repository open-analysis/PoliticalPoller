"""
Description: Functions that run the PoliticalPoller project's spiders
    (news_spider.py / election_spider.py) -- or, for bot-protected
    election sites, the equivalent Playwright-based fetch-and-parse path
    -- and return their results as plain lists of dicts. Split out of
    site_reader.py so site_reader.py can stay focused on the
    find_politician()/find_political_assoc() orchestration layer, and so
    other code can import just these spider-running functions without
    pulling in site_reader.py's requests/BeautifulSoup/Playwright fetch
    machinery it doesn't need.
LLM: claude-sonnet-5
"""

import json
import subprocess
import sys
import tempfile

from utils import fetch_soup_persistent_browser

"""
Description: Returns True if `article`'s title mentions every one of the
    given candidate/election/location terms (case-insensitive substring
    match). Terms left as None are simply not checked. The title is the
    only field NewsArticleItem captures, so that's what filtering runs
    against; a site that also needs body-text filtering would have to add
    a body/snippet field to NewsArticleItem and extract_article() first.
Param[in] article:    One article dict, as returned by run_news_spider()
Param[in] candidate:  Candidate name to require in the title, or None
Param[in] election:   Election name/cycle to require in the title (e.g.
    "2026 midterms"), or None
Param[in] location:   State/location to require in the title, or None
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _article_matches(
    article: dict,
    candidate: str = None,
    election: str = None,
    location: str = None,
) -> bool:
    title = (article.get("title") or "").lower()
    terms = [t for t in (candidate, election, location) if t]
    return all(t.lower() in title for t in terms)

"""
Description: Runs the PoliticalPoller Scrapy project's NewsSpider for a
    given configured site (see PoliticalPoller/site_configs.py) and returns
    the scraped articles as a list of dicts, optionally filtered down to
    ones mentioning a given candidate, election, and/or state/location.

    Runs Scrapy out-of-process via `scrapy crawl`, rather than importing
    CrawlerProcess in-process, so its Twisted reactor never has to share a
    process with the synchronous Playwright browser calls used elsewhere
    (utils.py's fetch_soup_* functions) -- both manage their own event
    loop and don't mix safely in one process.
Param[in] site:         Site key from PoliticalPoller/site_configs.py,
    e.g. "cnn"
Param[in] candidate:    Only return articles whose title mentions this
    candidate name, if given
Param[in] election:     Only return articles whose title mentions this
    election name/cycle, if given
Param[in] location:     Only return articles whose title mentions this
    state/location, if given
Param[in] project_dir:  Path to the PoliticalPoller project (the directory
    containing scrapy.cfg)
Param[in] timeout:      Max seconds to let the crawl run before killing it
Param[out] articles:    List of dicts (title, url, site, published_date,
    scraped_at), one per scraped article matching every given filter (or
    every scraped article, if no filters were given)
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def run_news_spider(
    site: str,
    candidate: str = None,
    election: str = None,
    location: str = None,
    project_dir: str = "PoliticalPoller",
    timeout: int = 1800,
) -> list:
    with tempfile.NamedTemporaryFile(
        suffix=".jsonl", delete=False
    ) as tmp:
        output_path = tmp.name

    cmd = [
        "scrapy", "crawl", "news",
        "-a", f"site={site}",
        "-o", output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=project_dir,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"scrapy crawl news -a site={site} did not finish within "
            f"{timeout}s."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"scrapy crawl news -a site={site} failed "
            f"(exit {result.returncode}):\n{result.stderr}"
        )

    articles = []
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                articles.append(json.loads(line))

    if candidate or election or location:
        articles = [
            a for a in articles
            if _article_matches(a, candidate=candidate, election=election, location=location)
        ]

    return articles

"""
Description: Runs the appropriate crawl path for a configured government
    election/candidate site and returns scraped candidates as a list of
    dicts, regardless of whether the site needs Scrapy or a real browser.

    Dispatches on election_site_configs.py's "requires_browser" flag:
      - True  (e.g. "mn"): fetches with utils.fetch_soup_persistent_browser()
        (Playwright + stealth + manual-CAPTCHA-solve), then parses the
        resulting HTML with the *same* table parser ElectionSpider would
        use, via election_table_parsers.parse_table().
      - False: runs `scrapy crawl elections -a site=<site>` out-of-process,
        for the same reactor-isolation reason run_news_spider() does.

    Both paths finish by calling election_table_parsers.
    build_candidate_records() (the same helper ElectionSpider.parse()
    uses) to attach site/state/source_url/scraped_at, so this always
    returns the same shape of list[dict] that run_news_spider() does --
    one dict per record, every field present, regardless of which fetch
    strategy a given site needed.
Param[in] site:          Site key from
    PoliticalPoller/election_site_configs.py, e.g. "mn"
Param[in] project_dir:   Path to the PoliticalPoller project (only used
    for the Scrapy path)
Param[in] headless:      Only used for the browser path; pass False once
    if a site starts blocking, to solve a CAPTCHA manually
Param[in] timeout:       Max seconds for the Scrapy path before killing it
Param[out] candidates:   List of dicts, each with: site, state,
    office_level, office, candidate_name, party, website, file_date,
    source_url, scraped_at
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def run_election_spider(
    site: str,
    project_dir: str = "PoliticalPoller",
    headless: bool = True,
    timeout: int = 1800,
) -> list:
    sys.path.append(project_dir)
    from election_site_configs import get_election_site_config
    from election_table_parsers import build_candidate_records, parse_table

    config = get_election_site_config(site)

    if config.get("requires_browser"):
        start_url = config["start_urls"][0]
        soup = fetch_soup_persistent_browser(start_url, headless=headless)

        from parsel import Selector
        selector = Selector(text=str(soup))
        raw_records = parse_table(
            selector, config["table_parser"], config.get("table_parser_config", {})
        )
        return build_candidate_records(
            raw_records, site, config.get("state", ""), start_url
        )

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tmp:
        output_path = tmp.name

    cmd = ["scrapy", "crawl", "elections", "-a", f"site={site}", "-o", output_path]

    try:
        result = subprocess.run(
            cmd, cwd=project_dir, timeout=timeout, capture_output=True, text=True
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"scrapy crawl elections -a site={site} did not finish within "
            f"{timeout}s."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"scrapy crawl elections -a site={site} failed "
            f"(exit {result.returncode}):\n{result.stderr}"
        )

    # Already shaped by build_candidate_records() inside ElectionSpider --
    # this just loads what Scrapy's JSONL feed export wrote.
    candidates = []
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                candidates.append(json.loads(line))

    return candidates

"""
Description: Runs run_election_spider() for a site and merges the result
    into that site's persisted candidate store (see
    PoliticalPoller/candidate_store.py): candidates already on file get
    their fields refreshed in place, newly-filed candidates get added,
    and nothing is deleted just because one run didn't see it (a vanished
    row could be a site hiccup rather than a real withdrawal, so removal
    stays a human decision).

    This is the entry point to call each time an election cycle comes
    around (or periodically during filing season) to keep a site's saved
    candidate list in sync with what's actually posted, rather than
    re-scraping from scratch and discarding history every time.
Param[in] site:         Election site key from
    PoliticalPoller/election_site_configs.py, e.g. "mn"
Param[in] project_dir:  Path to the PoliticalPoller project (only used
    for sites crawled via Scrapy, and to import candidate_store.py)
Param[in] store_dir:    Directory the per-site candidate JSON files live
    in (see candidate_store.DEFAULT_STORE_DIR)
Param[in] headless:     Only used for sites fetched via browser; pass
    False once if a site starts blocking, to solve a CAPTCHA manually
Param[in] timeout:      Max seconds for the Scrapy path before killing it
Param[out] summary:     Dict with "new_candidates" / "new_offices" /
    "updated_offices" (lists of labels), "unchanged" (a count),
    "collisions" (notes on any newly-detected same-name candidates -- see
    candidate_store.py), and "store" (the full merged store just saved)
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def sync_election_candidates(
    site: str,
    project_dir: str = "PoliticalPoller",
    store_dir: str = None,
    headless: bool = True,
    timeout: int = 1800,
) -> dict:
    sys.path.append(project_dir)
    import candidate_store

    fresh_records = run_election_spider(
        site, project_dir=project_dir, headless=headless, timeout=timeout
    )

    kwargs = {}
    if store_dir is not None:
        kwargs["store_dir"] = store_dir

    summary = candidate_store.upsert_candidates(site, fresh_records, **kwargs)

    print(
        f"Synced {site!r}: {len(summary['new_candidates'])} new candidates, "
        f"{len(summary['new_offices'])} new offices for known candidates, "
        f"{len(summary['updated_offices'])} updated, {summary['unchanged']} unchanged."
    )
    for label in summary["new_candidates"]:
        print(f"  + {label}")
    for label in summary["new_offices"]:
        print(f"  » {label}")
    for label in summary["updated_offices"]:
        print(f"  ~ {label}")
    for note in summary.get("collisions", []):
        print(f"  ! possible same-name collision -- {note}")

    return summary
