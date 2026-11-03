"""The 2026 state configs: URL sets, and end-to-end parsing of fixtures that reproduce the
column layouts observed on the live Washington, Kentucky and South Dakota pages.

The fixtures use synthetic candidate names. They prove the config + header_table parser
handle those layouts; they do not prove the live sites still serve that markup -- run
probe_site.sh against each site for that.
"""
import logging
import os

import pytest
from scrapy.http import HtmlResponse

import election_site_configs as esc
import election_table_parsers as ep
from PoliticalPoller.spiders.election_spider import ElectionSpider

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
NEW_STATES = ["wa", "ok", "ky", "fl", "mo", "il", "ak", "md", "va", "de", "mt", "nd", "sd", "nm"]
HEADER_TABLE_KEYS = {"table_selector", "group_rows", "skip_office_patterns", "skip_names",
                     "header_aliases", "min_header_matches"}


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def crawl(site, fixture, url=None):
    spider = ElectionSpider(site=site)
    response = HtmlResponse(url=url or spider.start_urls[0], body=load(fixture).encode(), encoding="utf-8")
    return spider, list(spider.parse(response))


# ---------------------------------------------------------------- every requested state is present
@pytest.mark.parametrize("site", NEW_STATES)
class TestEveryNewState:
    def test_is_registered_and_open(self, site):
        cfg = esc.get_election_site_config(site)
        assert cfg["requires_browser"] is False and cfg["state"]

    def test_uses_the_header_table_parser_with_valid_keys(self, site):
        cfg = esc.ELECTION_SITE_CONFIGS[site]
        assert cfg["table_parser"] == "header_table"
        assert set(cfg["table_parser_config"]) <= HEADER_TABLE_KEYS

    def test_spider_can_be_built_from_it(self, site):
        spider = ElectionSpider(site=site)
        assert spider.start_urls and spider.allowed_domains

    def test_canonical_headers_parse_to_a_record(self, site):
        html = ("<table><tr><th>Office</th><th>Name</th><th>Party</th></tr>"
                "<tr><td>Governor</td><td>Test Person</td><td>IND</td></tr></table>")
        from parsel import Selector
        cfg = esc.ELECTION_SITE_CONFIGS[site]
        rows = ep.parse_table(Selector(text=html), cfg["table_parser"], cfg["table_parser_config"])
        assert [(r["candidate_name"], r["office"]) for r in rows] == [("Test Person", "Governor")]

    def test_only_layout_observed_sites_claim_to_be_verified(self, site):
        cfg = esc.ELECTION_SITE_CONFIGS[site]
        assert (cfg["verification"] == "layout_observed") == (site in {"wa", "ky", "sd"})


# ---------------------------------------------------------------- URL sets
class TestUrlSets:
    def test_washington_is_one_url_per_election_with_county_filters(self):
        urls = esc.ELECTION_SITE_CONFIGS["wa"]["start_urls"]
        assert urls[0] == f"https://voter.votewa.gov/CandidateList.aspx?e={esc.WA_GENERAL_ELECTION_ID}"
        assert urls[1:] == [f"https://voter.votewa.gov/CandidateList.aspx?e={esc.WA_GENERAL_ELECTION_ID}&c={c}"
                            for c in range(1, 41)]

    def test_kentucky_has_statewide_categories_and_the_county_page(self):
        urls = esc.ELECTION_SITE_CONFIGS["ky"]["start_urls"]
        assert "https://web.sos.ky.gov/CandidateFilings/default.aspx?id=3" in urls
        assert urls[-1] == "https://web.sos.ky.gov/CandidateFilings/countyfilings.aspx"
        assert len(urls) == len(esc.KY_CATEGORY_IDS) + 1

    def test_maryland_has_statewide_and_all_counties_lists(self):
        urls = esc.ELECTION_SITE_CONFIGS["md"]["start_urls"]
        assert any("statewide_candidatelist" in u for u in urls) and any("all_counties_candidatelist" in u for u in urls)

    def test_south_dakota_points_at_the_general_election(self):
        assert esc.ELECTION_SITE_CONFIGS["sd"]["start_urls"] == ["https://vip.sdsos.gov/candidatelist.aspx?eid=774"]

    def test_florida_uses_the_general_election_id(self):
        assert esc.ELECTION_SITE_CONFIGS["fl"]["start_urls"][0].endswith("elecid=20261103-GEN")

    def test_oklahoma_url_covers_all_counties(self):
        assert esc.ELECTION_SITE_CONFIGS["ok"]["start_urls"][0].endswith("/99/all")


