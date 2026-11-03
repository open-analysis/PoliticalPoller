# Project Overview
Centralized site grab upcoming politician information \
**NOTE:** This is is not comprehensive list of information about any given political candidate, nor an endorsement any candidate

## Repository Layout
| Path | Purpose |
|---|---|
| `scripts/` | One run script per function (`find_politician.sh`, `sync_candidates.sh`, `run_election_spider.sh`, `run_news_spider.sh`, `read_page.sh`) plus shared venv setup in `common.sh` |
| `scrapy.cfg` | Scrapy project config (`settings = PoliticalPoller.settings`), at the repo root |
| `PoliticalPoller/site_reader.py` | Entry point / orchestration: `find_politician()`, `read_page()` (legacy one-off fetch) |
| `PoliticalPoller/spider_runner.py` | `run_news_spider()`, `run_election_spider()`, `sync_election_candidates()` |
| `PoliticalPoller/candidate_store.py` | Persists candidates to per-site JSON files (`candidate_data/candidates_<site>.json`); candidate identity, cycles, and review flags |
| `PoliticalPoller/site_configs.py` | News site configs (selectors, start URLs) used by the news spider |
| `PoliticalPoller/election_site_configs.py` | Government election site configs (e.g. `mn`) |
| `PoliticalPoller/probe_site.py`, `probe_site.sh` | Check a site config against a live or saved page (see Election Sites) |
| `tests/` | pytest unit tests (see Running the Tests) |
| `PoliticalPoller/election_table_parsers.py` | Shared table parsers (`colspan_hierarchy`, `simple_table`) |
| `PoliticalPoller/utils.py` | Fetch strategies (requests, Playwright, persistent browser) and HTML parsing helpers |
| `PoliticalPoller/spiders/` | Scrapy spiders: `news_spider.py` (`news`), `election_spider.py` (`elections`) |
| `PoliticalPoller/{items,pipelines,middlewares,settings}.py` | Scrapy project plumbing |
| `file_manipulation/file_reader.py` | Planned file readers (stubs) |
| `2026_state_candidate_list_sources.md` | Research on candidate-list sources for all 50 states |
| `sitePolicy.md`, `filePolicy.md`, `aiPolicy.md` | Scraping, code-documentation, and AI-usage policies |

## Getting Started
### Requirements
- Python 3.9+
- Git
- A Chromium install via Playwright (installed in the steps below)

### Setup
Assumes a virtual environment named `venv` already exists in the repo root, so create it first:
```bash
git clone https://github.com/open-analysis/PoliticalPoller.git
cd PoliticalPoller
python3 -m venv venv
source venv/bin/activate
pip3 install requests beautifulsoup4 playwright playwright-stealth scrapy
playwright install chromium
```

## Run Scripts

| Script | Wraps | Example |
|---|---|---|
| `scripts/find_politician.sh` | `find_politician()` | `scripts/find_politician.sh -n "Jane Doe" -s mn` |
| `scripts/sync_candidates.sh` | `sync_election_candidates()` | `scripts/sync_candidates.sh -s mn --headed` |
| `scripts/run_election_spider.sh` | `run_election_spider()` | `scripts/run_election_spider.sh -s mn -o mn.json` |
| `scripts/run_news_spider.sh` | `run_news_spider()` | `scripts/run_news_spider.sh -s cnn --candidate "Jane Doe" --location Minnesota` |
| `scripts/read_page.sh` | `read_page()` | `scripts/read_page.sh -u https://candidates.sos.mn.gov/ -m persistent_browser` |

Browser flags: `--headed` shows the Chromium window (needed the first time, to solve the Minnesota CAPTCHA); `--headless` hides it. `find_politician.sh` defaults to headed, the others default to headless, matching the Python defaults.

## Using the Python Functions Directly
The scripts are Python functions; call them from a Python shell or your own script. Run from the repo root with the venv active:
```python
import sys
sys.path.append("PoliticalPoller")
from site_reader import find_politician
from spider_runner import sync_election_candidates, run_election_spider, run_news_spider
```

