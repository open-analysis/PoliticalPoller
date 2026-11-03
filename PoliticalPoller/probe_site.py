# -*- coding: utf-8 -*-

"""
Description: Checks one election-site config against a real page, so a new
    state can be verified (or its selectors fixed) in one command instead of
    by trial and error. Fetches the site's first start URL (or the --url you
    give, or a saved --html file), runs the configured parser on it, and
    prints what was found plus a diagnosis when nothing was:

      - no <table> at all        -> probably JS-rendered; try --browser
      - looks like a CAPTCHA     -> needs the browser path (--browser --headed)
      - tables but zero records  -> prints the header labels it saw, which
                                    is what to add to header_aliases
      - "N items in M pages"     -> the page is paged; only page 1 was read

    Use --save FILE to keep the fetched HTML as a test fixture.
LLM: claude-sonnet-5.5
"""

import argparse
import json
import os
import re
import sys

from parsel import Selector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from election_site_configs import get_election_site_config  # noqa: E402
from election_table_parsers import parse_table  # noqa: E402

_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PoliticalPoller-probe; +https://github.com/open-analysis/PoliticalPoller)",
    "Accept": "text/html,application/xhtml+xml",
}


"""
Description: Fetches a page's HTML with plain requests, or with the
    persistent Playwright browser when `browser` is set.
Param[in] url:      Page to fetch
Param[in] browser:  Use the browser path (JS pages, CAPTCHAs)
Param[in] headless: Hide the browser window (browser path only)
Param[out] html:    The page's HTML
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def fetch_html(url: str, browser: bool = False, headless: bool = True) -> str:
    if browser:
        from utils import fetch_soup_persistent_browser
        return str(fetch_soup_persistent_browser(url, headless=headless))
    import requests
    response = requests.get(url, headers=_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


"""
Description: Runs a site's configured parser over HTML and summarizes the
    result: table structure, parsed records, and a list of plain-English
    diagnostics for the common ways a config fails to match a page.
Param[in] site:   Election site key, e.g. "wa"
Param[in] html:   The page's HTML
Param[in] url:    Where it came from (for the report only)
Param[in] show:   How many sample records to include
Param[out] report: Dict with site, url, verification, tables, records
    (count), sample, columns_missing, diagnostics
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def probe_html(site: str, html: str, url: str = "", show: int = 3) -> dict:
    config = get_election_site_config(site)
    selector = Selector(text=html)
    tables = selector.css("table")
    table_summaries = []
    for table in tables[:5]:
        rows = table.xpath("./tr | ./thead/tr | ./tbody/tr")
        first = rows[0].xpath("./th | ./td") if rows else []
        table_summaries.append({
            "rows": len(rows),
            "first_row": [" ".join(" ".join(c.xpath(".//text()").getall()).split()) for c in first][:15],
        })

    records = parse_table(selector, config["table_parser"], config.get("table_parser_config", {}))

    diagnostics = []
    text = html.lower()
    if re.search(r"captcha|radware|incident id|access denied|unusual traffic", text):
        diagnostics.append("The page looks like a CAPTCHA / bot-protection page; try --browser --headed.")
    if not tables:
        diagnostics.append("No <table> in the page. It is probably rendered by JavaScript; try --browser, "
                           "and if that shows a table, set requires_browser=True for this site.")
    elif not records:
        labels = sorted({t for s in table_summaries for t in s["first_row"] if t})
        diagnostics.append("Tables were found but no candidate rows were parsed. Header labels seen: "
                           f"{labels}. Add the ones for name/office/party to table_parser_config"
                           "['header_aliases'] (header_table) or fix the selectors (simple_table).")
    elif sum(1 for r in records if not r.get("office")) > len(records) / 2:
        diagnostics.append("Most records have no office: the office column was not recognised. Add its "
                           "header label to header_aliases['office'], or set group_rows='office' if the "
                           "office is a row above its candidates.")
    hint = config.get("pagination_hint_regex")
    match = re.search(hint, html) if hint else None
    if match and int(match.group(2)) > 1:
        diagnostics.append(f"The page lists {match.group(1)} items over {match.group(2)} pages; "
                           "only the first page is read, so this URL is incomplete.")

    return {
        "site": site,
        "url": url,
        "verification": config.get("verification"),
        "tables": table_summaries,
        "records": len(records),
        "sample": records[:show],
        "diagnostics": diagnostics,
    }


"""
Description: CLI entry point; see the module docstring.
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check an election-site config against a real page.")
    ap.add_argument("site", help="site key from election_site_configs.py, e.g. wa")
    ap.add_argument("--url", help="page to probe (default: the site's first start URL)")
    ap.add_argument("--html", help="probe a saved HTML file instead of fetching")
    ap.add_argument("--browser", action="store_true", help="fetch with the Playwright browser")
    ap.add_argument("--headed", action="store_true", help="show the browser window (CAPTCHAs)")
    ap.add_argument("--save", help="write the fetched HTML to this file (to use as a test fixture)")
    ap.add_argument("--show", type=int, default=3, help="sample records to print")
    args = ap.parse_args(argv)

    config = get_election_site_config(args.site)
    url = args.url or config["start_urls"][0]
    if args.html:
        with open(args.html, encoding="utf-8") as f:
            html = f.read()
    else:
        html = fetch_html(url, browser=args.browser or config.get("requires_browser", False),
                          headless=not args.headed)
    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(html)

    report = probe_html(args.site, html, url=url, show=args.show)
    print(json.dumps(report, indent=2))
    return 0 if report["records"] else 1


if __name__ == "__main__":
    sys.exit(main())
