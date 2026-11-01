#! /bin/bash
# Shared setup for the PoliticalPoller run scripts. Source this; don't run it.
#
#   - creates ./venv if it doesn't exist (same venv location as run.sh)
#   - activates it and installs the pip modules / Chromium (once; delete
#     venv/.deps_installed to force a reinstall)

ROOT_DIR=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
SCRAPER_DIR="${ROOT_DIR}/PoliticalPoller"
VENV_DIR="${ROOT_DIR}/venv"
DEPS_MARKER="${VENV_DIR}/.deps_installed"

pp_setup() {
    # Create python virtual env
    if [ ! -d "${VENV_DIR}" ]; then
        python3 -m venv "${VENV_DIR}" || { echo "Failed to create venv" >&2; exit 1; }
    fi

    # Activate VENV
    source "${VENV_DIR}/bin/activate"

    # Install pip modules + browser (first run only)
    if [ ! -f "${DEPS_MARKER}" ]; then
        pip3 install requests beautifulsoup4 playwright playwright-stealth scrapy || exit 1
        if playwright install chromium; then
            touch "${DEPS_MARKER}"
        else
            echo "WARNING: 'playwright install chromium' failed; browser-based sites (e.g. mn) won't work." >&2
        fi
    fi

    trap 'deactivate 2>/dev/null' EXIT

    # Outputs (candidate_data/, candidate_results_*.json, playwright_profile/)
    # land in the repo root.
    cd "${ROOT_DIR}"
}
