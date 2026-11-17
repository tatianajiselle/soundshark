import gzip

import httpx
import pytest
import structlog

from soundshark.clients import PoliteHttpClient, retry_after_seconds, stays_on_host
from soundshark.models import FetchFailure, Page
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


async def test_fetch_page_reports_error_statuses():
    async with httpx.AsyncClient(transport=httpx.MockTransport(FakeSite({}))) as http_client:
        polite = PoliteHttpClient(http_client, fast_policy(), structlog.get_logger())
        failure = await polite.fetch_page(fake_url("missing"))
    assert failure == FetchFailure(url=fake_url("missing"), reason="status 404", status=404)


async def test_redirects_are_followed_and_each_hop_waits_its_turn():
    site = FakeSite({"B": []})
    site.script("A", lambda: httpx.Response(301, headers={"Location": "/B"}))
    policy = fast_policy(seconds_between_requests_per_host=0.05)
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        page = await PoliteHttpClient(http_client, policy, structlog.get_logger()).fetch_page(fake_url("A"))
    assert isinstance(page, Page) and page.url == fake_url("A")
    first_request, redirected_request = site.page_request_times
    assert redirected_request - first_request >= 0.045


async def test_endless_redirects_are_a_failure():
    site = FakeSite({})
    site.script("A", *[lambda: httpx.Response(302, headers={"Location": "/A"})] * 10)
    policy = fast_policy(max_redirects=3)
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        failure = await PoliteHttpClient(http_client, policy, structlog.get_logger()).fetch_page(
            fake_url("A")
        )
    assert isinstance(failure, FetchFailure) and failure.status == 302
    assert site.requests_per_path["/A"] == 4


async def fetch_from(site: FakeSite, url: str, **policy) -> Page | FetchFailure:
    async with httpx.AsyncClient(transport=httpx.MockTransport(site)) as http_client:
        return await PoliteHttpClient(http_client, fast_policy(**policy), structlog.get_logger()).fetch_page(
            url
        )


def redirect_to(location: str, status: int = 302) -> httpx.Response:
    return httpx.Response(status, headers={"Location": location})


async def test_same_host_redirect_with_a_full_url_is_followed():
    site = FakeSite({"B": []})
    site.script("A", lambda: redirect_to("https://SITE.test/B"))
    page = await fetch_from(site, fake_url("A"))
    assert isinstance(page, Page) and page.status == 200
    assert site.requested_urls == [fake_url("A"), fake_url("B")]


@pytest.mark.parametrize(
    "location",
    [
        "https://elsewhere.example.org/B",
        "//elsewhere.example.org/B",
        "https://site.test.example.org/B",
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/B",
        "http://[::1]/B",
        "http://10.0.0.5/B",
        "file:///etc/passwd",
        "ftp://site.test/B",
        "gopher://site.test/B",
        "http://site.test/B",
        "https://site.test:8443/B",
    ],
)
async def test_redirect_off_the_requested_host_is_refused(location):
    site = FakeSite({"B": []})
    site.script("A", lambda: redirect_to(location))
    failure = await fetch_from(site, fake_url("A"))
    assert failure == FetchFailure(url=fake_url("A"), reason="status 302", status=302)
    assert site.requested_urls == [fake_url("A")]


async def test_a_later_hop_off_the_host_is_refused_too():
    site = FakeSite({"C": []})
    site.script("A", lambda: redirect_to("/B"))
    site.script("B", lambda: redirect_to("https://elsewhere.example.org/C", status=301))
    failure = await fetch_from(site, fake_url("A"))
    assert isinstance(failure, FetchFailure) and failure.status == 301
    assert site.requested_urls == [fake_url("A"), fake_url("B")]


async def test_http_to_https_on_the_same_host_is_followed():
    site = FakeSite({"B": []})
    site.script("A", lambda: redirect_to("https://site.test/B", status=301))
    page = await fetch_from(site, "http://site.test/A")
    assert isinstance(page, Page) and page.url == "http://site.test/A"
    assert site.requested_urls == ["http://site.test/A", "https://site.test/B"]


