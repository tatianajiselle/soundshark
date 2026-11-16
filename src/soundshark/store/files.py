import asyncio
import base64
import dataclasses
import gzip
import hashlib
import json
import os
import re
import tempfile
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from soundshark.pages import Page
from soundshark.store.base import CrawlRun

_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_PAGE_SUFFIX = ".json.gz"


def _segment(value: str, what: str) -> str:
    if not _SEGMENT.fullmatch(value):
        raise ValueError(f"{what} {value!r} is not a safe path segment (letters, digits, _ and -)")
    return value


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _encode_page(page: Page) -> bytes:
    record = {
        "url": page.url,
        "status": page.status,
        "content_type": page.content_type,
        "encoding": page.encoding,
        "fetched_at": page.fetched_at.isoformat(),
        "body": base64.b64encode(page.body).decode("ascii"),
    }
    return gzip.compress(json.dumps(record).encode(), mtime=0)


def _decode_page(data: bytes) -> Page:
    record = json.loads(gzip.decompress(data))
    return Page(
        url=record["url"],
        status=record["status"],
        body=base64.b64decode(record["body"]),
        fetched_at=datetime.fromisoformat(record["fetched_at"]),
        content_type=record["content_type"],
        encoding=record["encoding"],
    )


def _read_page(path: Path) -> Page | None:
    try:
        return _decode_page(path.read_bytes())
    except FileNotFoundError:
        return None


def _list_pages(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir() if p.name.endswith(_PAGE_SUFFIX) and not p.name.startswith(".")
    )


def _run_record(run: CrawlRun) -> dict[str, Any]:
    record = dataclasses.asdict(run)
    for key, value in record.items():
        if isinstance(value, datetime):
            record[key] = value.isoformat()
    return record


class FileStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _page_path(self, source: str, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.root / "raw" / _segment(source, "source") / f"{key}{_PAGE_SUFFIX}"

    async def get(self, source: str, url: str) -> Page | None:
        return await asyncio.to_thread(_read_page, self._page_path(source, url))

    async def put(self, source: str, page: Page) -> None:
        path = self._page_path(source, page.url)
        await asyncio.to_thread(_write_atomic, path, _encode_page(page))

    async def pages(self, source: str) -> AsyncIterator[Page]:
        directory = self.root / "raw" / _segment(source, "source")
        for path in await asyncio.to_thread(_list_pages, directory):
            page = await asyncio.to_thread(_read_page, path)
            if page is not None:
                yield page

    async def save_run(self, run: CrawlRun) -> None:
        path = self.root / "runs" / _segment(run.source, "source") / f"{_segment(run.id, 'run id')}.json"
        data = json.dumps(_run_record(run), indent=2).encode()
        await asyncio.to_thread(_write_atomic, path, data)
