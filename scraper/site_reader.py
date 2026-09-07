"""
Description: This file contains the various site reader/scraping functions.
"""

def try_antibot_read():
    pass

def try_dynamic_read():
    pass

def try_static_read():
    pass

"""
Description: This function reads the website by trying the static reader, then
    dynamic, finally trying to use Beescraper.
Param[in] input_webpage:    URI for the webpage to be read
Owner: @opnanalysis
"""
def read_page(input_webpage: str):
    pass

"""
Description: Finds political associations for a given politician
    - Office held/going for
    - State serving in
    - District/ward/county/etc serving 
    - Party affiliation 
    - Group affiliations?
    - Bills/Orders/Research/etc with their name attached to i
Param[in] name:     Politician name to search for
Param[in] assoc:    Association to search for
Owner: @opnanalysis
"""
def find_political_assoc(name: str, assoc: str):
    pass

"""
Description: Finds a given politician information
Param[in] name:     Politician name to search for
Owner: @opnanalysis
"""
def find_politician(name: str):
    pass