### Look up a candidate: `find_politician()`
```python
find_politician("Jane Doe", site="mn")
```
1. Checks the saved candidate store for `site` first.
2. If there is no cached match (or `force_refresh=True`), scrapes the live site, saves the results to the store, and searches again.
3. Prints one JSON block per office the candidate has filed for (`candidate_name`, `office_level`, `office`, `party`, `website`, `file_date`) and writes matches to `candidate_results_<YYYY-MM-DD>.json` in the current directory.

| Parameter | Default | Meaning |
|---|---|---|
| `name` | required | Name (or part of a name) to search for |
| `site` | `"mn"` | Key from `election_site_configs.py` |
| `project_dir` | `"PoliticalPoller"` | Directory containing the Scrapy project |
| `store_dir` | `candidate_data` | Where per-site JSON stores live |
| `headless` | `False` | Browser window visible or not |
| `force_refresh` | `False` | Skip the cache and scrape live |

### Sync a site's candidate list: `sync_election_candidates()`
```python
summary = sync_election_candidates("mn", headless=False)
```
Scrapes the site and merges the results into `candidate_data/candidates_mn.json`. Existing candidates are refreshed, new ones added, and nothing is ever deleted automatically. It prints `+` new candidates, `»` new offices for known candidates, `~` updated records, and `!` possible same-name collisions. Run it each election cycle or periodically during filing season.

### Scrape without saving: `run_election_spider()` / `run_news_spider()`
```python
candidates = run_election_spider("mn", headless=False)
articles = run_news_spider("cnn", candidate="Jane Doe", election="2026", location="Minnesota")
```
- `run_election_spider()` returns a list of dicts (`site, state, office_level, office, candidate_name, party, website, file_date, source_url, scraped_at`). Sites with `requires_browser: True` use Playwright; others use `scrapy crawl elections`.
- `run_news_spider()` runs `scrapy crawl news` and returns `title, url, site, published_date, scraped_at`. The optional filters match against the article **title** only.

### Bot-protected sites (Minnesota)
`mn` sits behind a CAPTCHA. The first time, run with `headless=False`: a Chromium window opens, solve the CAPTCHA by hand, and the script continues (it waits up to 10 minutes). The browser profile is saved in `playwright_profile/`, so later runs usually work without solving again, including headless. Both `playwright_profile/` and `candidate_data/` are local state; the profile is git-ignored.

### One-off page fetch: `read_page()`
```python
from site_reader import read_page
read_page("https://candidates.sos.mn.gov/", method="persistent_browser")
```
`method` can be `persistent_browser` (default, recommended), `playwright`, or `requests`. The persistent browser keeps its solved-CAPTCHA session in `playwright_profile/`, so there is no separate cookie file to manage. This is the legacy single-site entry point; prefer the functions above.

### Add a new site
- **Election/candidate site:** add an entry to `ELECTION_SITE_CONFIGS` in `PoliticalPoller/election_site_configs.py` (`state`, `allowed_domains`, `start_urls`, `requires_browser`, `table_parser`, `table_parser_config`). Use `simple_table` with CSS selectors for flat tables or `colspan_hierarchy` for MN-style tables. Start from the states recommended in `2026_state_candidate_list_sources.md`.
- **News site:** add an entry to `SITE_CONFIGS` in `PoliticalPoller/site_configs.py` (`allowed_domains`, `start_urls`, `index_link_selectors`, `article_url_contains`).

No spider code changes are needed for either.

### Scrapy settings
`PoliticalPoller/settings.py` sets `ROBOTSTXT_OBEY = True`, a 1-second download delay, and AutoThrottle. The `USER_AGENT` still contains placeholder contact info (`example.com`); replace it before real crawling.

## Candidate Identity and Review Flags
`candidate_store.py` decides whether a scraped row is a person it already has. In order:

