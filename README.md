# Project Overview
Centralized site grab upcoming politician information \
**NOTE:** This is is not comprehensive list of information about any given political candidate, nor an endorsement any candidate

## Repository Layout
| Path | Purpose |
|---|---|
| `run.sh` | Convenience script: activates the venv, installs dependencies, runs `scraper/site_reader.py` |
| `scripts/` | One run script per function (`find_politician.sh`, `sync_candidates.sh`, `run_election_spider.sh`, `run_news_spider.sh`, `read_page.sh`) plus shared venv setup in `common.sh` |
| `scraper/scrapy.cfg` | Scrapy project config (`settings = PoliticalPoller.settings`) |
| `scraper/site_reader.py` | Entry point / orchestration: `find_politician()`, `read_page()` (legacy one-off fetch), `find_political_assoc()` (stub) |
| `scraper/spider_runner.py` | `run_news_spider()`, `run_election_spider()`, `sync_election_candidates()` |
| `scraper/candidate_store.py` | Persists candidates to per-site JSON files (`candidate_data/candidates_<site>.json`) |
| `scraper/site_configs.py` | News site configs (selectors, start URLs) used by the news spider |
| `scraper/election_site_configs.py` | Government election site configs (e.g. `mn`) |
| `scraper/election_table_parsers.py` | Shared table parsers (`colspan_hierarchy`, `simple_table`) |
| `scraper/utils.py` | Fetch strategies (requests, cached session, Playwright, persistent browser) and HTML parsing helpers |
| `scraper/spiders/` | Scrapy spiders: `news_spider.py` (`news`), `election_spider.py` (`elections`) |
| `scraper/{items,pipelines,middlewares,settings}.py` | Scrapy project plumbing |
| `file_manipulation/file_reader.py` | Planned file readers (stubs) |
| `2026_state_candidate_list_sources.md` | Research on candidate-list sources for all 50 states |
| `sitePolicy.md`, `filePolicy.md`, `aiPolicy.md` | Scraping, code-documentation, and AI-usage policies |

## Getting Started
### Requirements
- Python 3.9+
- Git
- A Chromium install via Playwright (installed in the steps below)

### Setup
`run.sh` assumes a virtual environment named `venv` already exists in the repo root (the creation line is commented out), so create it first:
```bash
git clone https://github.com/open-analysis/PoliticalPoller.git
cd PoliticalPoller
python3 -m venv venv
source venv/bin/activate
pip3 install requests beautifulsoup4 playwright playwright-stealth scrapy
playwright install chromium
```

### Running with `run.sh`
```bash
./run.sh
```
This activates `venv`, installs the pip modules, installs Chromium for Playwright, then runs `python3 scraper/site_reader.py`. Running that file directly calls `find_politician("test")` against the Minnesota (`mn`) site, so edit the `__main__` block at the bottom of `scraper/site_reader.py` to search for a real name.

## Run Scripts
Each script in `scripts/` wraps one Python function and uses the same venv setup as `run.sh` (shared in `scripts/common.sh`): it creates `./venv` if missing, activates it, installs the pip modules and Chromium on the first run only (delete `venv/.deps_installed` to force a reinstall), then deactivates on exit. Outputs (`candidate_data/`, `candidate_results_<date>.json`, `playwright_profile/`) are written to the repo root. Run any script with `-h` for its options.

| Script | Wraps | Example |
|---|---|---|
| `scripts/find_politician.sh` | `find_politician()` | `scripts/find_politician.sh -n "Jane Doe" -s mn` |
| `scripts/sync_candidates.sh` | `sync_election_candidates()` | `scripts/sync_candidates.sh -s mn --headed` |
| `scripts/run_election_spider.sh` | `run_election_spider()` | `scripts/run_election_spider.sh -s mn -o mn.json` |
| `scripts/run_news_spider.sh` | `run_news_spider()` | `scripts/run_news_spider.sh -s cnn --candidate "Jane Doe" --location Minnesota` |
| `scripts/read_page.sh` | `read_page()` | `scripts/read_page.sh -u https://candidates.sos.mn.gov/ -m persistent_browser` |

Browser flags: `--headed` shows the Chromium window (needed the first time, to solve the Minnesota CAPTCHA); `--headless` hides it. `find_politician.sh` defaults to headed, the others default to headless, matching the Python defaults.

**Scrapy workaround:** the spiders import `PoliticalPoller.*` but the code lives in `scraper/`. `common.sh` creates a temporary `PoliticalPoller -> scraper` symlink on `PYTHONPATH` for each run so `scrapy crawl` can import the project. Nothing is added to the repo.

