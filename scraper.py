"""
Description: This file contains the main scraper execution and loops
"""

"""
TODO:
## Initial politician search
    1. Walkthrough list of sites
        1. How to handle robots.txt?
        2. Read in list of sites from a file
    2. Use scrapy to walkthrough the site for relevant links
        1. Search for politicians
        2. Search for politician information
    3. Scrape w/ appropriate tool
        - Beautiful Soup - static
        - Playwright -dynamic sites
        - BeeScrapers - API/anti-bot/etc
    4. Save information to politician file
    5. Compress

## Scraped politician
    1. Walkthrough politician file's links for invalid links
        1. Remove invalid links
        2. Remove links that don't match the title
    2. Walkthrough list of sites
        2. Read in list of sites from a file
    3. Use scrapy to walkthrough the site for relevant links
        2. Search for politician information
    3. Scrape w/ appropriate tool
        - Beautiful Soup - static
        - Playwright -dynamic sites
        - BeeScrapers - API/anti-bot/etc
    4. Update information to politician file
    5. Compress
"""

STATIC_SITES=[]
DYNAMIC_SITES=[]
EXTRA_HELP_SITES=[]
SCRAPING_SITES=[]

