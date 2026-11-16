from datetime import UTC, datetime

import pytest

from soundshark.pages import Page
from soundshark.store import CrawlRun


def test_page_text_decodes_body():
    page = Page(url="https://x.test/", status=200, body="Säule".encode(), fetched_at=datetime.now(UTC))
    assert page.text == "Säule"


def test_page_requires_aware_fetched_at():
    with pytest.raises(ValueError):
        Page(url="https://x.test/", status=200, body=b"", fetched_at=datetime(2026, 1, 1))


def test_crawl_runs_get_unique_ids():
    assert CrawlRun("demo").id != CrawlRun("demo").id
