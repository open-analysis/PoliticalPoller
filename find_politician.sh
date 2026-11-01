#! /bin/bash
# Look up a candidate by name (checks the saved store first, then the live site).
# Calls site_reader.find_politician().
usage() {
    cat << USAGE
Usage: $0 -n "<name>" [-s <site>] [--refresh] [--headless|--headed]
  -n, --name       Candidate name (or part of it)         [required]
  -s, --site       Election site key, e.g. mn              [default: mn]
  -r, --refresh    Skip the saved store and scrape live
      --headless   Run the browser without a window
      --headed     Show the browser window (needed to solve a CAPTCHA) [default]
Writes candidate_results_<date>.json in the repo root when there are matches.
USAGE
}
NAME=""; SITE="mn"; REFRESH="0"; HEADLESS="0"
while [ $# -gt 0 ]; do
    case "$1" in
        -n|--name) NAME="$2"; shift 2;;
        -s|--site) SITE="$2"; shift 2;;
        -r|--refresh) REFRESH="1"; shift;;
        --headless) HEADLESS="1"; shift;;
        --headed) HEADLESS="0"; shift;;
        -h|--help) usage; exit 0;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1;;
    esac
done
[ -z "${NAME}" ] && { echo "Missing --name" >&2; usage >&2; exit 1; }

source "$(dirname "$0")/common.sh"
pp_setup

PP_NAME="${NAME}" PP_SITE="${SITE}" PP_REFRESH="${REFRESH}" PP_HEADLESS="${HEADLESS}" \
PP_SCRAPER_DIR="${SCRAPER_DIR}" python3 - << 'PY'
import os, sys
sys.path.insert(0, os.environ["PP_SCRAPER_DIR"])
from site_reader import find_politician
find_politician(
    os.environ["PP_NAME"],
    site=os.environ["PP_SITE"],
    project_dir=os.environ["PP_SCRAPER_DIR"],
    headless=os.environ["PP_HEADLESS"] == "1",
    force_refresh=os.environ["PP_REFRESH"] == "1",
)
PY
