"""
Description: This file contains the various site reader/scraping functions.

The page renders a single results table where each <tr> has up to 6 <td>
cells that encode a hierarchy through *which column* has text:

    col 0 -> Office Level   (e.g. "Federal Offices", "State Offices")
    col 1 -> Office/Race    (e.g. "U.S. Senator", "State Senator District 1")
    col 2 -> Candidate Name (or the literal header "Candidate Name")
    col 3 -> Party
    col 4 -> Website
    col 5 -> File Date

Rows that only set col 0 or col 1 are "header" rows that update the current
context; blank rows are separators; rows with a real name in col 2 are
candidate records.
LLM: claude-sonnet-5
"""

import logging
import json
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '../utils'))
import custom_exceptions

# A more browser-like header set. A bare User-Agent alone is an easy
# fingerprint for bot-detection; matching what a real Chrome request sends
# (Accept, Accept-Language, Accept-Encoding, Sec-Fetch-* hints) makes the
# request look far less automated.
# LLM: claude-sonnet-5
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

def get_base_url(url:str) -> str:
    domain_names = [".gov", ".com", ".org", ".net"]
    base_url = ""
    for domain in domain_names:
        if domain in url:
            base_url = url.split(domain, 1)[0]
            logging.debug(f"Base URL ({base_url}) found")
            break
    if base_url == "":
        raise UnableToFindBaseUrlError(url, domain_names)
    return base_url

"""
Description: Builds a requests.Session with full browser-like headers and
    performs a warm-up GET against the site's base URL first, so any
    anti-bot session cookies the site issues on first contact get captured
    and replayed on the real request.
Param[out] session:  A requests.Session pre-loaded with browser headers
    and warm-up cookies
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def make_session(base_url: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        warm_up = session.get(base_url, timeout=30)
        print(f"Warm-up request to {base_url} -> status {warm_up.status_code}, "
              f"{len(warm_up.text)} bytes, cookies: {list(session.cookies.keys())}")
    except requests.RequestException as e:
        print(f"Warm-up request failed (continuing anyway): {e}")

    return session


"""
Description: Fetches the candidate results page using a plain
    requests.Session and returns it as parsed BeautifulSoup. Raises if the
    response looks like a CAPTCHA/bot-protection page instead of the real
    results table.
Param[in] url:      Page URI to fetch
Param[in] session:  Optional pre-built session (falls back to
    make_session() if not provided)
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def fetch_soup(url: str, session: requests.Session = None) -> BeautifulSoup:
    """Fetch the page and return a parsed BeautifulSoup object."""
    if session is None:
        session = make_session(get_base_url(url))

    res = session.get(url, timeout=30)
    res.raise_for_status()

    if "captcha" in res.text.lower() or "incident id" in res.text.lower():
        raise RuntimeError(
            "Blocked by a CAPTCHA/bot-protection page instead of the real "
            "results page. Session headers/cookies weren't enough to get "
            "through this time -- browser automation or a CAPTCHA-solving "
            "service would be the next step."
        )

    return BeautifulSoup(res.content, "html.parser")


DEFAULT_COOKIE_FILE = "session_cookies.json"

