#! /bin/bash

ROOT_DIR=$(git rev-parse --show-toplevel)

# Create python virtual env
# python3 -m venv venv

# Activate VENV
source ${ROOT_DIR}/venv/bin/activate

# Install pip modules
pip3 install requests beautifulsoup4 playwright playwright-stealth
playwright install chromium
# Run scripts
python3 ${ROOT_DIR}/scraper/site_reader.py

# Deactivate VENV
deactivate 