1. **Site-issued ID (strongest).** If a site shows a filer/candidate ID, set `filer_id_selector` (`simple_table`) or `filer_id_index` (`colspan_hierarchy`) in that site's `table_parser_config`. Rows then carry `filer_id`, and the store uses it as the identity (via `candidate_hash(..., extra="filer:<id>")`): the same ID always lands on the same candidate, even if the name is respelled, and same-named people with different IDs are never merged. A name-only record that already exists gets the ID attached, keeping its history, unless the party and website both disagree.
2. **Name + state, with a check before merging.** When a name-only match would get a *new office or new cycle*, the store compares the new row to the candidate's latest filing: party (case-insensitive) and website domain (ignoring `www.`), only when both sides have a value.
   - Party **and** website differ: kept as a separate record (scoped to the office), the name goes on the collisions list (`_collisions`), and a `split_conflict` flag is raised.
   - Only one differs: merged, with a `party_changed` or `website_changed` flag, since a party switch or a new campaign site between cycles is common.
   - Pass `split_policy="either"` to `upsert_candidates()` to split when either one differs.
   - The same office in the same cycle is just a refresh of the same filing and is never split.
3. **Same-scrape collisions.** Two different offices under one name in one scrape are treated as two people, as before.

**Cycles.** Each office entry stores `cycle`, the year in `file_date` (`2026-05-26`, `5/26/2026`, and `5/26/26` all work; no readable year means no cycle checks for that row). The candidate has a sorted `cycles` list. If the same office is filed again in a later cycle, the earlier values are kept in that entry's `history` list. A name-only match more than `CYCLE_GAP_WARN_YEARS` (6) from every cycle on file raises a `cycle_gap` flag. Note the cycle is the *filing* year, so a site that opens filing the year before the election reports the earlier year.

**Reviewing flags.** Flags are stored in the candidate file under `_review` and printed at the end of every sync:
```
  ? review [party_changed] Al Kim: party 'DFL' -> 'GOP' (now Senator, cycle 2024) (flag 72317257942f)
```
```python
import candidate_store
candidate_store.list_review_flags("mn")                       # open flags
candidate_store.dismiss_review_flag("mn", "72317257942f", "checked, same person")
```
Flags never block a merge on their own, and a dismissed flag is not raised again.

## Election Sites
`election_site_configs.py` has a config per state. Fourteen open state sites use the `header_table` parser, which finds columns by their **header text** instead of by position or CSS class, so a reordered or extra column does not break it:

| State | Start URLs | Verified? | Coverage and known gaps |
|---|---|---|---|
| WA | `CandidateList.aspx?e=899`, plus `&c=1..40` (one per county) | layout seen | Includes county and local races. Pages 100 rows at a time through a postback that is not performed, so big lists are incomplete (a warning is logged) |
| OK | `filings.okelections.gov/ViewCandidates/<dates>/99/all` | URL only | County code `99` = all counties. May be JavaScript-rendered |
| KY | `CandidateFilings/default.aspx?id=1..27`, plus `countyfilings.aspx` | layout seen | `id` is an office category. The county page is a postback form |
| FL | `CanList.asp?elecid=20261103-GEN` | URL only | No county races; status mapped to `status` |
| MO, IL | `displaycandidatesplacement.aspx`, `CandidateList.aspx` | URL only | ASP.NET WebForms; the election choice may be a postback |
| AK | `candidates/?election=26gen` | URL only | `26gen` is inferred from `26prim` |
| MD, VA, DE | statewide + all-counties (MD), index + local offices (VA), `genl_fcddt_2026.html` (DE) | URL only | VA's index page links to its lists; Excel exports exist and are not read |
| SD | `candidatelist.aspx?eid=774` | layout seen | General election; `eid=773` is the primary |
| MT, ND, NM | `CandidateList.aspx?e=`/`eid=` | URL only | The ids are the **primary** ids from the research notes; the general-election ids still need to be found |

