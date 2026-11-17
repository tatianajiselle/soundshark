from dataclasses import dataclass

DEFAULT_USER_AGENT = "soundshark/0.1 (+https://soundshark.dev)"


@dataclass(frozen=True, slots=True)
class CrawlPolicy:
    user_agent: str = DEFAULT_USER_AGENT
    max_concurrent_requests_per_host: int = 1
    seconds_between_requests_per_host: float = 2.0
    max_retries: int = 3
    retry_backoff_seconds: float = 1.0
    max_retry_after_seconds: float = 300.0
    request_timeout_seconds: float = 20.0
    max_redirects: int = 5
    max_response_bytes: int = 10 * 1024 * 1024
    max_consecutive_failures: int = 5
    statuses_that_stop_the_crawl: frozenset[int] = frozenset({401, 403, 451})
