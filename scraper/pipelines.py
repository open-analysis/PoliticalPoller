"""
Description: This file contains the pipelines necessary the spiders to crawl a given website.

Define your item pipelines here
Don't forget to add your pipeline to the ITEM_PIPELINES setting
See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
"""


from scrapy.exceptions import DropItem

"""
Description: Drops items missing required fields and de-duplicates by URL within
a single crawl run. Keeping this in a pipeline (rather than checking
ad hoc inside parse()) is the standard Scrapy way to validate/clean
items, and it runs for every item regardless of which callback yielded
it.

Owner: @opnanalysis
LLM: claude-sonnet-5
"""
class NewsArticleValidationPipeline(object):
    def __init__(self):
        self.seen_urls = set()

    def process_item(self, item, spider):
        if not item.get("title") or not item.get("url"):
            raise DropItem(f"Missing title or url: {item!r}")

        if item["url"] in self.seen_urls:
            raise DropItem(f"Duplicate article: {item['url']}")
        self.seen_urls.add(item["url"])

        return item

"""
Description: Drops candidate rows with no name (a parsing miss, not a real
candidate) and de-dupes on (site, office, candidate_name) within a
run, since a candidate can legitimately appear once per office but a
parser bug could otherwise emit the same row twice.

Owner: @opnanalysis
LLM: claude-sonnet-5
"""
class ElectionCandidateValidationPipeline(object):
    def __init__(self):
        self.seen = set()

    def process_item(self, item, spider):
        if not item.get("candidate_name"):
            raise DropItem(f"Missing candidate_name: {item!r}")

        key = (item.get("site"), item.get("office"), item.get("candidate_name"))
        if key in self.seen:
            raise DropItem(f"Duplicate candidate row: {key}")
        self.seen.add(key)

        return item