**"Layout seen"** means the live page's column headers were read and the config was checked against them (with synthetic data, in `tests/fixtures/`). **"URL only"** means the URL comes from `2026_state_candidate_list_sources.md` and the table layout is *assumed*. I could not fetch raw HTML for these, so selectors were not checked. Run the probe on each before trusting it.

### Checking a site: `probe_site.sh`
```bash
./probe_site.sh wa                          # fetch the site's first start URL and parse it
./probe_site.sh ok --browser                # fetch with Playwright instead (JavaScript pages)
./probe_site.sh fl --save fl.html           # keep the page as a test fixture
./probe_site.sh fl --html fl.html           # re-run the parser on a saved page
```
It prints the tables it found, how many candidates it parsed, a few samples, and a diagnosis when there are none (no `<table>` means JavaScript; unrecognised headers are listed so you can add them to `header_aliases`; a CAPTCHA page; a paged grid). The exit status is 0 when at least one candidate was parsed.

### `header_table` options
Set in a site's `table_parser_config` (all optional): `header_aliases` (`{field: [labels]}` for headers it does not know), `table_selector`, `group_rows` (`"office"` or `"office_level"` when the office is a row above its candidates), `skip_office_patterns` (e.g. ballot amendments), `skip_names`. The office is built from the office column plus the district column (`State Senator (6th)`), so the same race in different districts stays distinct.

Records now also carry `status` (Active, Withdrawn, Qualified, ...) when the site shows one. Washington lists withdrawn candidates, so check `status` before treating a row as a current candidate.

## Running the Tests
```bash
source venv/bin/activate
pip3 install pytest pytest-cov
python3 -m pytest                                  # whole suite
python3 -m pytest tests/test_candidate_store.py    # one file
python3 -m pytest --cov=PoliticalPoller --cov-report=term-missing
```
The suite needs no network, browser, or CAPTCHA: Scrapy callbacks run against canned `HtmlResponse`s, `subprocess.run` and the Playwright fetchers are replaced with fakes, and candidate stores are written to pytest's temp directories.

| File | Covers |
|---|---|
| `test_candidate_store.py` | hashing, persistence, upsert, filer IDs, party/website corroboration and splits, cycles, review flags |
| `test_election_table_parsers.py` | the colspan and simple table parsers, the dispatcher, record stamping |
| `test_header_table.py` | the header-text table parser: column mapping, offices, group rows, nesting |
| `test_state_configs.py` | the 14 state configs, end to end on fixtures shaped like the WA, KY and SD pages |
| `test_probe_site.py` | the probe tool and its diagnoses |
| `test_utils.py` | HTML parsing helpers, block detection, `fetch_soup`, `get_base_url` |
| `test_spiders.py` | `NewsSpider` and `ElectionSpider` callbacks and setup errors |
| `test_spider_runner.py` | `run_news_spider`, `run_election_spider`, `sync_election_candidates` |
| `test_site_reader.py` | `read_page` dispatch, `find_politician` cache/refresh behaviour |
| `test_pipelines.py`, `test_site_configs.py` | validation pipelines; every site config is well-formed |

Not unit-tested: the real-browser fetchers (`fetch_soup_persistent_browser`, `fetch_soup_playwright`), the generated Scrapy `settings.py`/`middlewares.py`, and the `__main__` block.

## Known Issues
- `_looks_solved()` in `utils.py` is hard-coded to `candidates.sos.mn.gov`, so the manual-CAPTCHA flow only works for Minnesota.
- For sites that expose no filer/candidate ID (Minnesota's config doesn't use one yet), identity is still name + state, backed by the party/website checks above. Two different people with the same name, party, and website domain would still be merged; the cycle-gap flag is the main safeguard.

- With the default `header_td_count` of 6, a `colspan_hierarchy` data row that has 6 cells is silently skipped (it looks like the column-header row). A site config that adds a filer-ID column needs `header_td_count` overridden as well as `data_row_td_count`.

