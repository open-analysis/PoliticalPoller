#! /bin/bash
# Fetch one page, parse the candidate table, and print candidates grouped by office.
# Calls site_reader.read_page() (legacy single-page entry point).
usage() {
    cat << USAGE
Usage: $0 -u <url> [-m <method>] [--headless|--headed]
  -u, --url        Page to fetch                           [required]
  -m, --method     persistent_browser | playwright | requests
                                                           [default: persistent_browser]
      --headless   Run the browser without a window        [default]
      --headed     Show the browser window (needed to solve a CAPTCHA)
USAGE
}
URL=""; METHOD="persistent_browser"; HEADLESS="1"
while [ $# -gt 0 ]; do
    case "$1" in
        -u|--url) URL="$2"; shift 2;;
        -m|--method) METHOD="$2"; shift 2;;
        --headless) HEADLESS="1"; shift;;
        --headed) HEADLESS="0"; shift;;
        -h|--help) usage; exit 0;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1;;
    esac
done
[ -z "${URL}" ] && { echo "Missing --url" >&2; usage >&2; exit 1; }

source "$(dirname "$0")/common.sh"
pp_setup

PP_URL="${URL}" PP_METHOD="${METHOD}" PP_HEADLESS="${HEADLESS}" PP_SCRAPER_DIR="${SCRAPER_DIR}" python3 - << 'PY'
import json, os, sys
sys.path.insert(0, os.environ["PP_SCRAPER_DIR"])
from site_reader import read_page
result = read_page(
    os.environ["PP_URL"],
    method=os.environ["PP_METHOD"],
    headless=os.environ["PP_HEADLESS"] == "1",
)
print(json.dumps(result, indent=2))
PY
