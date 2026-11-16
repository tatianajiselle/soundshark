import httpx
import pytest
import structlog

from soundshark.clients import PoliteHttpClient, retry_after_seconds
from tests.fakes import FakeSite, fake_url, fast_policy


async def get_from(site: FakeSite, page_name: str, **policy) -> tuple[httpx.Response | None, FakeSite]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        polite = PoliteHttpClient(http_client, fast_policy(**policy), structlog.get_logger())
        return await polite.get(fake_url(page_name)), site


async def test_retries_server_errors_until_success():
    site = FakeSite({"A": []})
    site.script("A", lambda: httpx.Response(503), lambda: httpx.Response(500))
    response, _ = await get_from(site, "A")
    assert response is not None and response.status_code == 200
    assert site.requests_per_path["/A"] == 3


async def test_gives_up_after_max_retries_and_returns_the_last_response():
    site = FakeSite({"A": []})
    site.script("A", *[lambda: httpx.Response(503)] * 10)
    response, _ = await get_from(site, "A", max_retries=2)
    assert response is not None and response.status_code == 503
    assert site.requests_per_path["/A"] == 3


async def test_does_not_retry_client_errors():
    site = FakeSite({})
    response, _ = await get_from(site, "missing")
    assert response is not None and response.status_code == 404
    assert site.requests_per_path["/missing"] == 1


async def test_waits_as_long_as_retry_after_asks():
    site = FakeSite({"A": []})
    site.script("A", lambda: httpx.Response(429, headers={"Retry-After": "1"}))
    await get_from(site, "A")
    first_request, retry = site.page_request_times
    assert retry - first_request >= 0.95


async def test_skips_absurd_retry_after_instead_of_waiting():
    site = FakeSite({"A": []})
    site.script("A", lambda: httpx.Response(429, headers={"Retry-After": "86400"}))
    response, _ = await get_from(site, "A")
    assert response is not None and response.status_code == 429
    assert site.requests_per_path["/A"] == 1


async def test_spaces_requests_to_the_same_host():
    site = FakeSite({"A": [], "B": [], "C": []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        polite = PoliteHttpClient(
            http_client,
            fast_policy(seconds_between_requests_per_host=0.05, max_concurrent_requests_per_host=3),
            structlog.get_logger(),
        )
        for page in "ABC":
            await polite.get(fake_url(page))
    gaps = [
        later - earlier
        for earlier, later in zip(site.page_request_times, site.page_request_times[1:], strict=False)
    ]
    assert min(gaps) >= 0.045


async def test_fetch_page_returns_none_for_error_statuses():
    async with httpx.AsyncClient(transport=httpx.MockTransport(FakeSite({}))) as http_client:
        polite = PoliteHttpClient(http_client, fast_policy(), structlog.get_logger())
        assert await polite.fetch_page(fake_url("missing")) is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [("120", 120.0), ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0), ("soon", None)],
)
def test_retry_after_seconds_reads_both_header_formats(header, expected):
    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": header})) == expected


def test_retry_after_seconds_without_header():
    assert retry_after_seconds(httpx.Response(429)) is None