## Using the Python Functions Directly
The scripts are Python functions; call them from a Python shell or your own script. Run from the repo root with the venv active:
```python
import sys
sys.path.append("scraper")
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
| `project_dir` | `"PoliticalPoller"` | Scrapy project path (see Known Issues) |
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
`method` can be `persistent_browser` (default, recommended), `cached_session`, `playwright`, or `requests`. This is the legacy single-site entry point; prefer the functions above.

### Add a new site
- **Election/candidate site:** add an entry to `ELECTION_SITE_CONFIGS` in `scraper/election_site_configs.py` (`state`, `allowed_domains`, `start_urls`, `requires_browser`, `table_parser`, `table_parser_config`). Use `simple_table` with CSS selectors for flat tables or `colspan_hierarchy` for MN-style tables. Start from the states recommended in `2026_state_candidate_list_sources.md`.
- **News site:** add an entry to `SITE_CONFIGS` in `scraper/site_configs.py` (`allowed_domains`, `start_urls`, `index_link_selectors`, `article_url_contains`).

No spider code changes are needed for either.

### Scrapy settings
`scraper/settings.py` sets `ROBOTSTXT_OBEY = True`, a 1-second download delay, and AutoThrottle. The `USER_AGENT` still contains placeholder contact info (`example.com`); replace it before real crawling.

## Known Issues
- **Scrapy package name:** `scraper/scrapy.cfg` now exists, but it points at `PoliticalPoller.settings` and there is no `PoliticalPoller` package (the code is in `scraper/`), so `scrapy crawl` fails with `ModuleNotFoundError` when run directly. The `scripts/` run scripts work around this with a temporary symlink; running the Python functions directly or `run.sh` does not. `spider_runner.py` also defaults `project_dir` to `"PoliticalPoller"`, which doesn't exist.
- **Stale pipeline in `settings.py`:** `ITEM_PIPELINES` still lists `PoliticalPoller.pipelines.PoliticalpollerPipeline`, which doesn't exist in `pipelines.py`. Any Scrapy crawl (news, or non-browser election sites) stops with a `NameError` until that line is removed. The browser path used by `mn` doesn't use Scrapy.
- `file_manipulation/file_reader.py` uses `List` without importing it from `typing`, and both functions are stubs.
- `find_political_assoc()` is a stub.
- `utils.py` mentions a `capture_session.py` helper that is not in the repo.
- `_looks_solved()` in `utils.py` is hard-coded to `candidates.sos.mn.gov`, so the manual-CAPTCHA flow only works for Minnesota.
- `run.sh` does not create the venv, and reinstalls dependencies on every run.
- `__main__` in `site_reader.py` searches for the placeholder name `"test"`.
- Candidate identity is keyed on name + state only; same-named people who never appear in the same scrape can be merged (see `candidate_store.py`).

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
1. Reconcile the `scraper/` vs `PoliticalPoller` package name (rename the folder or change `scrapy.cfg`, `settings.py` and the spider imports) so Scrapy runs without the symlink workaround
2. Remove the nonexistent `PoliticalpollerPipeline` from `ITEM_PIPELINES` in `settings.py`
3. Add a `requirements.txt` (or `pyproject.toml`) with pinned dependencies
4. Make `run.sh` create the venv if missing and skip reinstalling when up to date
5. Replace the placeholder `USER_AGENT` contact info in `settings.py`
6. Add `candidate_data/` and `candidate_results_*.json` to `.gitignore`
7. Replace the bash heredocs in `scripts/` with a proper Python CLI (`argparse`) if the scripts grow

### Code gaps
1. Implement `read_sites_file()` and `read_politician_file()` in `file_manipulation/file_reader.py` (and add the `typing.List` import)
2. Implement `find_political_assoc()` (office, state, district, party, group affiliations, bills/orders)
3. Add or remove the missing `capture_session.py` referenced in `utils.py`
4. Generalize `_looks_solved()` / block detection beyond Minnesota
5. Add a stronger candidate identifier to `candidate_hash()` when a site exposes one (filer ID, district, birth year)
6. Add tests (the `test/` folder is git-ignored and nothing is checked in)

### More sources
1. Add election site configs for the 32 states with live HTML candidate lists (start with WA, OK, KY, FL, MO, IL, AK; see `2026_state_candidate_list_sources.md`)
2. Add document parsing (PDF/XLSX) for the 16 states that publish only documents; follow landing-page links since filenames change
3. Handle county-decentralized states (TX, OH)
4. Test each state site for bot protection and ASP.NET ViewState/postback handling
5. Add news site configs beyond `cnn` (local and state organizations first, per `sitePolicy.md`)
6. Add candidate summarizer sites from `sitePolicy.md` (knowyourvotes.com, whoisrunning.org, kyc.vote, theballotbrief.com, ballotmatch.org)
7. Add a body/snippet field to `NewsArticleItem` so news filtering can go beyond titles

---

# Developer Support
[Buy me a Ko-Fi](https://ko-fi.com/opnanalysis)
