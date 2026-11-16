import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx
from structlog.typing import FilteringBoundLogger

from soundshark.models import CrawlPolicy, Page
from soundshark.utils import origin_of

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


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

    async def fetch_page(self, url: str) -> Page | None:
        response = await self.get(url)
        if response is None:
            return None
        if not response.is_success:
            self._log.warning("http.unexpected_status", url=url, status=response.status_code)
            return None
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
                response = await self._send_when_allowed(pacer, url)
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

    async def _send_when_allowed(self, pacer: HostPacer, url: str) -> httpx.Response:
        async with pacer.concurrency_limit:
            await pacer.wait_for_turn()
            started = time.perf_counter()
            response = await self._http_client.get(
                url,
                headers={"User-Agent": self._policy.user_agent},
                timeout=self._policy.request_timeout_seconds,
                follow_redirects=True,
            )
        self._log.debug(
            "http.response",
            url=url,
            status=response.status_code,
            bytes=len(response.content),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return response

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
