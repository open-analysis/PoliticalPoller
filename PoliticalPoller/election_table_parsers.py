# -*- coding: utf-8 -*-

"""
Description: Site-agnostic parsers for government candidate/ballot tables.

Government election sites don't share one markup convention the way news
sitemaps loosely do, so unlike news_spider.py's link-selector approach,
this module holds a small set of *parsing strategies*, each parameterized
by a per-site config dict (see PoliticalPoller/election_site_configs.py).
Adding a site usually means picking an existing strategy and supplying
selectors/column indices, not writing new parsing code.

Both this project's Scrapy spider (election_spider.py, for plain HTML gov
sites) and the Playwright-based fetchers in site_reader.py (for
bot-protected sites like Minnesota's) call into the same functions here,
so the parsing logic -- and any future fixes to it -- lives in one place
regardless of how the HTML was fetched.

Every function takes a `parsel.Selector` (Scrapy responses already are
one; site_reader.py wraps fetched HTML text in one -- see
`parsel.Selector(text=html)`) so the same code works from either caller.
LLM: claude-sonnet-5
"""

import re
from datetime import datetime, timezone

from parsel import Selector


"""
Description: Returns the stripped, concatenated text of a td's full
    subtree (via XPath string()), or an empty string if the cell is None.
Param[in] td:  A parsel Selector for a single <td>
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def _cell_text(td) -> str:
    if td is None:
        return ""
    return (td.xpath("string(.)").get() or "").strip()


"""
Description: Returns the integer colspan attribute of a td, defaulting to
    1 if missing or unparseable.
Param[in] td:       A parsel Selector for a single <td>
Param[in] default:  Value to return if colspan is missing/unparseable
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def _colspan(td, default: int = 1) -> int:
    try:
        return int(td.attrib.get("colspan", default))
    except (TypeError, ValueError):
        return default


