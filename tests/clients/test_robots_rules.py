import asyncio

import httpx
import structlog

from soundshark.clients import PoliteHttpClient, RobotsRules
from tests.fakes import FakeSite, fake_url, fast_policy


def robots_for(
    site: FakeSite, http_client: httpx.AsyncClient, **policy
) -> tuple[RobotsRules, PoliteHttpClient]:
    polite = PoliteHttpClient(http_client, fast_policy(**policy), structlog.get_logger())
    return RobotsRules(polite, structlog.get_logger()), polite


async def allowed_pages(site: FakeSite, pages: str, **policy) -> set[str]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        robots, _ = robots_for(site, http_client, **policy)
        return {page for page in pages if await robots.is_allowed(fake_url(page))}


async def test_disallowed_paths_are_refused():
    site = FakeSite({}, robots_txt="User-agent: *\nDisallow: /C\n")
    assert await allowed_pages(site, "ABC") == {"A", "B"}


async def test_rules_for_our_user_agent_win_over_the_wildcard():
    site = FakeSite({}, robots_txt="User-agent: soundshark\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert await allowed_pages(site, "ABC") == set()


async def test_missing_robots_txt_allows_everything():
    assert await allowed_pages(FakeSite({}, robots_txt=404), "ABC") == {"A", "B", "C"}


async def test_robots_txt_server_error_disallows_everything():
    assert await allowed_pages(FakeSite({}, robots_txt=503), "ABC", max_retries=0) == set()


async def test_robots_txt_is_fetched_once_per_host_even_when_asked_concurrently():
    site = FakeSite({}, robots_txt="User-agent: *\nAllow: /\n")
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        robots, _ = robots_for(site, http_client)
        await asyncio.gather(*(robots.is_allowed(fake_url(page)) for page in "ABCDEF"))
    assert site.requests_per_path["/robots.txt"] == 1


async def test_crawl_delay_slows_down_later_requests():
    site = FakeSite({"A": [], "B": []}, robots_txt="User-agent: *\nCrawl-delay: 1\n")
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        robots, polite = robots_for(site, http_client)
        await robots.is_allowed(fake_url("A"))
        await polite.get(fake_url("A"))
        await polite.get(fake_url("B"))
    first, second = site.page_request_times
    assert second - first >= 0.95
