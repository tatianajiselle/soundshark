"""Run every configured source at once and summarize what came back.

    .venv/bin/python -m wavelength
"""

import asyncio
import time

import httpx
from dotenv import load_dotenv

from wavelength.models import Event
from wavelength.sources.base import Source
from wavelength.sources.loader import load_sources


async def collect(source: Source, client: httpx.AsyncClient) -> list[Event]:
    return [event async for event in source.events(client)]


async def main() -> None:
    load_dotenv()  # reads .env if present (gitignored)
    sources = load_sources()
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=20) as client:
        async with asyncio.TaskGroup() as tg:
            tasks = {s.name: tg.create_task(collect(s, client)) for s in sources}
    for name, task in tasks.items():
        events = task.result()
        artists = {a for e in events for a in e.artists}
        print(f"{name:12} {len(events):5} events  {len(artists):5} artists")
    print(f"done in {time.perf_counter() - start:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
