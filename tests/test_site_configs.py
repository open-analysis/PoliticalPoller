"""site_configs.py / election_site_configs.py: lookups and config sanity."""
import pytest

import election_site_configs as esc
import election_table_parsers as ep
import site_configs as sc


class TestLookups:
    def test_news_site_lookup(self):
        assert sc.get_site_config("cnn") is sc.SITE_CONFIGS["cnn"]

    def test_unknown_news_site_lists_known_sites(self):
        with pytest.raises(ValueError, match="cnn"):
            sc.get_site_config("nope")

    def test_election_site_lookup(self):
        assert esc.get_election_site_config("mn")["state"] == "Minnesota"

    def test_unknown_election_site_lists_known_sites(self):
        with pytest.raises(ValueError, match="mn"):
            esc.get_election_site_config("nope")


@pytest.mark.parametrize("site", sorted(sc.SITE_CONFIGS))
def test_news_configs_have_everything_the_spider_reads(site):
    cfg = sc.SITE_CONFIGS[site]
    assert cfg["allowed_domains"] and cfg["start_urls"]
    assert cfg["index_link_selectors"] and isinstance(cfg["article_url_contains"], str)


@pytest.mark.parametrize("site", sorted(esc.ELECTION_SITE_CONFIGS))
class TestElectionConfigs:
    def test_required_keys(self, site):
        cfg = esc.ELECTION_SITE_CONFIGS[site]
        for key in ("state", "allowed_domains", "start_urls", "requires_browser", "table_parser"):
            assert key in cfg, key

    def test_parser_name_is_registered(self, site):
        assert esc.ELECTION_SITE_CONFIGS[site]["table_parser"] in ep.PARSERS

    def test_start_urls_are_inside_allowed_domains(self, site):
        cfg = esc.ELECTION_SITE_CONFIGS[site]
        for url in cfg["start_urls"]:
            assert any(domain in url for domain in cfg["allowed_domains"])

    def test_declares_how_trustworthy_it_is(self, site):
        cfg = esc.ELECTION_SITE_CONFIGS[site]
        assert cfg["verification"] in esc.VERIFICATION_LEVELS
        assert cfg["notes"].strip()

    def test_no_duplicate_start_urls(self, site):
        urls = esc.ELECTION_SITE_CONFIGS[site]["start_urls"]
        assert len(urls) == len(set(urls))

    def test_simple_table_configs_have_required_selectors(self, site):
        cfg = esc.ELECTION_SITE_CONFIGS[site]
        if cfg["table_parser"] == "simple_table":
            assert {"row_selector", "name_selector"} <= set(cfg["table_parser_config"])