"""
Description: Fetches the page by replaying a previously-solved session
    (cookies + user agent) from a saved JSON cookie file through plain
    requests, avoiding a browser entirely for the actual scrape. Raises if
    the site still blocks the request, which likely means the site
    revalidates the client's TLS/JS fingerprint per-request rather than
    trusting the cookie alone.
Param[in] url:          Page URI to fetch
Param[in] cookie_file:  Path to the saved session JSON produced by
    capture_session.py
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def fetch_soup_cached_session(
    url: str, cookie_file: str = DEFAULT_COOKIE_FILE
) -> BeautifulSoup:
    """
    Note: this can still fail if the site's bot-detection ties its risk
    decision to more than just the cookie value (e.g. re-checking the TLS
    or JS fingerprint of the *client making each request*, not just the
    session token) -- `requests` has a different TLS fingerprint than a
    real browser. If this raises the "still blocked" error below, re-run
    capture_session.py, and if it keeps failing even right after a fresh
    capture, that's a sign the site is doing exactly this kind of
    per-request revalidation and cookie reuse alone won't be enough.
    """
    try:
        with open(cookie_file, "r") as f:
            saved = json.load(f)
    except FileNotFoundError:
        raise RuntimeError(
            f"No saved session found at {cookie_file!r}. Run "
            "capture_session.py first to manually solve the CAPTCHA once "
            "and save a reusable session."
        )

    session = requests.Session()
    session.headers.update(HEADERS)
    if saved.get("user_agent"):
        session.headers["User-Agent"] = saved["user_agent"]

    for cookie in saved["cookies"]:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain", ""),
            path=cookie.get("path", "/"),
        )

    res = session.get(url, timeout=30)
    res.raise_for_status()

    if "captcha" in res.text.lower() or "radware" in res.text.lower():
        raise RuntimeError(
            f"Still blocked even with the cookies saved in {cookie_file!r}. "
            "Either the session expired, or this site re-validates more "
            "than just the cookie per request (see note above). Re-run "
            "capture_session.py for a fresh session and try again."
        )

    return BeautifulSoup(res.content, "html.parser")


DEFAULT_PROFILE_DIR = "playwright_profile"

"""
Description: Returns True if the given page HTML contains signs of a
    CAPTCHA/bot-protection challenge (e.g. "captcha" or "radware").
Param[in] content:  Raw page HTML to inspect
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _looks_blocked(content: str) -> bool:
    lowered = content.lower()
    return "captcha" in lowered or "radware" in lowered

"""
Description: Returns True if the given Playwright page is on the
    candidates site, not showing a block page, and appears to contain the
    real results table -- used to detect when a manually-solved CAPTCHA
    has cleared.
Param[in] page:  Live Playwright page object to inspect
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _looks_solved(page) -> bool:
    if "candidates.sos.mn.gov" not in page.url:
        return False
    content = page.content()
    if _looks_blocked(content):
        return False
    return "Candidate Name" in content or "<table" in content.lower()

"""
Description: Fetches the page using a real Chromium browser with a
    persistent, on-disk profile so cookies/fingerprint stay consistent
    across runs. If blocked and running with a visible window, pauses and
    polls until a human manually solves the CAPTCHA, then continues; if
    headless with no window available, raises immediately with
    instructions to rerun non-headless once. This is the recommended
    method since keeping the solve and the scrape in one consistent
    browser identity avoids the TLS/JS fingerprint mismatch that breaks
    fetch_soup_cached_session.
Param[in] url:                  Page URI to fetch
Param[in] user_data_dir:        Folder to persist the browser profile in
Param[in] headless:             Whether to run without a visible window
Param[in] manual_wait_seconds:  Max seconds to wait for a manual CAPTCHA
    solve when headless=False and a block is detected
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def fetch_soup_persistent_browser(
    url: str,
    user_data_dir: str = DEFAULT_PROFILE_DIR,
    headless: bool = True,
    manual_wait_seconds: int = 600,
) -> BeautifulSoup:
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=headless,
            viewport={"width": 1920, "height": 1080},
        )
        stealth = Stealth()
        stealth.apply_stealth_sync(context)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        content = page.content()

        if _looks_blocked(content):
            if headless:
                context.close()
                raise RuntimeError(
                    "Blocked, and running headless so there's no window to "
                    "solve a CAPTCHA in. Re-run with headless=False once to "
                    "solve it manually -- the persistent profile will then "
                    "keep working (including headless=True) until the "
                    "session expires again."
                )

            print("Blocked. Please solve the CAPTCHA in the browser window...")
            waited = 0
            last_message_at = 0
            while waited < manual_wait_seconds:
                if _looks_solved(page):
                    print("Looks solved! Continuing...")
                    break
                if waited - last_message_at >= 15:
                    print(f"  ...still waiting ({waited}s elapsed)")
                    last_message_at = waited
                time.sleep(1)
                waited += 1
            else:
                context.close()
                raise TimeoutError(
                    f"Gave up after {manual_wait_seconds}s without detecting "
                    "a solved page."
                )

            content = page.content()

        context.close()

        if _looks_blocked(content):
            raise RuntimeError(
                "Still blocked after the solve attempt. Something's off -- "
                "worth inspecting a fresh debug_page.html-style dump here."
            )

        return BeautifulSoup(content, "html.parser")

