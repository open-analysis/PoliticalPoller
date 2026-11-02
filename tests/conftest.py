"""Shared pytest setup.

The project mixes two import styles: modules inside PoliticalPoller/ import
each other flat (``from utils import ...``), while the Scrapy spiders import
``PoliticalPoller.items``. Both the PoliticalPoller/ directory and the repo
root therefore need to be on sys.path.
"""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "PoliticalPoller")
for path in (PKG, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture
def store_dir(tmp_path):
    """An empty, throwaway candidate-store directory."""
    return str(tmp_path / "candidate_data")


def make_record(name, office="Governor", party="DFL", website="https://janedoe.com",
                file_date="05/26/2026", filer_id=None, state="Minnesota", level="State Offices"):
    """A candidate record shaped like run_election_spider() output."""
    return {
        "site": "mn", "state": state, "office_level": level, "office": office,
        "candidate_name": name, "party": party, "website": website,
        "file_date": file_date, "filer_id": filer_id,
        "source_url": "https://example.test/", "scraped_at": "2026-01-01T00:00:00+00:00",
    }


# Minnesota-style markup: level row / office row / column header / data rows.
MN_HTML = """
<table>
  <tr><td colspan="6">Federal Offices</td></tr>
  <tr><td></td><td colspan="5">U.S. Senator</td></tr>
  <tr><td></td><td></td><td>Candidate Name</td><td>Party</td><td>Website</td><td>File Date</td></tr>
  <tr><td colspan="2"></td><td>Jane Doe</td><td>DFL</td>
      <td><a href="https://janedoe.com">site</a></td><td>05/26/2026</td></tr>
  <tr><td colspan="2"></td><td>John Roe</td><td>GOP</td>
      <td><a href="javascript:void(0)">none</a></td><td>05/27/2026</td></tr>
  <tr><td colspan="6">State Offices</td></tr>
  <tr><td></td><td colspan="5">Governor</td></tr>
  <tr><td colspan="2"></td><td>Jane Doe</td><td>DFL</td><td>janedoe.com</td><td>06/01/2026</td></tr>
  <tr><td colspan="2"></td><td></td><td>IND</td><td></td><td>06/02/2026</td></tr>
</table>
"""


@pytest.fixture
def mn_html():
    return MN_HTML
