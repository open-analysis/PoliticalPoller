#! /bin/bash
# Check one election-site config against its live page (or a saved HTML file):
# prints the tables found, the records parsed, and a diagnosis if there are none.
# Calls PoliticalPoller/probe_site.py.
usage() {
    cat << USAGE
Usage: $0 <site> [--url <url>] [--html <file>] [--browser] [--headed] [--save <file>] [--show N]
  <site>        Election site key, e.g. wa, ky, sd
  --url         Page to probe             [default: the site's first start URL]
  --html        Probe a saved HTML file instead of fetching
  --browser     Fetch with the Playwright browser (JS pages, CAPTCHAs)
  --headed      Show the browser window
  --save        Save the fetched HTML (handy as a test fixture)
Exit status is 0 when at least one record was parsed, 1 otherwise.
USAGE
}
[ $# -eq 0 ] && { usage >&2; exit 1; }
case "$1" in -h|--help) usage; exit 0;; esac

source "$(dirname "$0")/common.sh"
pp_setup
python3 "${SCRAPER_DIR}/probe_site.py" "$@"
