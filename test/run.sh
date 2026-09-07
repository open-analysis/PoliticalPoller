#! /bin/bash

ROOT_DIR=$(git rev-parse --show-toplevel)

# Create python virtual env
python3 -m venv venv

# Activate VENV
source ${ROOT_DIR}/venv/bin/activate

playwright install

# Install pip modules
pip3 install requests beautifulsoup4 playwright

# Run scripts
python3 ${ROOT_DIR}/test/static_scraper.py
# echo ""
# python3 ${ROOT_DIR}/test/dynamic_scraper.py

# Deactivate VENV
deactivate 