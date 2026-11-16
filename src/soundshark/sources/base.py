from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import httpx

from soundshark.models import Event


@runtime_checkable
class Source(Protocol):
    name: str

    def events(self, client: httpx.AsyncClient) -> AsyncIterator[Event]: ...
