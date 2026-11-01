#! /bin/bash
# Scrape an election site and merge the results into candidate_data/candidates_<site>.json.
# Calls spider_runner.sync_election_candidates().
usage() {
    cat << USAGE
Usage: $0 [-s <site>] [--headless|--headed]
  -s, --site       Election site key, e.g. mn              [default: mn]
      --headless   Run the browser without a window        [default]
      --headed     Show the browser window (needed to solve a CAPTCHA)
USAGE
}
SITE="mn"; HEADLESS="1"
while [ $# -gt 0 ]; do
    case "$1" in
        -s|--site) SITE="$2"; shift 2;;
        --headless) HEADLESS="1"; shift;;
        --headed) HEADLESS="0"; shift;;
        -h|--help) usage; exit 0;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1;;
    esac
done

source "$(dirname "$0")/common.sh"
pp_setup

PP_SITE="${SITE}" PP_HEADLESS="${HEADLESS}" PP_SCRAPER_DIR="${SCRAPER_DIR}" python3 - << 'PY'
import os, sys
sys.path.insert(0, os.environ["PP_SCRAPER_DIR"])
from spider_runner import sync_election_candidates
sync_election_candidates(
    os.environ["PP_SITE"],
    project_dir=os.environ["PP_SCRAPER_DIR"],
    headless=os.environ["PP_HEADLESS"] == "1",
)
PY
