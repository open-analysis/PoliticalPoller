"""
Description: Orchestration layer for finding politician/candidate info --
    find_politician(), find_political_assoc(), and the legacy read_page()
    all-in-one entry point. This file intentionally does NOT contain the
    low-level fetch/parse helpers or the spider-running functions
    themselves anymore:
      - utils.py holds the HTTP/browser fetch strategies (fetch_soup,
        fetch_soup_cached_session, fetch_soup_persistent_browser,
        fetch_soup_playwright) and the HTML parsing helpers
        (parse_candidates, group_by_office, and their small _cell_text/
        _extract_website/_colspan building blocks)
      - spider_runner.py holds run_news_spider(), run_election_spider(),
        and sync_election_candidates() -- the functions that actually run
        the PoliticalPoller Scrapy spiders (or the equivalent browser
        path for bot-protected sites)
    Both are imported below and used the same way local functions used to
    be; nothing that previously worked by calling a function straight off
    this module should need to change other than the import.
LLM: claude-sonnet-5
"""

import json
import sys
import os

sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), "PoliticalPoller"))

from utils import (
    DEFAULT_COOKIE_FILE,
    DEFAULT_PROFILE_DIR,
    fetch_soup,
    fetch_soup_cached_session,
    fetch_soup_persistent_browser,
    fetch_soup_playwright,
    get_base_url,
    group_by_office,
    make_session,
    parse_candidates,
)
from spider_runner import run_election_spider, run_news_spider, sync_election_candidates

"""
Description: Fetches, parses, and groups the candidate results page in one
    call, choosing among the available fetch strategies (persistent
    browser, cached session, fresh playwright, or plain requests).

    This is the original, single-site, no-persistence entry point this
    file started with. For anything new, prefer run_election_spider() /
    sync_election_candidates() (spider_runner.py) instead -- they work
    across every site in PoliticalPoller/election_site_configs.py (not
    just this one), return results shaped like run_news_spider()'s, and
    sync_election_candidates() persists what it finds via
    candidate_store.py. This is kept for direct one-off use/debugging
    against a specific URL.
Param[in] input_webpage:  URI for the webpage to be read
Param[in] method:         Fetch strategy to use -- "persistent_browser"
    (default, recommended), "cached_session", "playwright", or "requests"
Param[in] headless:       Used by "persistent_browser"/"playwright"; try
    headless=False once if blocked, to solve manually
Param[in] cookie_file:    Only used by "cached_session"
Param[in] user_data_dir:  Only used by "persistent_browser"
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def read_page(input_webpage: str,
    method: str = "persistent_browser",
    headless: bool = True,
    cookie_file: str = DEFAULT_COOKIE_FILE,
    user_data_dir: str = DEFAULT_PROFILE_DIR,
) -> dict:
    if method == "persistent_browser":
        soup = fetch_soup_persistent_browser(
            input_webpage, user_data_dir=user_data_dir, headless=headless
        )
    elif method == "cached_session":
        soup = fetch_soup_cached_session(input_webpage, cookie_file=cookie_file)
    elif method == "playwright":
        soup = fetch_soup_playwright(input_webpage, headless=headless)
    elif method == "requests":
        session = make_session(get_base_url(input_webpage))
        soup = fetch_soup(input_webpage, session=session)
    else:
        raise ValueError(
            f"Unknown method: {method!r}. Use 'persistent_browser', "
            "'cached_session', 'playwright', or 'requests'."
        )

    records = parse_candidates(soup)
    return group_by_office(records)

"""
Description: Finds political associations for a given politician
    - Office held/going for
    - State serving in
    - District/ward/county/etc serving 
    - Party affiliation 
    - Group affiliations?
    - Bills/Orders/Research/etc with their name attached to i
Param[in] name:     Politician name to search for
Param[in] assoc:    Association to search for
Owner: @open-analysis
"""
def find_political_assoc(name: str, assoc: str):
    pass

"""
Description: Prints each matched candidate's full office history in the
    office_level/office/candidate_name/party/website/file_date shape
    find_politician() has always returned, one JSON block per office they
    hold a record for (a candidate can have more than one, if they've run
    for different offices across cycles -- see candidate_store.py).
Param[in] matches:  List of candidate record dicts (the "offices"-shaped
    kind from candidate_store.py), as returned by search_by_name()
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def _print_candidate_matches(matches: list) -> None:
    for m in matches:
        for office, details in m.get("offices", {}).items():
            print(json.dumps({
                "candidate_name": m.get("candidate_name"),
                "office_level": details.get("office_level"),
                "office": office,
                "party": details.get("party"),
                "website": details.get("website"),
                "file_date": details.get("file_date"),
            }, indent=2))

"""
Description: Finds a given politician's candidate filing info -- office
    level, office, candidate name, party, website, and file date, for
    every office they've been recorded for -- checking the saved
    candidate store (see candidate_store.py) first and only falling back
    to a live scrape (via sync_election_candidates(), which both fetches
    and saves) if nothing's cached yet or force_refresh is requested.
    Checking the store first means a repeat lookup doesn't re-hit the
    site at all, and a candidate who's filed for more than one office
    over time shows up as one person with their full office history,
    not a separate hit per office.
Param[in] name:           Politician name to search for
Param[in] site:           Election site key from
    PoliticalPoller/election_site_configs.py, e.g. "mn"
Param[in] project_dir:    Path to the PoliticalPoller project (needed to
    import candidate_store.py, and for the live-fetch fallback)
Param[in] store_dir:      Directory the per-site candidate JSON files
    live in (see candidate_store.DEFAULT_STORE_DIR)
Param[in] headless:       Only used if the live-fetch fallback runs and
    `site` requires the browser path; pass False once if a site starts
    blocking, to solve a CAPTCHA manually
Param[in] force_refresh:  Skip the cache and go straight to a live scrape
    (still updates the store either way)
Param[out] matches:       List of candidate record dicts (candidate_name,
    state, first_seen, last_seen, offices: {office: {office_level,
    party, website, file_date, source_url, first_seen, last_seen}})
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def find_politician(
    name: str,
    site: str = "mn",
    project_dir: str = "PoliticalPoller",
    store_dir: str = None,
    headless: bool = False,
    force_refresh: bool = False,
) -> list:
    import datetime

    sys.path.append(project_dir)
    import candidate_store

    store_kwargs = {} if store_dir is None else {"store_dir": store_dir}

    if not force_refresh:
        cached_store = candidate_store.load_candidate_store(site, **store_kwargs)
        matches = candidate_store.search_by_name(cached_store, name)
        if matches:
            print(f"Found {len(matches)} cached match(es) for {name!r} in the saved {site!r} store.")
            _print_candidate_matches(matches)
            return matches
        print(f"No cached match for {name!r} in the saved {site!r} store -- checking the live site...")

    summary = sync_election_candidates(
        site, project_dir=project_dir, store_dir=store_dir, headless=headless
    )
    matches = candidate_store.search_by_name(summary["store"], name)

    if not matches:
        print(f"No candidate matching {name!r} found on site {site!r} (checked cache and live site).")
        return matches

    _print_candidate_matches(matches)

    output_filename = f"candidate_results_{datetime.date.today().isoformat()}.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=2)
    print(f"\nSaved to {output_filename}")

    return matches


if __name__ == "__main__":
    find_politician("test")
