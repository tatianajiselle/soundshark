import asyncio
from urllib.robotparser import RobotFileParser

from structlog.typing import FilteringBoundLogger

from soundshark.clients.polite_http_client import PoliteHttpClient, ResponseTooLarge
from soundshark.utils import origin_of

_DISALLOW_EVERYTHING = ["User-agent: *", "Disallow: /"]
_ALLOW_EVERYTHING: list[str] = []


class RobotsRules:
    def __init__(self, http: PoliteHttpClient, log: FilteringBoundLogger) -> None:
        self._http = http
        self._log = log
        self._rules_by_origin: dict[str, asyncio.Task[RobotFileParser]] = {}

    async def is_allowed(self, url: str) -> bool:
        origin = origin_of(url)
        if origin not in self._rules_by_origin:
            self._rules_by_origin[origin] = asyncio.create_task(self._load_rules(origin))
        rules = await self._rules_by_origin[origin]
        return rules.can_fetch(self._http.policy.user_agent, url)

    async def _load_rules(self, origin: str) -> RobotFileParser:
        robots_url = f"{origin}/robots.txt"
        rules = RobotFileParser(robots_url)
        try:
            response = await self._http.get(robots_url)
        except ResponseTooLarge:
            response = None

        if response is None or response.is_redirect or response.status_code >= 500:
            status = None if response is None else response.status_code
            self._log.warning("robots.unreachable", origin=origin, status=status, treating_as="disallow all")
            rules.parse(_DISALLOW_EVERYTHING)
            return rules

        if response.status_code >= 400:
            self._log.info(
                "robots.missing", origin=origin, status=response.status_code, treating_as="allow all"
            )
            rules.parse(_ALLOW_EVERYTHING)
            return rules

        rules.parse(response.text.splitlines())
        crawl_delay = rules.crawl_delay(self._http.policy.user_agent)
        if crawl_delay is not None:
            self._http.slow_down(origin, float(crawl_delay))
        self._log.info("robots.loaded", origin=origin, crawl_delay_seconds=crawl_delay)
        return rules
