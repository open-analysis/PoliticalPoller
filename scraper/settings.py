"""
Description: This file defines the settings necessary the spiders to crawl a given website.ß
For simplicity, this file contains only settings considered important or
commonly used. You can find more settings consulting the documentation:

    https://docs.scrapy.org/en/latest/topics/settings.html
    https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
    https://docs.scrapy.org/en/latest/topics/spider-middleware.html
"""

BOT_NAME = 'PoliticalPoller'

SPIDER_MODULES = ['PoliticalPoller.spiders']
NEWSPIDER_MODULE = 'PoliticalPoller.spiders'


# Crawl responsibly by identifying yourself (and your website) on the user-agent
# LLM: claude-sonnet-5 -- a real UA + contact point is a best practice: sites
# that want to rate-limit or contact you about your crawler can, instead of
# just silently blocking an anonymous-looking client.
USER_AGENT = 'PoliticalPoller/1.0 (+https://example.com/bot-info; contact@example.com)'

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests performed by Scrapy (default: 16)
#CONCURRENT_REQUESTS = 32

# Be polite to any single site: cap concurrency per domain and add a small
# delay. AutoThrottle then adjusts the delay up/down based on the site's
# actual response latency, which is gentler than a fixed DOWNLOAD_DELAY
# alone.
# LLM: claude-sonnet-5
CONCURRENT_REQUESTS_PER_DOMAIN = 4
DOWNLOAD_DELAY = 1

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 30
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
#AUTOTHROTTLE_DEBUG = True

# A sitemap crawl can otherwise recurse indefinitely if a site's index
# pages link back into each other; cap how deep NewsSpider will follow
# index links from a start_url.
# LLM: claude-sonnet-5
DEPTH_LIMIT = 6

# Retry failed requests -- transient errors are common at any real crawl
# volume and shouldn't lose the whole page.
RETRY_ENABLED = True
RETRY_TIMES = 2

# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#   'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
#   'Accept-Language': 'en',
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    'PoliticalPoller.middlewares.PoliticalpollerSpiderMiddleware': 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    'PoliticalPoller.middlewares.PoliticalpollerDownloaderMiddleware': 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    'scrapy.extensions.telnet.TelnetConsole': None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
# LLM: claude-sonnet-5 -- validation/dedup pipeline enabled so every item,
# from any spider, gets checked before export.
ITEM_PIPELINES = {
    'PoliticalPoller.pipelines.NewsArticleValidationPipeline': 200,
    'PoliticalPoller.pipelines.ElectionCandidateValidationPipeline': 210,
    'PoliticalPoller.pipelines.PoliticalpollerPipeline': 300,
}

# Where scraped items get written by default. Override per run with
# `scrapy crawl news -a site=cnn -o some_other_file.jsonl` (same pattern
# for `scrapy crawl elections -a site=...`). %(site)s comes from the
# `self.site` attribute both NewsSpider and ElectionSpider set.
# LLM: claude-sonnet-5
FEEDS = {
    '%(name)s_%(site)s_%(time)s.jsonl': {
        'format': 'jsonlines',
        'encoding': 'utf8',
        'overwrite': False,
    },
}

# ElectionSpider tightens these further via its own custom_settings
# (government sites are generally lower-capacity and more sensitive to
# scraping traffic than commercial news sites), but the baseline here
# still applies to every other setting it doesn't override.

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
# (Superseded by the AUTOTHROTTLE_* block above, kept enabled.)

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = 'httpcache'
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'
