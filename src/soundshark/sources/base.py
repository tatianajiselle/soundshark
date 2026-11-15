"""The Source interface: the one thing every data source must implement.

Real, site-specific sources live in a separate private package and are loaded
at runtime (see loader.py). This public repo only ships the interface and a demo.
"""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import httpx

from soundshark.models import Event


@runtime_checkable
class Source(Protocol):
    name: str

    def events(self, client: httpx.AsyncClient) -> AsyncIterator[Event]:
        """Yield events one at a time.

        Implement this as an async generator (`async def events(...)` with `yield`).
        That's why the signature has no `async` here: calling an async generator
        returns an AsyncIterator right away, which the engine consumes with
        `async for event in source.events(client)`.

        The client is shared by every source so connections get reused.
        Sources must be polite: respect the site's terms and pace requests.
        """
        ...