"""
Description: Fetches the page using a fresh, stealth-patched Playwright
    browser with no session persistence between runs. Since this site's
    CAPTCHA requires solving, a fresh unauthenticated browser hits the
    wall on every call; kept only for reference/comparison against
    fetch_soup_persistent_browser.
Param[in] url:                        Page URI to fetch
Param[in] headless:                   Whether to run without a visible
    window
Param[in] page_load_timeout_ms:       Timeout for page navigation/table
    wait, in milliseconds
Param[in] extra_wait_if_blocked_s:    Extra seconds to wait and recheck if
    a CAPTCHA page is detected, in case it's a timed challenge
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def fetch_soup_playwright(
    url: str,
    headless: bool = True,
    page_load_timeout_ms: int = 20000,
    extra_wait_if_blocked_s: int = 10,
) -> BeautifulSoup:
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=page_load_timeout_ms)

            try:
                page.wait_for_selector("table", timeout=page_load_timeout_ms)
            except PlaywrightTimeoutError:
                pass  # fall through and check content below regardless

            content = page.content()

            if "captcha" in content.lower() or "incident id" in content.lower():
                print(
                    f"CAPTCHA page detected. Waiting an extra "
                    f"{extra_wait_if_blocked_s}s in case it's a timed challenge..."
                )
                time.sleep(extra_wait_if_blocked_s)
                content = page.content()

            if "captcha" in content.lower() or "incident id" in content.lower():
                raise RuntimeError(
                    "Still blocked by CAPTCHA even with Playwright + stealth. "
                    "Next steps: try headless=False, or use a CAPTCHA-solving "
                    "service (2Captcha/Anti-Captcha/CapSolver) to "
                    "programmatically solve the challenge shown on this page."
                )

            return BeautifulSoup(content, "html.parser")

        finally:
            browser.close()

"""
Description: Returns the stripped visible text of a <td>, or an empty
    string if the cell is None.
Param[in] td:  BeautifulSoup <td> tag to read
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _cell_text(td) -> str:
    return td.get_text(strip=True) if td is not None else ""

"""
Description: Extracts a candidate's website value from a <td>, preferring
    the href of an embedded <a> link and falling back to its visible text;
    ignores empty or placeholder hrefs (e.g. "javascript:...", bare
    "http://").
Param[in] td:  BeautifulSoup <td> tag containing the website cell
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _extract_website(td) -> str:
    if td is None:
        return ""
    a = td.find("a")
    if a is not None:
        href = a.get("href", "").strip()
        # Ignore empty/placeholder hrefs like "http://" or "javascript:..."
        if href and not href.lower().startswith("javascript:") and href.lower() != "http://":
            return href
        text = a.get_text(strip=True)
        if text:
            return text
        return ""
    return _cell_text(td)

"""
Description: Returns the integer colspan attribute of a <td>, defaulting
    to 1 if missing or unparseable.
Param[in] td:  BeautifulSoup <td> tag to read
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _colspan(td) -> int:
    try:
        return int(td.get("colspan", 1))
    except (TypeError, ValueError):
        return 1

