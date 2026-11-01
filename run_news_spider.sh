#! /bin/bash
# Crawl a news site and print matching articles as JSON.
# Calls spider_runner.run_news_spider().
usage() {
    cat << USAGE
Usage: $0 [-s <site>] [--candidate <name>] [--election <text>] [--location <text>] [-o <file>]
  -s, --site        News site key from scraper/site_configs.py [default: cnn]
      --candidate   Only articles whose title mentions this
      --election    Only articles whose title mentions this (e.g. "2026 midterms")
      --location    Only articles whose title mentions this (e.g. "Minnesota")
  -o, --output      Write JSON to this file instead of stdout
Note: crawls can take a long time (timeout is 30 minutes).
USAGE
}
SITE="cnn"; CANDIDATE=""; ELECTION=""; LOCATION=""; OUTPUT=""
while [ $# -gt 0 ]; do
    case "$1" in
        -s|--site) SITE="$2"; shift 2;;
        --candidate) CANDIDATE="$2"; shift 2;;
        --election) ELECTION="$2"; shift 2;;
        --location) LOCATION="$2"; shift 2;;
        -o|--output) OUTPUT="$2"; shift 2;;
        -h|--help) usage; exit 0;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 1;;
    esac
done
[ -n "${OUTPUT}" ] && [[ "${OUTPUT}" != /* ]] && OUTPUT="$(pwd)/${OUTPUT}"

source "$(dirname "$0")/common.sh"
pp_setup

PP_SITE="${SITE}" PP_CANDIDATE="${CANDIDATE}" PP_ELECTION="${ELECTION}" PP_LOCATION="${LOCATION}" \
PP_OUTPUT="${OUTPUT}" PP_SCRAPER_DIR="${SCRAPER_DIR}" python3 - << 'PY'
import json, os, sys
sys.path.insert(0, os.environ["PP_SCRAPER_DIR"])
from spider_runner import run_news_spider
articles = run_news_spider(
    os.environ["PP_SITE"],
    candidate=os.environ["PP_CANDIDATE"] or None,
    election=os.environ["PP_ELECTION"] or None,
    location=os.environ["PP_LOCATION"] or None,
    project_dir=os.environ["PP_SCRAPER_DIR"],
)
out = os.environ["PP_OUTPUT"]
if out:
    with open(out, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2)
    print(f"Wrote {len(articles)} article(s) to {out}")
else:
    print(json.dumps(articles, indent=2))
PY
