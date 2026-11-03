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

# Config keys beyond the parser settings:
#   verification  "layout_observed": the live page's column headers were read
#                 and the config was checked against them.
#                 "url_only": the URL comes from 2026_state_candidate_list_sources.md
#                 and the table layout is ASSUMED. Run probe_site.py on it
#                 before trusting its output.
#   notes         what the list covers, and known gaps (paging, postbacks,
#                 election IDs still to pick).
#   ready_selector  (optional, browser-path sites) CSS selector only the real
#                 results page contains (default "table"); it is how the
#                 browser fetcher knows a manually-solved CAPTCHA has cleared.
#   pagination_hint_regex  (optional) regex with two groups (total items,
#                 total pages); ElectionSpider warns when a page says there
#                 are more pages than it fetched, so missing rows are never
#                 silent.
VERIFICATION_LEVELS = ("layout_observed", "url_only")

# Washington: county filter ids are the alphabetical position of the county
# in the site's own dropdown (17 = King, 18 = Kitsap, 27 = Pierce, 28 = San
# Juan were seen in live URLs); 33 is "State". e=898 is the 2026 primary
# (seen live); e=899 is the 2026 general per the research notes.
WA_GENERAL_ELECTION_ID = 899
WA_COUNTY_IDS = range(1, 41)

# Kentucky's candidate pages are one page per office category (?id=N); ids
# 3 (U.S. Senator), 11 (State Senator), 13 (Commonwealth's Attorney),
# 14 (Supreme Court) and 23 (a ballot amendment) were seen live.
KY_CATEGORY_IDS = range(1, 28)