"""
Description: Walks every <tr> in the parsed results page in document
    order, tracking the current office level and office name as they
    appear in header rows, and emits one record per candidate data row
    encountered.
Param[in] soup:  Parsed BeautifulSoup of the results page
Param[out] records:  Flat list of dicts, each with level, office, name,
    party, website, file_date
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def parse_candidates(soup: BeautifulSoup) -> list:
    """
    Row shapes, confirmed against the real site markup (not just a
    markdown-flattened guess):

      Level row   (e.g. "Federal Offices"):
          1 <td colspan="6"> containing the label.

      Office row  (e.g. "U.S. Senator"):
          2 <td>s -- a small empty spacer <td>, then a
          <td colspan="5"> containing the label.

      Column header row ("Candidate Name" / "Party" / "Website" / "File Date"):
          6 separate <td>s, with "Candidate Name" in the 3rd.

      Candidate data row:
          5 <td>s -- an empty <td colspan="2"> (collapsing what would be
          the first two columns), then name / party / website / file date.
    """
    records = []
    current_level = None
    current_office = None

    rows = soup.find_all("tr")

    for tr in rows:
        tds = tr.find_all("td", recursive=False) or tr.find_all("td")
        if not tds:
            continue

        # --- Level row: single td, colspan >= 6 ---
        if len(tds) == 1 and _colspan(tds[0]) >= 6:
            label = _cell_text(tds[0])
            if label:
                current_level = label
            continue

        # --- Office row: 2 tds, second has colspan >= 5 ---
        if len(tds) == 2 and _colspan(tds[1]) >= 5:
            label = _cell_text(tds[1])
            if label:
                current_office = label
            continue

        # --- Column header row: 6 separate tds ---
        if len(tds) == 6:
            if _cell_text(tds[2]) == "Candidate Name":
                continue  # just the header labels, not data
            # An unexpected 6-td row that isn't the header -- skip rather
            # than misparse, since we don't have confirmed evidence of
            # this shape carrying real data.
            continue

        # --- Candidate data row: 5 tds, first is an empty colspan=2 spacer ---
        if len(tds) == 5 and _colspan(tds[0]) == 2:
            name = _cell_text(tds[1])
            if not name:
                continue  # no real candidate name; skip
            party = _cell_text(tds[2])
            website = _extract_website(tds[3])
            file_date = _cell_text(tds[4])

            records.append(
                {
                    "level": current_level,
                    "office": current_office,
                    "name": name,
                    "party": party,
                    "website": website,
                    "file_date": file_date,
                }
            )
            continue

        # Any other row shape (page chrome, nav, unrelated tables elsewhere
        # on the page) is intentionally ignored.

    return records

"""
Description: Reshapes a flat list of candidate records into a nested dict
    keyed first by office level, then by office name, each mapping to a
    list of candidate detail dicts.
Param[in] records:  Flat list of candidate dicts, as produced by
    parse_candidates
Param[out] grouped:  Nested dict of { level: { office: [candidates] } }
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def group_by_office(records: list) -> dict:
    grouped = {}
    for r in records:
        level = r["level"] or "Unknown Level"
        office = r["office"] or "Unknown Office"
        candidate = {
            "name": r["name"],
            "party": r["party"],
            "website": r["website"],
            "file_date": r["file_date"],
        }
        grouped.setdefault(level, {}).setdefault(office, []).append(candidate)
    return grouped

"""
Description: Fetches, parses, and groups the candidate results page in one
    call, choosing among the available fetch strategies (persistent
    browser, cached session, fresh playwright, or plain requests).
Param[in] input_webpage:  URI for the webpage to be read
Param[in] method:         Fetch strategy to use -- "persistent_browser"
    (default, recommended), "cached_session", "playwright", or "requests"
Param[in] headless:       Used by "persistent_browser"/"playwright"; try
    headless=False once if blocked, to solve manually
Param[in] cookie_file:    Only used by "cached_session"
Param[in] user_data_dir:  Only used by "persistent_browser"
Owner: @opnanalysis
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
            url, user_data_dir=user_data_dir, headless=headless
        )
    elif method == "cached_session":
        soup = fetch_soup_cached_session(url, cookie_file=cookie_file)
    elif method == "playwright":
        soup = fetch_soup_playwright(url, headless=headless)
    elif method == "requests":
        session = make_session()
        soup = fetch_soup(url, session=session)
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
Owner: @opnanalysis
"""
def find_political_assoc(name: str, assoc: str):
    pass

"""
Description: Finds a given politician information
Param[in] name:     Politician name to search for
Owner: @opnanalysis
"""
def find_politician(name: str):
    # temporary test
    import datetime

    data = read_page(method="persistent_browser", headless=False)
    print(json.dumps(data, indent=2))

    output_filename = f"candidate_results_{datetime.date.today().isoformat()}.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"\nSaved to {output_filename}")


if __name__ == "__main__":
    find_politician("test")