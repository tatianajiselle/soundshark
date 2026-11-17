import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx
from structlog.typing import FilteringBoundLogger

from soundshark.models import CrawlPolicy, FetchFailure, Page
from soundshark.utils import origin_of

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_PORTS = {"http": 80, "https": 443}
_HEADERS_ABOUT_THE_RAW_BODY = frozenset({"content-encoding", "content-length", "transfer-encoding"})


class ResponseTooLarge(Exception):
    def __init__(self, url: str, status: int, max_bytes: int) -> None:
        super().__init__(f"{url} answered with more than {max_bytes} bytes")
        self.url = url
        self.status = status
        self.max_bytes = max_bytes


@dataclass(slots=True)
class HostPacer:
    concurrency_limit: asyncio.Semaphore
    seconds_between_requests: float
    next_request_at: float = 0.0

    async def wait_for_turn(self) -> None:
        now = asyncio.get_running_loop().time()
        my_turn_at = max(now, self.next_request_at)
        self.next_request_at = my_turn_at + self.seconds_between_requests
        if my_turn_at > now:
            await asyncio.sleep(my_turn_at - now)

    def hold_off_until(self, loop_time: float) -> None:
        self.next_request_at = max(self.next_request_at, loop_time)


class PoliteHttpClient:
    def __init__(
        self, http_client: httpx.AsyncClient, policy: CrawlPolicy, log: FilteringBoundLogger
    ) -> None:
        self._http_client = http_client
        self._policy = policy
        self._log = log
        self._pacer_by_origin: dict[str, HostPacer] = {}

    @property
    def policy(self) -> CrawlPolicy:
        return self._policy

    def slow_down(self, url: str, seconds_between_requests: float) -> None:
        pacer = self._pacer_for(url)
        pacer.seconds_between_requests = max(pacer.seconds_between_requests, seconds_between_requests)

    async def fetch_page(self, url: str) -> Page | FetchFailure:
        try:
            response = await self.get(url)
        except ResponseTooLarge as error:
            return FetchFailure(
                url=url, reason=f"response larger than {error.max_bytes} bytes", status=error.status
            )
        if response is None:
            return FetchFailure(url=url, reason="no response after retries")
        if not response.is_success:
            self._log.warning("http.unexpected_status", url=url, status=response.status_code)
            return FetchFailure(url=url, reason=f"status {response.status_code}", status=response.status_code)
        return Page(
            url=url,
            status=response.status_code,
            body=response.content,
            fetched_at=datetime.now(UTC),
            content_type=response.headers.get("content-type"),
            encoding=response.encoding or "utf-8",
        )

    async def get(self, url: str) -> httpx.Response | None:
        pacer = self._pacer_for(url)
        attempts_allowed = self._policy.max_retries + 1
        for attempt in range(1, attempts_allowed + 1):
            is_last_attempt = attempt == attempts_allowed
            try:
                response = await self._send_following_redirects(url)
            except httpx.TransportError as error:
                reason = f"{type(error).__name__}: {error}"
                if is_last_attempt:
                    self._log.warning("http.gave_up", url=url, attempts=attempt, reason=reason)
                    return None
                wait_seconds = self._backoff_seconds(attempt)
                self._log.info(
                    "http.retrying", url=url, attempt=attempt, reason=reason, wait_seconds=wait_seconds
                )
                await asyncio.sleep(wait_seconds)
                continue

            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response
            reason = f"status {response.status_code}"
            if is_last_attempt:
                self._log.warning("http.gave_up", url=url, attempts=attempt, reason=reason)
                return response
            wait_seconds = retry_after_seconds(response) or self._backoff_seconds(attempt)
            if wait_seconds > self._policy.max_retry_after_seconds:
                self._log.warning("http.retry_after_too_long", url=url, wait_seconds=wait_seconds)
                return response
            self._log.info(
                "http.retrying", url=url, attempt=attempt, reason=reason, wait_seconds=wait_seconds
            )
            pacer.hold_off_until(asyncio.get_running_loop().time() + wait_seconds)
        return None

    async def _send_following_redirects(self, url: str) -> httpx.Response:
        current_url = url
        response = await self._send_when_allowed(current_url)
        redirects_followed = 0
        while response.is_redirect and redirects_followed < self._policy.max_redirects:
            next_url = urljoin(current_url, response.headers["location"])
            if not stays_on_host(url, next_url):
                self._log.warning(
                    "http.redirect_refused", url=current_url, target=next_url, status=response.status_code
                )
                return response
            self._log.debug("http.redirected", url=current_url, to=next_url, status=response.status_code)
            current_url = next_url
            response = await self._send_when_allowed(current_url)
            redirects_followed += 1
        return response

    async def _send_when_allowed(self, url: str) -> httpx.Response:
        pacer = self._pacer_for(url)
        async with pacer.concurrency_limit:
            await pacer.wait_for_turn()
            started = time.perf_counter()
            async with self._http_client.stream(
                "GET",
                url,
                headers={"User-Agent": self._policy.user_agent},
                timeout=self._policy.request_timeout_seconds,
                follow_redirects=False,
            ) as streamed:
                body = await self._read_body_within_limit(url, streamed)
        self._log.debug(
            "http.response",
            url=url,
            status=streamed.status_code,
            bytes=len(body),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return httpx.Response(
            streamed.status_code,
            headers=[
                (name, value)
                for name, value in streamed.headers.multi_items()
                if name.lower() not in _HEADERS_ABOUT_THE_RAW_BODY
            ],
            content=body,
            request=streamed.request,
            default_encoding=streamed.default_encoding,
        )

    async def _read_body_within_limit(self, url: str, streamed: httpx.Response) -> bytes:
        max_bytes = self._policy.max_response_bytes
        declared_bytes = declared_content_length(streamed)
        if declared_bytes is not None and declared_bytes > max_bytes:
            self._log.warning(
                "http.response_too_large", url=url, max_bytes=max_bytes, content_length=declared_bytes
            )
            raise ResponseTooLarge(url, streamed.status_code, max_bytes)
        chunks: list[bytes] = []
        bytes_read = 0
        async for chunk in streamed.aiter_bytes():
            bytes_read += len(chunk)
            if bytes_read > max_bytes:
                self._log.warning(
                    "http.response_too_large", url=url, max_bytes=max_bytes, bytes_read=bytes_read
                )
                raise ResponseTooLarge(url, streamed.status_code, max_bytes)
            chunks.append(chunk)
        return b"".join(chunks)

    def _pacer_for(self, url: str) -> HostPacer:
        origin = origin_of(url)
        if origin not in self._pacer_by_origin:
            self._pacer_by_origin[origin] = HostPacer(
                concurrency_limit=asyncio.Semaphore(self._policy.max_concurrent_requests_per_host),
                seconds_between_requests=self._policy.seconds_between_requests_per_host,
            )
        return self._pacer_by_origin[origin]

    def _backoff_seconds(self, attempt: int) -> float:
        exponential = self._policy.retry_backoff_seconds * 2 ** (attempt - 1)
        return round(exponential * random.uniform(0.5, 1.0), 3)


def stays_on_host(requested_url: str, redirect_url: str) -> bool:
    requested = urlsplit(requested_url)
    target = urlsplit(redirect_url)
    if target.scheme not in DEFAULT_PORTS or requested.scheme not in DEFAULT_PORTS:
        return False
    if target.scheme != requested.scheme and (requested.scheme, target.scheme) != ("http", "https"):
        return False
    if not target.hostname or target.hostname != requested.hostname:
        return False
    try:
        requested_port = requested.port or DEFAULT_PORTS[requested.scheme]
        target_port = target.port or DEFAULT_PORTS[target.scheme]
    except ValueError:
        return False
    return target_port in (requested_port, DEFAULT_PORTS[target.scheme])


def declared_content_length(response: httpx.Response) -> int | None:
    header = response.headers.get("content-length")
    if header is None or not header.strip().isdigit():
        return None
    return int(header)


def retry_after_seconds(response: httpx.Response) -> float | None:
    header = response.headers.get("retry-after")
    if header is None:
        return None
    if header.strip().isdigit():
        return float(header)
    try:
        retry_at = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