"""
Description: Extracts a candidate's website value from a td, preferring
    the href of an embedded <a> and falling back to the cell's visible
    text; ignores empty/placeholder hrefs (e.g. "javascript:...", bare
    "http://").
Param[in] td:  A parsel Selector for a single <td>
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def _extract_website(td) -> str:
    if td is None:
        return ""
    href = td.css("a::attr(href)").get()
    if href:
        href = href.strip()
        if href and not href.lower().startswith("javascript:") and href.lower() != "http://":
            return href
    return _cell_text(td)


def parse_colspan_hierarchy_table(selector: Selector, config: dict) -> list:
    """Generalized version of the row-shape-detection parser originally
    written for Minnesota's candidate list: rows alternate between
    "header" rows (identified by a wide colspan) that set the current
    office level/office, and narrower data rows that hold one candidate
    each. Column positions and colspans are configurable since sites that
    share this general table shape rarely share exact numbers.

    Recognized config keys (all optional, defaults match MN's markup):
        level_min_colspan     (default 6)  -- single <td> at/above this
                                               colspan sets office_level
        office_row_td_count   (default 2)  -- a 2-td row where the 2nd
                                               td's colspan is >=
        office_min_colspan    (default 5)  --   office_min_colspan sets
                                               the current office
        header_td_count       (default 6)  -- column-header row shape,
        header_name_index     (default 2)  --   skipped rather than
        header_name_text  (default "Candidate Name") -- parsed as data
        data_row_td_count     (default 5)  -- shape of a real candidate
        data_spacer_colspan   (default 2)  --   row: a leading spacer td
                                               at this colspan, then...
        name_index    (default 1)
        party_index   (default 2)
        website_index (default 3)
        file_date_index (default 4)
        filer_id_index (default None) -- td index holding a site-issued
                                         candidate/filer ID, if the site
                                         shows one (see candidate_store.py)
    """
    cfg = {
        "level_min_colspan": 6,
        "office_row_td_count": 2,
        "office_min_colspan": 5,
        "header_td_count": 6,
        "header_name_index": 2,
        "header_name_text": "Candidate Name",
        "data_row_td_count": 5,
        "data_spacer_colspan": 2,
        "name_index": 1,
        "party_index": 2,
        "website_index": 3,
        "file_date_index": 4,
        "filer_id_index": None,
        **config,
    }

    records = []
    current_level = None
    current_office = None

    for tr in selector.xpath("//tr"):
        tds = tr.xpath("./td")
        if not tds:
            continue

        # --- Level row: single td, wide colspan ---
        if len(tds) == 1 and _colspan(tds[0]) >= cfg["level_min_colspan"]:
            label = _cell_text(tds[0])
            if label:
                current_level = label
            continue

        # --- Office row: N tds, last has a wide colspan ---
        if len(tds) == cfg["office_row_td_count"] and _colspan(tds[-1]) >= cfg["office_min_colspan"]:
            label = _cell_text(tds[-1])
            if label:
                current_office = label
            continue

        # --- Column header row: skip, it's not data ---
        if len(tds) == cfg["header_td_count"]:
            if _cell_text(tds[cfg["header_name_index"]]) == cfg["header_name_text"]:
                continue
            continue  # unrecognized N-td row -- skip rather than misparse

        # --- Candidate data row ---
        if len(tds) == cfg["data_row_td_count"] and _colspan(tds[0]) == cfg["data_spacer_colspan"]:
            name = _cell_text(tds[cfg["name_index"]])
            if not name:
                continue
            records.append({
                "office_level": current_level,
                "office": current_office,
                "candidate_name": name,
                "party": _cell_text(tds[cfg["party_index"]]),
                "website": _extract_website(tds[cfg["website_index"]]),
                "file_date": _cell_text(tds[cfg["file_date_index"]]),
                "filer_id": (
                    _cell_text(tds[cfg["filer_id_index"]])
                    if cfg["filer_id_index"] is not None and cfg["filer_id_index"] < len(tds)
                    else ""
                ),
            })
            continue

        # Any other row shape (page chrome, nav, unrelated tables) is
        # intentionally ignored.

    return records


def parse_simple_table(selector: Selector, config: dict) -> list:
    """For gov sites that publish a plain, flat candidate table with one
    CSS class/column per field -- the common case for sites that don't
    nest office-level/office as separate header rows.

    Required config keys:
        row_selector       -- CSS selector for each candidate <tr>
        name_selector       -- CSS selector (relative to a row) for the
                                candidate name text/attr
    Optional config keys (skipped if absent/no match):
        office_level_selector, office_selector, party_selector,
        website_selector, file_date_selector, filer_id_selector (a
        site-issued candidate/filer ID -- when a site has one, set this:
        it is the only reliable way to tell same-named people apart, see
        candidate_store.py)
    """
    if "row_selector" not in config or "name_selector" not in config:
        raise ValueError(
            "parse_simple_table requires at least 'row_selector' and "
            "'name_selector' in table_parser_config."
        )

    records = []
    for row in selector.css(config["row_selector"]):
        name = (row.css(config["name_selector"]).get() or "").strip()
        if not name:
            continue

        def field(key):
            sel = config.get(key)
            if not sel:
                return ""
            val = row.css(sel).get()
            return val.strip() if val else ""

        records.append({
            "office_level": field("office_level_selector"),
            "office": field("office_selector"),
            "candidate_name": name,
            "party": field("party_selector"),
            "website": field("website_selector"),
            "file_date": field("file_date_selector"),
            "filer_id": field("filer_id_selector"),
        })

    return records



# Header labels the header_table parser recognises, per field. A column is
# matched when its header text equals one of these (best), or else contains
# one as a whole word. Sites can add/override aliases via
# table_parser_config["header_aliases"].
DEFAULT_HEADER_ALIASES = {
    "candidate_name": ["candidate name", "ballot name", "name", "candidate"],
    "office": ["office title", "office", "contest", "race", "office sought"],
    "office_level": ["district type", "office level", "level", "category"],
    "district": ["district/division", "district/county", "district", "division"],
    "party": ["party preference", "party affiliation", "party"],
    "website": ["web site", "website", "url"],
    "file_date": ["petition filing date", "filing date", "date filed", "file date", "filed"],
    "filer_id": ["filer id", "candidate id", "id number"],
    "status": ["election status", "qualification status", "status"],
}


def _row_cells(row):
    """Direct th/td children of a <tr> (so a nested pager table's cells
    are never mistaken for this row's)."""
    return row.xpath("./th | ./td")


def _cell_plain_text(cell) -> str:
    return " ".join(" ".join(cell.xpath(".//text()").getall()).split())


def _match_header(text: str, aliases: list) -> int:
    """0 = no match, 2 = exact alias match, 1 = alias appears as whole word(s)."""
    text = " ".join(text.lower().split())
    if text in aliases:
        return 2
    for alias in aliases:
        if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text):
            return 1
    return 0


def _map_columns(texts: list, aliases: dict) -> dict:
    """{field: column index} for one header row. Each column is claimed by
    at most one field, exact matches win over whole-word matches, and
    earlier fields in `aliases` win ties."""
    mapping, used = {}, set()
    for quality in (2, 1):
        for field, alias_list in aliases.items():
            if field in mapping:
                continue
            for idx, text in enumerate(texts):
                if idx not in used and _match_header(text, alias_list) == quality:
                    mapping[field] = idx
                    used.add(idx)
                    break
    return mapping


def parse_header_table(selector: Selector, config: dict) -> list:
    """Parses candidate tables whose columns are identified by their HEADER
    TEXT instead of by position, so it keeps working when a site reorders or
    adds columns, and needs no per-site CSS selectors. Written for the many
    state lists that are one plain table (or a few) with a header row, such
    as Washington, Kentucky, and the BPro-built Dakota/Montana/New Mexico
    lists.

    How it reads a page:
      - every <table> is scanned in document order (nested tables are not
        descended into). A row is a header row when at least two of its
        cells match known header labels; the column mapping from the most
        recent header row is reused for later tables, because some grids
        (Telerik RadGrid) put the header and the body in separate tables.
      - a row under a known header is a candidate row when it has a value in
        the candidate-name column; rows with a single non-empty cell are
        treated as GROUP rows (see group_rows) and are never candidates.
      - "office" is built from the office column plus the district column
        (e.g. "State Senator (6th)"), because a bare "State Senator" is
        ambiguous across districts. A district that merely repeats the
        office level (Washington's "Federal"/"Federal") is dropped.

    Config (all optional):
        header_aliases   {field: [labels]} merged over DEFAULT_HEADER_ALIASES
        table_selector   CSS selector for the tables to read (default "table")
        group_rows       None (default), "office", or "office_level": what a
                         single-cell row means ("Governor" above its candidates)
        skip_office_patterns  regexes; candidates whose built office matches
                         are dropped (e.g. ballot-measure rows)
        skip_names       candidate names to drop (case-insensitive)
        min_header_matches  header labels a row needs to count as the header (2)
    Param[out] records: dicts with office_level, office, candidate_name,
        party, website, file_date, filer_id, status
    LLM: claude-sonnet-5.5
    """
    aliases = {**DEFAULT_HEADER_ALIASES, **(config.get("header_aliases") or {})}
    group_field = config.get("group_rows")
    skip_patterns = [re.compile(p, re.I) for p in config.get("skip_office_patterns") or []]
    skip_names = {n.lower() for n in config.get("skip_names") or []}
    min_matches = config.get("min_header_matches", 2)

    records, columns, group_value = [], None, None
    for table in selector.css(config.get("table_selector", "table")):
        # A table nested inside another (a pager, a layout wrapper) must find
        # its own header; it never inherits the outer table's columns.
        saved_columns = None
        nested = bool(table.xpath("ancestor::table"))
        if nested:
            saved_columns, columns = columns, None
        for row in table.xpath("./tr | ./thead/tr | ./tbody/tr | ./tfoot/tr"):
            cells = _row_cells(row)
            if not cells:
                continue
            texts = [_cell_plain_text(c) for c in cells]

            mapping = _map_columns(texts, aliases)
            if len(mapping) >= min_matches and "candidate_name" in mapping:
                columns, group_value = mapping, None
                continue
            if columns is None:
                continue

            non_empty = [t for t in texts if t]
            if len(cells) <= 2 and len(non_empty) == 1:
                # A one- or two-cell row with a single value is a section
                # label ("Governor"), never a candidate.
                if group_field:
                    group_value = non_empty[0]
                continue
            if max(columns.values()) >= len(cells):
                continue  # too short to be a data row (spacer, pager, ...)

            def value(field):
                idx = columns.get(field)
                return texts[idx] if idx is not None and idx < len(texts) else ""

            name = value("candidate_name")
            if not name or name.lower() in skip_names:
                continue

            level = value("office_level") or (group_value if group_field == "office_level" else "")
            office = value("office") or (group_value if group_field == "office" else "")
            district = value("district")
            if district and district.lower() not in (level.lower(), office.lower()):
                office = f"{office} ({district})" if office else district
            if any(p.search(office) for p in skip_patterns):
                continue

            website = ""
            idx = columns.get("website")
            if idx is not None and idx < len(cells):
                href = cells[idx].xpath(".//a/@href").get()
                if href and not href.strip().lower().startswith(("javascript:", "mailto:")):
                    website = href.strip()
                else:
                    website = texts[idx]

            records.append({
                "office_level": level,
                "office": office,
                "candidate_name": name,
                "party": value("party"),
                "website": website,
                "file_date": value("file_date"),
                "filer_id": value("filer_id"),
                "status": value("status"),
            })
        if nested and columns is None:
            columns = saved_columns
    return records


PARSERS = {
    "colspan_hierarchy": parse_colspan_hierarchy_table,
    "simple_table": parse_simple_table,
    "header_table": parse_header_table,
}


"""
Description: Dispatches to the named table-parsing strategy
    (PARSERS["colspan_hierarchy"] or PARSERS["simple_table"]) and returns
    its parsed candidate rows.
Param[in] selector:       A parsel Selector over the full page
Param[in] parser_name:    Key into PARSERS, e.g. "colspan_hierarchy"
Param[in] parser_config:  That parser's config dict (see
    parse_colspan_hierarchy_table()/parse_simple_table() for the keys
    each accepts)
Param[out] records:       List of dicts (office_level, office,
    candidate_name, party, website, file_date, filer_id)
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def parse_table(selector: Selector, parser_name: str, parser_config: dict) -> list:
    try:
        parser = PARSERS[parser_name]
    except KeyError:
        raise ValueError(
            f"Unknown table_parser {parser_name!r}. Known parsers: "
            f"{sorted(PARSERS)}"
        )
    return parser(selector, parser_config or {})


def build_candidate_records(records: list, site: str, state: str, source_url: str) -> list:
    """Stamps parse_table()'s raw rows (office_level/office/candidate_name/
    party/website/file_date) with the same crawl metadata ElectionSpider
    attaches to its items (site/state/source_url/scraped_at), so results
    are shaped identically regardless of whether they were parsed from a
    Scrapy response or from browser-fetched HTML. This is what keeps
    run_election_spider()'s two code paths (Scrapy for open sites,
    Playwright for bot-protected ones) returning the same thing.
    LLM: claude-sonnet-5
    """
    scraped_at = datetime.now(timezone.utc).isoformat()
    return [
        {
            "site": site,
            "state": state,
            "office_level": r.get("office_level"),
            "office": r.get("office"),
            "candidate_name": r.get("candidate_name"),
            "party": r.get("party"),
            "website": r.get("website"),
            "file_date": r.get("file_date"),
            "filer_id": r.get("filer_id") or None,
            "status": r.get("status") or None,
            "source_url": source_url,
            "scraped_at": scraped_at,
        }
        for r in records
    ]