## Support
Open issues for:
- Missing candidates
- Missing election information
- Missing news sites
- Add user to collaborators list
- Problems with the service
- Efficiency improvements for the service

---

## TODO:
### Initial politician search
1. ~~Walkthrough list of sites~~
    1. ~~How to handle robots.txt?~~
    2. ~~Read in list of sites from a file~~
2. ~~Use scrapy to walkthrough the site for relevant links~~
    1. ~~Search for politicians~~
    2. ~~Search for politician information~~
3. ~~Scrape w/ appropriate tool~~
    - ~~Beautiful Soup - static~~
    - ~~Playwright -dynamic sites~~
    - ~~BeeScrapers - API/anti-bot/etc~~
4. ~~Save information to politician file~~
5. Compress

### Scraped politician
1. Walkthrough politician file's links for invalid links
    1. Remove invalid links
    2. Remove links that don't match the title
2. ~~Walkthrough list of sites~~
    2. ~~Read in list of sites from a file~~
3. ~~Use scrapy to walkthrough the site for relevant links~~
    2. ~~Search for politician information~~
4. ~~Scrape w/ appropriate tool~~
    - ~~Beautiful Soup - static~~
    - ~~Playwright -dynamic sites~~
    - ~~BeeScrapers - API/anti-bot/etc~~
5. ~~Update information to politician file~~
6. Compress

### Setup and packaging
1. ~~Reconcile the `scraper/` vs `PoliticalPoller` package name (rename the folder, move `scrapy.cfg` to the repo root)~~
2. ~~Remove the nonexistent `PoliticalpollerPipeline` from `ITEM_PIPELINES` in `settings.py`~~
3. Add a `requirements.txt` (or `pyproject.toml`) with pinned dependencies
4. Replace the placeholder `USER_AGENT` contact info in `settings.py`
5. Add `candidate_data/` and `candidate_results_*.json` to `.gitignore`
6. Replace the bash heredocs in `scripts/` with a proper Python CLI (`argparse`) if the scripts grow

### Code gaps
1. Implement `read_sites_file()` and `read_politician_file()` in `file_manipulation/file_reader.py` (and add the `typing.List` import)
2. Add `find_political_assoc()` back once it is implemented (office, state, district, party, group affiliations, bills/orders)
3. Generalize `_looks_solved()` / block detection beyond Minnesota
4. ~~Add a stronger candidate identifier to `candidate_hash()` when a site exposes one~~ (done: `filer_id`; see Candidate Identity). Still to do: check each state's candidate page for a filer/candidate ID (Minnesota's included) and set `filer_id_selector` / `filer_id_index` where one exists
5. ~~Add tests~~ (done: `tests/`). Still to do: add a CI workflow that runs `python3 -m pytest`, and browser-level tests for the Playwright fetchers

### More sources
1. ~~Add election site configs for WA, OK, KY, FL, MO, IL, AK, MD, VA, DE, MT, ND, SD, NM~~ (done, see Election Sites). Still to do:
    - run `./probe_site.sh <state>` on each "URL only" state and fix its config
    - find the general-election ids for MT, ND and NM
    - add postback support for paged or form-driven sites (WA's 100-row pages, KY county filings, MO, IL)
    - add the remaining ~18 live-HTML states
2. Add document parsing (PDF/XLSX) for the 16 states that publish only documents; follow landing-page links since filenames change
3. Handle county-decentralized states (TX, OH)
4. Test each state site for bot protection and ASP.NET ViewState/postback handling
5. Add news site configs beyond `cnn` (local and state organizations first, per `sitePolicy.md`)
6. Add candidate summarizer sites from `sitePolicy.md` (knowyourvotes.com, whoisrunning.org, kyc.vote, theballotbrief.com, ballotmatch.org)
7. Add a body/snippet field to `NewsArticleItem` so news filtering can go beyond titles

---

# Developer Support
[Buy me a Ko-Fi](https://ko-fi.com/opnanalysis)
