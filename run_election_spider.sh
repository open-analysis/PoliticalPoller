#! /bin/bash
# Scrape an election site and print the candidates as JSON (nothing is saved to the store).
# Calls spider_runner.run_election_spider().
usage() {
    cat << USAGE
Usage: $0 [-s <site>] [-o <file>] [--headless|--headed]
  -s, --site       Election site key, e.g. mn              [default: mn]
  -o, --output     Write JSON to this file instead of stdout
      --headless   Run the browser without a window        [default]
      --headed     Show the browser window (needed to solve a CAPTCHA)
USAGE
}
SITE="mn"; OUTPUT=""; HEADLESS="1"
while [ $# -gt 0 ]; do
    case "$1" in
        -s|--site) SITE="$2"; shift 2;;
        -o|--output) OUTPUT="$2"; shift 2;;
        --headless) HEADLESS="1"; shift;;
        --headed) HEADLESS="0"; shift;;
        -h|--help) usage; exit 0;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1;;
    esac
done
# Resolve relative output paths against where the user ran the script
[ -n "${OUTPUT}" ] && [[ "${OUTPUT}" != /* ]] && OUTPUT="$(pwd)/${OUTPUT}"

source "$(dirname "$0")/common.sh"
pp_setup

PP_SITE="${SITE}" PP_OUTPUT="${OUTPUT}" PP_HEADLESS="${HEADLESS}" PP_SCRAPER_DIR="${SCRAPER_DIR}" python3 - << 'PY'
import json, os, sys
sys.path.insert(0, os.environ["PP_SCRAPER_DIR"])
from spider_runner import run_election_spider
records = run_election_spider(
    os.environ["PP_SITE"],
    project_dir=os.environ["PP_SCRAPER_DIR"],
    headless=os.environ["PP_HEADLESS"] == "1",
)
out = os.environ["PP_OUTPUT"]
if out:
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Wrote {len(records)} record(s) to {out}")
else:
    print(json.dumps(records, indent=2))
PY
