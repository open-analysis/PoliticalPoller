"""pipelines.py: validation/de-dupe pipelines."""
import pytest
from scrapy.exceptions import DropItem

from PoliticalPoller.items import ElectionCandidateItem, NewsArticleItem
from PoliticalPoller.pipelines import ElectionCandidateValidationPipeline, NewsArticleValidationPipeline


class TestNewsPipeline:
    def test_valid_item_passes_unchanged(self):
        item = NewsArticleItem(title="T", url="https://x/a")
        assert NewsArticleValidationPipeline().process_item(item, None) is item

    @pytest.mark.parametrize("fields", [{"url": "https://x/a"}, {"title": "T"}, {}])
    def test_missing_title_or_url_is_dropped(self, fields):
        with pytest.raises(DropItem, match="Missing"):
            NewsArticleValidationPipeline().process_item(NewsArticleItem(**fields), None)

    def test_duplicate_url_is_dropped(self):
        pipe = NewsArticleValidationPipeline()
        pipe.process_item(NewsArticleItem(title="T", url="https://x/a"), None)
        with pytest.raises(DropItem, match="Duplicate"):
            pipe.process_item(NewsArticleItem(title="Other", url="https://x/a"), None)

    def test_separate_pipeline_instances_do_not_share_state(self):
        item = NewsArticleItem(title="T", url="https://x/a")
        NewsArticleValidationPipeline().process_item(item, None)
        NewsArticleValidationPipeline().process_item(item, None)


class TestElectionPipeline:
    def item(self, name="Jane Doe", office="Governor", site="mn"):
        return ElectionCandidateItem(site=site, office=office, candidate_name=name)

    def test_valid_item_passes(self):
        item = self.item()
        assert ElectionCandidateValidationPipeline().process_item(item, None) is item

    def test_missing_name_is_dropped(self):
        with pytest.raises(DropItem, match="Missing"):
            ElectionCandidateValidationPipeline().process_item(self.item(name=""), None)

    def test_exact_duplicate_row_is_dropped(self):
        pipe = ElectionCandidateValidationPipeline()
        pipe.process_item(self.item(), None)
        with pytest.raises(DropItem, match="Duplicate"):
            pipe.process_item(self.item(), None)

    def test_same_person_under_a_different_office_is_kept(self):
        pipe = ElectionCandidateValidationPipeline()
        pipe.process_item(self.item(office="Governor"), None)
        pipe.process_item(self.item(office="Senator"), None)

    def test_same_name_on_a_different_site_is_kept(self):
        pipe = ElectionCandidateValidationPipeline()
        pipe.process_item(self.item(site="mn"), None)
        pipe.process_item(self.item(site="ia"), None)