def _bpro_config(state: str, host: str, urls: list, notes: str, verification: str) -> dict:
    """The Dakota/Montana/New Mexico candidate lists share one ASP.NET
    CandidateList.aspx design (likely one vendor), so one parser config
    covers them. South Dakota's was observed live with these columns:
    Contest | Name | Party | Petition Filing Date | District/County |
    Ballot Order | Mailing Address."""
    return {
        "state": state,
        "allowed_domains": [host],
        "start_urls": urls,
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {},
        "verification": verification,
        "notes": notes,
    }


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
        "ready_selector": "table",
        "verification": "layout_observed",
        "notes": "Bot-protected (CAPTCHA); run through the browser path. Includes county and local races.",
    },

    # ------------------------------------------------------------------
    # Open state sites (no bot protection known). All use header_table, which
    # finds columns by header text.
    # ------------------------------------------------------------------
    "wa": {
        "state": "Washington",
        "allowed_domains": ["voter.votewa.gov"],
        # One URL per election (e=), optionally filtered to a county (c=);
        # the county pages add county and local races (and PCOs).
        "start_urls": (
            [f"https://voter.votewa.gov/CandidateList.aspx?e={WA_GENERAL_ELECTION_ID}"]
            + [f"https://voter.votewa.gov/CandidateList.aspx?e={WA_GENERAL_ELECTION_ID}&c={c}"
               for c in WA_COUNTY_IDS]
        ),
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {},
        # The grid shows "215 items in 3 pages" and pages 100 rows at a time
        # through an ASP.NET postback this spider does not perform.
        "pagination_hint_regex": r"(\d+)\s+items?\s+in\s+(\d+)\s+pages?",
        "verification": "layout_observed",
        "notes": (
            "Columns (seen on the e=898 primary page): District Type, District, Race, Term Type, "
            "Term Length, Name, Mailing Address, Email, Phone, Filing Date, Party Preference, "
            "Status, Election Status, Ballot Order. Only the first page (100 rows) of each URL is "
            "fetched; the spider logs a warning when a page has more. A statewide or large-county "
            "list (e.g. King) will be incomplete until postback paging is added. e=899 is the "
            "2026 general per the research notes and was not itself fetched."
        ),
    },
    "ok": {
        "state": "Oklahoma",
        "allowed_domains": ["filings.okelections.gov"],
        # /ViewCandidates/<filing start><filing end>/<county code>/<office filter>;
        # county 99 = all counties, which includes county offices.
        "start_urls": ["https://filings.okelections.gov/ViewCandidates/2026040120260403/99/all"],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {},
        "verification": "url_only",
        "notes": (
            "URL pattern from the research notes and a Wikipedia citation; the page itself was not "
            "readable. If probe_site.py finds no <table>, the portal is JS-rendered and needs the "
            "browser path (requires_browser=True)."
        ),
    },
    "ky": {
        "state": "Kentucky",
        "allowed_domains": ["web.sos.ky.gov"],
        # Statewide filings (one page per office category) plus the separate
        # county-clerk filings page, all on one domain.
        "start_urls": (
            [f"https://web.sos.ky.gov/CandidateFilings/default.aspx?id={i}" for i in KY_CATEGORY_IDS]
            + ["https://web.sos.ky.gov/CandidateFilings/countyfilings.aspx"]
        ),
        "requires_browser": False,
        "table_parser": "header_table",
        # Ballot amendments appear as "candidates" named Yes/No.
        "table_parser_config": {"skip_office_patterns": [r"constitutional amendment", r"ballot question"]},
        "verification": "layout_observed",
        "notes": (
            "Columns: Name / Running Mate, POBox Address / Email, Office, District/Division, Party, "
            "Date Filed. ?id=N is an office category, not an election; ids that do not exist return "
            "an empty list. countyfilings.aspx is a postback form (pick a county) and may return "
            "nothing to a plain GET."
        ),
    },
    "fl": {
        "state": "Florida",
        "allowed_domains": ["dos.elections.myflorida.com"],
        "start_urls": ["https://dos.elections.myflorida.com/candidates/CanList.asp?elecid=20261103-GEN"],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {},
        "verification": "url_only",
        "notes": (
            "Federal, statewide and legislative races only; county races are with the 67 county "
            "Supervisors of Elections. The list shows qualification status, mapped to `status`."
        ),
    },
    "mo": {
        "state": "Missouri",
        "allowed_domains": ["s1.sos.mo.gov"],
        "start_urls": ["https://s1.sos.mo.gov/candidatesonweb/displaycandidatesplacement.aspx"],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {"group_rows": "office"},
        "verification": "url_only",
        "notes": "ASP.NET WebForms; the election/office choice may be a postback, so a plain GET can show a default election only.",
    },
    "il": {
        "state": "Illinois",
        "allowed_domains": ["www.elections.il.gov"],
        "start_urls": ["https://www.elections.il.gov/ElectionOperations/CandidateList.aspx"],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {"group_rows": "office"},
        "verification": "url_only",
        "notes": "ASP.NET WebForms; the election is chosen through a form (postback), so a plain GET may show nothing. Chicago and county lists are separate sites.",
    },
    "ak": {
        "state": "Alaska",
        "allowed_domains": ["www.elections.alaska.gov"],
        "start_urls": ["https://www.elections.alaska.gov/candidates/?election=26gen"],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {},
        "verification": "url_only",
        "notes": "?election=26prim is the primary (research notes); 26gen is an inference. State offices only: Alaska has no county-run state elections.",
    },
    "md": {
        "state": "Maryland",
        "allowed_domains": ["elections.maryland.gov"],
        "start_urls": [
            "https://elections.maryland.gov/elections/2026/general_candidates/2026_GG_statewide_candidatelist.html",
            "https://elections.maryland.gov/elections/2026/general_candidates/2026_GG_all_counties_candidatelist.html",
        ],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {"group_rows": "office"},
        "verification": "url_only",
        "notes": "Statewide and all-counties pages; both also come as Excel exports (not read here).",
    },
    "va": {
        "state": "Virginia",
        "allowed_domains": ["www.elections.virginia.gov"],
        "start_urls": [
            "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/",
            "https://www.elections.virginia.gov/casting-a-ballot/candidate-list/november-3-2026-gen-elect-local-offices/",
        ],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {"group_rows": "office"},
        "verification": "url_only",
        "notes": (
            "The first URL is an index; the statewide-office list is linked from it. The local-offices "
            "path is completed from an elided reference in the research notes. Follow links from the "
            "index with probe_site.py before relying on either."
        ),
    },
    "de": {
        "state": "Delaware",
        "allowed_domains": ["elections.delaware.gov"],
        "start_urls": ["https://elections.delaware.gov/candidates/candidatelist/genl_fcddt_2026.html"],
        "requires_browser": False,
        "table_parser": "header_table",
        "table_parser_config": {"group_rows": "office"},
        "verification": "url_only",
        "notes": "The statewide list includes county offices; an Excel version also exists.",
    },
    "mt": _bpro_config(
        "Montana", "candidatefiling.mt.gov",
        ["https://candidatefiling.mt.gov/candidatefiling/CandidateList.aspx?e=450002928"],
        "e=450002928 is the id in the research notes (likely the primary). Pick the general-election "
        "id from the site's election list. County races are with county election administrators.",
        "url_only"),
    "nd": _bpro_config(
        "North Dakota", "vip.sos.nd.gov",
        ["https://vip.sos.nd.gov/candidatelist.aspx?eid=346"],
        "eid=346 is the 2026 primary per the research notes; the general-election eid still needs "
        "to be found. County races are with county auditors.",
        "url_only"),
    "sd": _bpro_config(
        "South Dakota", "vip.sdsos.gov",
        ["https://vip.sdsos.gov/candidatelist.aspx?eid=774"],
        "eid=774 is the 2026 general (confirmed: page title \"2026 General Election Candidate List\"; "
        "columns Contest, Name, Party, Petition Filing Date, District/County, Ballot Order, Mailing "
        "Address). eid=773 is the primary. County races are with county auditors.",
        "layout_observed"),
    "nm": _bpro_config(
        "New Mexico", "candidateportal.servis.sos.state.nm.us",
        ["https://candidateportal.servis.sos.state.nm.us/CandidateList.aspx?eid=2911&cty=99"],
        "eid=2911 is the 2026 primary per the research notes; cty=99 looks like \"all counties\". "
        "The general-election eid still needs to be found.",
        "url_only"),

    # Example second site, shown as a template for adding an open (i.e.
    # not bot-protected) state or county site with a flat candidate table.
    "example_open_state": {
        "state": "Example State",
        "allowed_domains": ["elections.example.gov"],
        "start_urls": ["https://elections.example.gov/candidates/2026"],
        "requires_browser": False,
        "verification": "url_only",
        "notes": "Template for adding a state with a flat candidate table; not a real site.",
        "table_parser": "simple_table",
        "table_parser_config": {
            "row_selector": "table.candidate-list tr",
            "name_selector": "td.candidate-name::text",
            "office_selector": "td.office::text",
            "party_selector": "td.party::text",
            "website_selector": "td.website a::attr(href)",
            "file_date_selector": "td.filed-date::text",
            # If the site shows a candidate/filer ID, add it -- it is the
            # only reliable way to tell same-named people apart:
            # "filer_id_selector": "td.filer-id::text",
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
