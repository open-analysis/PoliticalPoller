"""
Description: This file defines the spider's sub-classes/items.
"""


import scrapy

"""
Description: Spider subclass/item for data to return to caller for News sites.

NewsArticleItem is intentionally generic (title/url/site/dates only) so the
same spider and pipelines can be reused across many news sites instead of
being hard-coded to one site's fields.
Owner: @open-analysis
LLM: claude-sonnet-5
"""
class NewsArticleItem(scrapy.Item):
    site = scrapy.Field()             # config key, e.g. "cnn"
    title = scrapy.Field()
    url = scrapy.Field()
    published_date = scrapy.Field()   # best-effort, from meta tags
    scraped_at = scrapy.Field()       # ISO timestamp, set in the spider


"""
Description: Spider subclass/item for data to return to caller for election sites.

ElectionCandidateItem is intentionally generic (title/url/site/dates only) so the
same spider and pipelines can be reused across many sites instead of
being hard-coded to one site's fields.
Owner: @open-analysis
LLM: claude-sonnet-5
"""
class ElectionCandidateItem(scrapy.Item):
    site = scrapy.Field()             # config key, e.g. "mn"
    state = scrapy.Field()
    office_level = scrapy.Field()     # e.g. "Federal Offices", "State Offices"
    office = scrapy.Field()           # e.g. "U.S. Senator"
    candidate_name = scrapy.Field()
    party = scrapy.Field()
    website = scrapy.Field()
    file_date = scrapy.Field()
    source_url = scrapy.Field()
    scraped_at = scrapy.Field()       # ISO timestamp, set in the spider
