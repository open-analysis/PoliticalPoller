"""header_table parser: columns found by header text, office building, groups, skips."""
from parsel import Selector

import election_table_parsers as ep


def parse(html, cfg=None):
    return ep.parse_table(Selector(text=html), "header_table", cfg or {})


def page(header, *rows):
    th = "".join(f"<th>{h}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{body}</table>"


class TestColumnMapping:
    def test_maps_columns_by_header_text_in_any_order(self):
        rows = parse(page(["Party", "Date Filed", "Name", "Office"], ["DFL", "5/1/2026", "Jo Park", "Mayor"]))
        assert rows[0]["candidate_name"] == "Jo Park" and rows[0]["office"] == "Mayor"
        assert rows[0]["party"] == "DFL" and rows[0]["file_date"] == "5/1/2026"

    def test_whole_word_match_for_compound_headers(self):
        cols = ep._map_columns(["Name / Running Mate", "Office", "Party Preference", "Petition Filing Date"],
                               ep.DEFAULT_HEADER_ALIASES)
        assert cols == {"candidate_name": 0, "office": 1, "party": 2, "file_date": 3}

    def test_exact_match_beats_partial_match(self):
        # "District" must go to district, not be swallowed by "District Type"
        cols = ep._map_columns(["District Type", "District", "Race", "Name"], ep.DEFAULT_HEADER_ALIASES)
        assert cols["office_level"] == 0 and cols["district"] == 1

    def test_unrelated_words_are_not_matched(self):
        cols = ep._map_columns(["Mailing Address", "Email", "Phone", "Ballot Order"], ep.DEFAULT_HEADER_ALIASES)
        assert cols == {}

    def test_custom_aliases_are_merged_in(self):
        html = page(["Aspirant", "Seat"], ["Jo Park", "Mayor"])
        assert parse(html) == []
        rows = parse(html, {"header_aliases": {"candidate_name": ["aspirant"], "office": ["seat"]}})
        assert rows[0]["candidate_name"] == "Jo Park" and rows[0]["office"] == "Mayor"

    def test_page_without_candidate_headers_yields_nothing(self):
        assert parse(page(["Product", "Price"], ["Pen", "$1"])) == []
        assert parse("<p>no tables</p>") == []


class TestOfficeBuilding:
    def test_district_is_appended_to_the_office(self):
        rows = parse(page(["Name", "Office", "District"], ["A B", "State Senator", "6th"]))
        assert rows[0]["office"] == "State Senator (6th)"

    def test_district_repeating_the_level_or_office_is_dropped(self):
        rows = parse(page(["District Type", "District", "Race", "Name"],
                          ["Federal", "Federal", "U.S. Senator", "A B"],
                          ["State", "Governor", "Governor", "C D"]))
        assert [r["office"] for r in rows] == ["U.S. Senator", "Governor"]

    def test_district_alone_is_used_when_there_is_no_office_column(self):
        assert parse(page(["Name", "District"], ["A B", "District 5"]))[0]["office"] == "District 5"

    def test_same_race_in_different_districts_stays_distinguishable(self):
        rows = parse(page(["Name", "Race", "District"], ["A", "State Rep", "LD 23"], ["B", "State Rep", "LD 26"]))
        assert len({r["office"] for r in rows}) == 2


class TestRows:
    def test_rows_without_a_name_are_skipped(self):
        assert len(parse(page(["Name", "Office"], ["", "Mayor"], ["A B", "Clerk"]))) == 1

    def test_short_rows_are_skipped(self):
        assert parse(page(["Name", "Office", "Party"], ["A B"])) == []

    def test_group_rows_supply_the_office(self):
        html = ("<table><tr><th>Candidate</th><th>Party</th></tr>"
                "<tr><td colspan='2'>Governor</td></tr>"
                "<tr><td>A B</td><td>DFL</td></tr><tr><td>C D</td><td>GOP</td></tr>"
                "<tr><td colspan='2'>Auditor</td></tr><tr><td>E F</td><td>IND</td></tr></table>")
        rows = parse(html, {"group_rows": "office"})
        assert [(r["candidate_name"], r["office"]) for r in rows] == \
            [("A B", "Governor"), ("C D", "Governor"), ("E F", "Auditor")]

    def test_group_rows_are_ignored_unless_configured(self):
        html = ("<table><tr><th>Candidate</th><th>Party</th></tr>"
                "<tr><td colspan='2'>Governor</td></tr><tr><td>A B</td><td>DFL</td></tr></table>")
        assert parse(html)[0]["office"] == ""

    def test_group_rows_can_supply_the_level(self):
        html = ("<table><tr><th>Candidate</th><th>Office</th></tr>"
                "<tr><td colspan='2'>Federal</td></tr><tr><td>A B</td><td>Senator</td></tr></table>")
        assert parse(html, {"group_rows": "office_level"})[0]["office_level"] == "Federal"

    def test_skip_office_patterns_and_names(self):
        html = page(["Name", "Office"], ["Yes", "Constitutional Amendment 1"], ["A B", "Mayor"], ["Write-in", "Mayor"])
        rows = parse(html, {"skip_office_patterns": ["constitutional amendment"], "skip_names": ["WRITE-IN"]})
        assert [r["candidate_name"] for r in rows] == ["A B"]

    def test_header_carries_across_tables(self):
        html = ("<table><tr><th>Name</th><th>Office</th></tr></table>"
                "<table><tr><td>A B</td><td>Mayor</td></tr></table>")
        assert parse(html)[0]["office"] == "Mayor"

    def test_columns_survive_a_nested_pager_for_the_next_table(self):
        # header table, then a body table that contains a nested pager table, then a second body
        # table: the second one must still use the columns from the header.
        html = ("<table><tr><th>Name</th><th>Office</th></tr></table>"
                "<table><tr><td>A B</td><td>Mayor</td></tr>"
                "<tr><td colspan='2'><table><tr><td>1</td><td>2</td></tr></table></td></tr></table>"
                "<table><tr><td>C D</td><td>Clerk</td></tr></table>")
        assert [(r["candidate_name"], r["office"]) for r in parse(html)] == [("A B", "Mayor"), ("C D", "Clerk")]

    def test_rows_shorter_than_the_header_are_skipped(self):
        html = page(["Name", "Office", "Party", "Date Filed"], ["A B", "Mayor", "X"], ["C D", "Clerk", "Y", "5/1/2026"])
        assert [r["candidate_name"] for r in parse(html)] == ["C D"]

    def test_a_new_header_replaces_the_old_mapping(self):
        html = ("<table><tr><th>Name</th><th>Office</th></tr><tr><td>A B</td><td>Mayor</td></tr></table>"
                "<table><tr><th>Office</th><th>Name</th></tr><tr><td>Clerk</td><td>C D</td></tr></table>")
        assert [(r["candidate_name"], r["office"]) for r in parse(html)] == [("A B", "Mayor"), ("C D", "Clerk")]

    def test_nested_tables_are_not_read_as_rows(self):
        html = ("<table><tr><th>Name</th><th>Office</th></tr>"
                "<tr><td>A B</td><td>Mayor<table><tr><td>Z Z</td><td>Ghost</td></tr></table></td></tr></table>")
        assert [r["candidate_name"] for r in parse(html)] == ["A B"]

    def test_table_selector_limits_where_to_look(self):
        html = ("<table class='x'><tr><th>Name</th><th>Office</th></tr><tr><td>A B</td><td>Mayor</td></tr></table>"
                "<table class='y'><tr><th>Name</th><th>Office</th></tr><tr><td>C D</td><td>Clerk</td></tr></table>")
        assert [r["candidate_name"] for r in parse(html, {"table_selector": "table.y"})] == ["C D"]


class TestWebsiteAndExtras:
    def test_website_prefers_the_link_target(self):
        html = page(["Name", "Office", "Website"], ["A B", "Mayor", "<a href='https://ab.test'>site</a>"])
        assert parse(html)[0]["website"] == "https://ab.test"

    def test_javascript_and_mailto_links_fall_back_to_text(self):
        html = page(["Name", "Office", "Website"], ["A B", "Mayor", "<a href='javascript:x()'>visit</a>"])
        assert parse(html)[0]["website"] == "visit"

    def test_no_website_column_gives_blank(self):
        assert parse(page(["Name", "Office"], ["A B", "Mayor"]))[0]["website"] == ""

    def test_status_and_filer_id_are_captured(self):
        rows = parse(page(["Name", "Office", "Status", "Filer ID"], ["A B", "Mayor", "Withdrawn", "F-1"]))
        assert rows[0]["status"] == "Withdrawn" and rows[0]["filer_id"] == "F-1"

    def test_build_candidate_records_carries_status(self):
        (rec,) = ep.build_candidate_records([{"candidate_name": "A", "status": "Withdrawn"}], "s", "S", "u")
        assert rec["status"] == "Withdrawn"
        (rec,) = ep.build_candidate_records([{"candidate_name": "A", "status": ""}], "s", "S", "u")
        assert rec["status"] is None
