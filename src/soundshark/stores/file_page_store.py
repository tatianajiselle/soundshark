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

from soundshark.models import CrawlRun, Page

_SAFE_PATH_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_PAGE_FILE_SUFFIX = ".json.gz"


def _require_safe_path_segment(value: str, what_it_is: str) -> str:
    if not _SAFE_PATH_SEGMENT.fullmatch(value):
        raise ValueError(f"{what_it_is} {value!r} is not a safe path segment (letters, digits, _ and -)")
    return value


def _write_file_atomically(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _page_to_gzipped_json(page: Page) -> bytes:
    record = {
        "url": page.url,
        "status": page.status,
        "content_type": page.content_type,
        "encoding": page.encoding,
        "fetched_at": page.fetched_at.isoformat(),
        "body": base64.b64encode(page.body).decode("ascii"),
    }
    return gzip.compress(json.dumps(record).encode(), mtime=0)


def _page_from_gzipped_json(data: bytes) -> Page:
    record = json.loads(gzip.decompress(data))
    return Page(
        url=record["url"],
        status=record["status"],
        body=base64.b64decode(record["body"]),
        fetched_at=datetime.fromisoformat(record["fetched_at"]),
        content_type=record["content_type"],
        encoding=record["encoding"],
    )


def _read_page_file(path: Path) -> Page | None:
    try:
        return _page_from_gzipped_json(path.read_bytes())
    except FileNotFoundError:
        return None


def _page_files_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p for p in directory.iterdir() if p.name.endswith(_PAGE_FILE_SUFFIX) and not p.name.startswith(".")
    )


def _run_as_json_dict(run: CrawlRun) -> dict[str, Any]:
    record = dataclasses.asdict(run)
    for key, value in record.items():
        if isinstance(value, datetime):
            record[key] = value.isoformat()
    return record


class FilePageStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path_for_page(self, source_name: str, url: str) -> Path:
        source_dir = _require_safe_path_segment(source_name, "source name")
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return self.root / "raw" / source_dir / f"{url_hash}{_PAGE_FILE_SUFFIX}"

    async def load_page(self, source_name: str, url: str) -> Page | None:
        return await asyncio.to_thread(_read_page_file, self._path_for_page(source_name, url))

    async def save_page(self, source_name: str, page: Page) -> None:
        path = self._path_for_page(source_name, page.url)
        await asyncio.to_thread(_write_file_atomically, path, _page_to_gzipped_json(page))

    async def iter_pages(self, source_name: str) -> AsyncIterator[Page]:
        directory = self.root / "raw" / _require_safe_path_segment(source_name, "source name")
        for path in await asyncio.to_thread(_page_files_in, directory):
            page = await asyncio.to_thread(_read_page_file, path)
            if page is not None:
                yield page

    async def save_run(self, run: CrawlRun) -> None:
        source_dir = _require_safe_path_segment(run.source_name, "source name")
        run_file = f"{_require_safe_path_segment(run.id, 'run id')}.json"
        run_json = json.dumps(_run_as_json_dict(run), indent=2).encode()
        await asyncio.to_thread(_write_file_atomically, self.root / "runs" / source_dir / run_file, run_json)