# ---------------------------------------------------------------- Washington fixture, end to end
class TestWashington:
    def test_parses_the_grid_whose_header_is_a_separate_table(self):
        _, items = crawl("wa", "wa_candidate_list.html")
        assert [i["candidate_name"] for i in items] == [
            "Ada Example", "Ben Sample", "Cleo Test", "Dev Placeholder", "Eve Fixture", "Finn Mock"]

    def test_offices_are_unique_per_district(self):
        _, items = crawl("wa", "wa_candidate_list.html")
        offices = [i["office"] for i in items]
        assert offices == [
            "U.S. Senator",                                          # "Federal"/"Federal" district dropped
            "U.S. Representative (Congressional District 6)",
            "State Representative Pos. 1 (Legislative District 23)",
            "State Representative Pos. 1 (Legislative District 26)",  # same race, different district
            "County Assessor",                                       # blank district
            "Justice Position #04 (Supreme Court)",
        ]

    def test_withdrawn_candidates_are_marked_not_dropped(self):
        _, items = crawl("wa", "wa_candidate_list.html")
        cleo = next(i for i in items if i["candidate_name"] == "Cleo Test")
        assert cleo["status"] == "Withdrawn" and cleo["party"] == "REPUBLICAN"

    def test_other_fields(self):
        _, items = crawl("wa", "wa_candidate_list.html")
        ada = items[0]
        assert ada["office_level"] == "Federal" and ada["file_date"].startswith("5/6/2026")
        assert ada["state"] == "Washington" and ada["site"] == "wa" and ada["status"] == "Active"

    def test_the_pager_table_is_not_read_as_candidates(self):
        _, items = crawl("wa", "wa_candidate_list.html")
        assert not any(i["candidate_name"] in {"1", "2", "3"} for i in items)

    def test_a_multi_page_grid_is_flagged_as_incomplete(self, caplog):
        with caplog.at_level(logging.WARNING):
            crawl("wa", "wa_candidate_list.html")
        assert any("215 items over 3 pages" in r.getMessage() for r in caplog.records)

    def test_incomplete_pages_are_counted_in_the_crawl_stats(self):
        class Stats:
            counts = {}
            def inc_value(self, key):
                self.counts[key] = self.counts.get(key, 0) + 1
        class Crawler:
            stats = Stats()
        spider = ElectionSpider(site="wa")
        spider.crawler = Crawler()
        response = HtmlResponse(url=spider.start_urls[0], body=load("wa_candidate_list.html").encode(), encoding="utf-8")
        list(spider.parse(response))
        assert Crawler.stats.counts == {"elections/incomplete_pages": 1}

    def test_a_single_page_grid_is_not_flagged(self, caplog):
        spider = ElectionSpider(site="wa")
        body = load("wa_candidate_list.html").replace("215 items in 3 pages", "6 items in 1 pages")
        with caplog.at_level(logging.WARNING):
            list(spider.parse(HtmlResponse(url=spider.start_urls[0], body=body.encode(), encoding="utf-8")))
        assert not caplog.records

    def test_sites_without_a_pagination_hint_never_warn(self, caplog):
        spider = ElectionSpider(site="ky")
        with caplog.at_level(logging.WARNING):
            list(spider.parse(HtmlResponse(url=spider.start_urls[0],
                                           body=b"<p>999 items in 9 pages</p>", encoding="utf-8")))
        assert not caplog.records


# ---------------------------------------------------------------- Kentucky fixture, end to end
class TestKentucky:
    def test_parses_candidates_and_skips_ballot_amendments(self):
        _, items = crawl("ky", "ky_candidate_list.html")
        assert [i["candidate_name"] for i in items] == ["Gale Example", "Hal Sample", "Ida Test", "Jo Placeholder"]
        assert not any("Amendment" in (i["office"] or "") for i in items)

    def test_district_division_is_folded_into_the_office(self):
        _, items = crawl("ky", "ky_candidate_list.html")
        assert [i["office"] for i in items] == ["US Senator", "US Senator", "State Senator (6th)", "State Senator (12th)"]

    def test_party_and_date_columns(self):
        _, items = crawl("ky", "ky_candidate_list.html")
        assert items[0]["party"] == "Republican Party" and items[0]["file_date"] == "11/7/2025"
        assert items[0]["state"] == "Kentucky"

    def test_a_category_page_with_no_candidates_yields_nothing(self):
        spider = ElectionSpider(site="ky")
        body = b"<html><table><tr><th>Name / Running Mate</th><th>Office</th></tr></table></html>"
        assert list(spider.parse(HtmlResponse(url=spider.start_urls[0], body=body, encoding="utf-8"))) == []


# ---------------------------------------------------------------- South Dakota fixture, end to end
class TestSouthDakota:
    def test_contest_district_and_date_columns(self):
        _, items = crawl("sd", "sd_candidate_list.html")
        assert [(i["candidate_name"], i["office"], i["file_date"]) for i in items] == [
            ("Kai Example", "United States Senator", "3/10/2026"),
            ("Lou Sample", "State Senator (District 17)", "3/24/2026"),
            ("Max Placeholder", "State Senator (District 05)", "2/5/2026"),
            ("Nia Mock", "County Commissioner (Minnehaha County)", "2/19/2026"),
        ]

    def test_county_races_are_included(self):
        _, items = crawl("sd", "sd_candidate_list.html")
        assert any("County" in i["office"] for i in items)

    def test_the_same_parser_config_serves_the_other_bpro_states(self):
        for site in ("mt", "nd", "nm"):
            _, items = crawl(site, "sd_candidate_list.html")
            assert len(items) == 4, site