@pytest.mark.parametrize(
    ("requested", "target", "expected"),
    [
        ("https://site.test/A", "https://site.test/B", True),
        ("https://site.test/A", "https://Site.Test/B", True),
        ("http://site.test/A", "https://site.test/B", True),
        ("https://site.test:8443/A", "https://site.test:8443/B", True),
        ("https://site.test:8443/A", "https://site.test/B", True),
        ("http://site.test:8080/A", "https://site.test:8080/B", True),
        ("https://site.test/A", "https://site.test:443/B", True),
        ("https://site.test/A", "http://site.test/B", False),
        ("https://site.test/A", "https://site.test:8443/B", False),
        ("https://site.test/A", "https://www.site.test/B", False),
        ("https://site.test/A", "https://user@elsewhere.example.org/B", False),
        ("https://site.test/A", "https://site.test:notaport/B", False),
        ("https://site.test/A", "mailto:someone@site.test", False),
    ],
)
def test_stays_on_host(requested, target, expected):
    assert stays_on_host(requested, target) is expected


async def test_oversized_content_length_is_refused_without_reading_the_body():
    chunks_sent = 0

    async def body():
        nonlocal chunks_sent
        for _ in range(10):
            chunks_sent += 1
            yield b"x" * 100

    site = FakeSite({})
    site.script("A", lambda: httpx.Response(200, headers={"Content-Length": "5000"}, content=body()))
    failure = await fetch_from(site, fake_url("A"), max_response_bytes=1000)
    assert failure == FetchFailure(url=fake_url("A"), reason="response larger than 1000 bytes", status=200)
    assert chunks_sent == 0
    assert site.requests_per_path["/A"] == 1


async def test_oversized_streamed_body_is_refused_once_it_passes_the_limit():
    chunks_sent = 0

    async def endless_body():
        nonlocal chunks_sent
        while True:
            chunks_sent += 1
            yield b"x" * 100

    site = FakeSite({})
    site.script("A", lambda: httpx.Response(200, content=endless_body()))
    failure = await fetch_from(site, fake_url("A"), max_response_bytes=1000)
    assert failure == FetchFailure(url=fake_url("A"), reason="response larger than 1000 bytes", status=200)
    assert chunks_sent == 11
    assert site.requests_per_path["/A"] == 1


async def test_body_within_the_limit_is_kept_whole():
    body = b'{"links": []}' + b" " * 987
    site = FakeSite({})
    site.script(
        "A",
        lambda: httpx.Response(
            200, headers={"Content-Type": "application/json; charset=latin-1"}, content=body
        ),
    )
    page = await fetch_from(site, fake_url("A"), max_response_bytes=len(body))
    assert isinstance(page, Page)
    assert page.body == body
    assert page.content_type == "application/json; charset=latin-1"
    assert page.encoding == "latin-1"


async def test_compressed_body_is_decoded_and_limited_by_its_decoded_size():
    raw = b"x" * 5000
    site = FakeSite({"B": []})
    site.script(
        "A",
        lambda: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(raw)),
    )
    site.script(
        "B",
        lambda: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(raw)),
    )
    failure = await fetch_from(site, fake_url("A"), max_response_bytes=1000)
    assert isinstance(failure, FetchFailure) and failure.reason == "response larger than 1000 bytes"
    page = await fetch_from(site, fake_url("B"))
    assert isinstance(page, Page) and page.body == raw


async def test_retry_after_still_works_with_streamed_responses():
    site = FakeSite({"A": []})
    site.script("A", lambda: httpx.Response(503, headers={"Retry-After": "1"}, content=b"busy"))
    page = await fetch_from(site, fake_url("A"))
    assert isinstance(page, Page)
    first_request, retry = site.page_request_times
    assert retry - first_request >= 0.95


@pytest.mark.parametrize(
    ("header", "expected"),
    [("120", 120.0), ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0), ("soon", None)],
)
def test_retry_after_seconds_reads_both_header_formats(header, expected):
    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": header})) == expected


def test_retry_after_seconds_without_header():
    assert retry_after_seconds(httpx.Response(429)) is None
