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

from parsel import Selector


def _cell_text(td) -> str:
    if td is None:
        return ""
    return (td.xpath("string(.)").get() or "").strip()


def _colspan(td, default: int = 1) -> int:
    try:
        return int(td.attrib.get("colspan", default))
    except (TypeError, ValueError):
        return default


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
        website_selector, file_date_selector
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
        })

    return records


PARSERS = {
    "colspan_hierarchy": parse_colspan_hierarchy_table,
    "simple_table": parse_simple_table,
}


def parse_table(selector: Selector, parser_name: str, parser_config: dict) -> list:
    try:
        parser = PARSERS[parser_name]
    except KeyError:
        raise ValueError(
            f"Unknown table_parser {parser_name!r}. Known parsers: "
            f"{sorted(PARSERS)}"
        )
    return parser(selector, parser_config or {})
