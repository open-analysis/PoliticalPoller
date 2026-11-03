"""election_table_parsers.py: both table parsers, the dispatcher, record stamping."""
import pytest
from parsel import Selector

import election_table_parsers as ep


# ---------------------------------------------------------------- colspan_hierarchy
class TestColspanHierarchy:
    def parse(self, html, cfg=None):
        return ep.parse_table(Selector(text=html), "colspan_hierarchy", cfg or {})

    def test_levels_offices_and_candidates(self, mn_html):
        rows = self.parse(mn_html)
        assert [(r["office_level"], r["office"], r["candidate_name"]) for r in rows] == [
            ("Federal Offices", "U.S. Senator", "Jane Doe"),
            ("Federal Offices", "U.S. Senator", "John Roe"),
            ("State Offices", "Governor", "Jane Doe"),
        ]

    def test_fields(self, mn_html):
        first = self.parse(mn_html)[0]
        assert first["party"] == "DFL"
        assert first["website"] == "https://janedoe.com"
        assert first["file_date"] == "05/26/2026"
        assert first["filer_id"] == ""

    def test_placeholder_href_falls_back_to_link_text(self, mn_html):
        assert self.parse(mn_html)[1]["website"] == "none"

    def test_plain_text_website(self, mn_html):
        assert self.parse(mn_html)[2]["website"] == "janedoe.com"

    def test_nameless_rows_and_header_rows_are_skipped(self, mn_html):
        names = [r["candidate_name"] for r in self.parse(mn_html)]
        assert "" not in names and "Candidate Name" not in names

    def test_unrelated_markup_is_ignored(self):
        assert self.parse("<table><tr><td>x</td><td>y</td><td>z</td></tr></table><p>hi</p>") == []

    def test_empty_page(self):
        assert self.parse("<html></html>") == []

    # spacer + name/party/website/date + ID = 6 tds
    FILER_ROW_HTML = """<table>
      <tr><td colspan="6">Local</td></tr>
      <tr><td></td><td colspan="5">Mayor</td></tr>
      <tr><td colspan="2"></td><td>Jo Park</td><td>IND</td><td></td><td>01/02/2026</td><td>F-77</td></tr>
    </table>"""

    def test_filer_id_index(self):
        rows = self.parse(self.FILER_ROW_HTML, {"data_row_td_count": 6, "header_td_count": 99,
                                                "filer_id_index": 5})
        assert rows == [{"office_level": "Local", "office": "Mayor", "candidate_name": "Jo Park",
                         "party": "IND", "website": "", "file_date": "01/02/2026", "filer_id": "F-77"}]

    def test_six_td_data_rows_need_header_td_count_overridden(self):
        # Known gotcha: a 6-td data row has the same shape as the default
        # 6-td column-header row, so it is skipped unless header_td_count is
        # changed too. Adding a filer-ID column to a site config therefore
        # needs BOTH settings.
        assert self.parse(self.FILER_ROW_HTML, {"data_row_td_count": 6, "filer_id_index": 5}) == []

    def test_filer_id_index_out_of_range_is_blank(self, mn_html):
        assert self.parse(mn_html, {"filer_id_index": 99})[0]["filer_id"] == ""

    def test_config_overrides_default_column_positions(self):
        html = """<table>
          <tr><td colspan="9">Level</td></tr>
          <tr><td></td><td colspan="8">Office</td></tr>
          <tr><td colspan="2"></td><td>GRN</td><td>Zed</td><td></td><td>01/02/2026</td></tr>
        </table>"""
        (row,) = self.parse(html, {"level_min_colspan": 9, "office_min_colspan": 8,
                                   "name_index": 2, "party_index": 1})
        assert (row["office_level"], row["office"], row["candidate_name"], row["party"]) == \
            ("Level", "Office", "Zed", "GRN")


# ---------------------------------------------------------------- simple_table
SIMPLE_HTML = """
<table class="c">
 <tr class="row"><td class="n">Jo Park</td><td class="o">Mayor</td><td class="l">Local</td><td class="p">IND</td>
   <td class="w"><a href="https://jopark.org">x</a></td><td class="f"> 05/01/2026 </td><td class="id">F-77</td></tr>
 <tr class="row"><td class="n"></td><td class="o">Clerk</td></tr>
 <tr class="row"><td class="n">Al Fox</td><td class="o">Clerk</td></tr>
</table>"""
SIMPLE_CFG = {
    "row_selector": "tr.row", "name_selector": "td.n::text", "office_selector": "td.o::text",
    "office_level_selector": "td.l::text", "party_selector": "td.p::text",
    "website_selector": "td.w a::attr(href)", "file_date_selector": "td.f::text",
    "filer_id_selector": "td.id::text",
}


class TestSimpleTable:
    def parse(self, cfg=None, html=SIMPLE_HTML):
        return ep.parse_table(Selector(text=html), "simple_table", cfg or SIMPLE_CFG)

    def test_parses_all_configured_fields(self):
        first = self.parse()[0]
        assert first == {
            "office_level": "Local", "office": "Mayor", "candidate_name": "Jo Park", "party": "IND",
            "website": "https://jopark.org", "file_date": "05/01/2026", "filer_id": "F-77",
        }

    def test_rows_without_a_name_are_skipped(self):
        assert [r["candidate_name"] for r in self.parse()] == ["Jo Park", "Al Fox"]

    def test_optional_selectors_default_to_blank(self):
        cfg = {"row_selector": "tr.row", "name_selector": "td.n::text"}
        row = self.parse(cfg)[0]
        assert row["party"] == "" and row["filer_id"] == "" and row["office"] == ""

    def test_missing_cell_in_a_row_is_blank_not_an_error(self):
        al = self.parse()[1]
        assert al["party"] == "" and al["website"] == ""

    @pytest.mark.parametrize("missing", ["row_selector", "name_selector"])
    def test_required_config_keys(self, missing):
        cfg = {k: v for k, v in SIMPLE_CFG.items() if k != missing}
        with pytest.raises(ValueError, match="row_selector"):
            self.parse(cfg)


# ---------------------------------------------------------------- dispatcher / stamping
class TestDispatchAndStamping:
    def test_unknown_parser_lists_known_ones(self):
        with pytest.raises(ValueError, match="colspan_hierarchy"):
            ep.parse_table(Selector(text=""), "nope", {})

    def test_registered_parsers(self):
        assert set(ep.PARSERS) == {"colspan_hierarchy", "simple_table", "header_table"}

    def test_build_candidate_records_stamps_metadata(self):
        raw = [{"office_level": "L", "office": "O", "candidate_name": "N", "party": "P",
                "website": "W", "file_date": "D", "filer_id": "42"}]
        (rec,) = ep.build_candidate_records(raw, "mn", "Minnesota", "https://x.test/")
        assert rec["site"] == "mn" and rec["state"] == "Minnesota"
        assert rec["source_url"] == "https://x.test/" and rec["scraped_at"]
        assert rec["filer_id"] == "42" and rec["candidate_name"] == "N"

    def test_blank_filer_id_becomes_none(self):
        (rec,) = ep.build_candidate_records([{"candidate_name": "N", "filer_id": ""}], "s", "S", "u")
        assert rec["filer_id"] is None

    def test_missing_keys_become_none(self):
        (rec,) = ep.build_candidate_records([{"candidate_name": "N"}], "s", "S", "u")
        assert rec["party"] is None and rec["office"] is None

    def test_empty_input(self):
        assert ep.build_candidate_records([], "s", "S", "u") == []
