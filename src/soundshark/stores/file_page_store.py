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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from soundshark.models import CrawlRun, Page, StoredPageVersion

_SAFE_PATH_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_PAGE_FILE_SUFFIX = ".json.gz"
_HASH_CHARS_IN_FILE_NAME = 16


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


def _version_file_name(page: Page) -> str:
    fetched = page.fetched_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{fetched}-{page.content_sha256[:_HASH_CHARS_IN_FILE_NAME]}{_PAGE_FILE_SUFFIX}"


def _content_hash_prefix(version_file: Path) -> str:
    return version_file.name.removesuffix(_PAGE_FILE_SUFFIX).rsplit("-", 1)[-1]


def _page_to_gzipped_json(page: Page) -> bytes:
    record = {
        "url": page.url,
        "status": page.status,
        "content_type": page.content_type,
        "encoding": page.encoding,
        "fetched_at": page.fetched_at.isoformat(),
        "crawl_run_id": page.crawl_run_id,
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
        crawl_run_id=record.get("crawl_run_id"),
    )


def _versions_oldest_first(url_directory: Path) -> list[Path]:
    if not url_directory.is_dir():
        return []
    return sorted(
        p
        for p in url_directory.iterdir()
        if p.name.endswith(_PAGE_FILE_SUFFIX) and not p.name.startswith(".")
    )


def _url_directories(source_directory: Path) -> list[Path]:
    if not source_directory.is_dir():
        return []
    return sorted(p for p in source_directory.iterdir() if p.is_dir())


def _read_latest_version(url_directory: Path) -> Page | None:
    versions = _versions_oldest_first(url_directory)
    return _page_from_gzipped_json(versions[-1].read_bytes()) if versions else None


def _save_version(url_directory: Path, page: Page) -> None:
    versions = _versions_oldest_first(url_directory)
    new_version = url_directory / _version_file_name(page)
    _write_file_atomically(new_version, _page_to_gzipped_json(page))
    if not versions:
        return
    previous_latest = versions[-1]
    same_content = _content_hash_prefix(previous_latest) == _content_hash_prefix(new_version)
    if same_content and previous_latest != new_version:
        previous_latest.unlink()


def _run_from_json_file(path: Path) -> CrawlRun:
    record = json.loads(path.read_text())
    for key in ("started_at", "finished_at"):
        if record.get(key) is not None:
            record[key] = datetime.fromisoformat(record[key])
    return CrawlRun(**record)


def _run_files_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".json" and not p.name.startswith("."))


def _run_as_json_dict(run: CrawlRun) -> dict[str, Any]:
    record = dataclasses.asdict(run)
    for key, value in record.items():
        if isinstance(value, datetime):
            record[key] = value.isoformat()
    return record


class FilePageStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _source_directory(self, source_name: str) -> Path:
        return self.root / "raw" / _require_safe_path_segment(source_name, "source name")

    def _url_directory(self, source_name: str, url: str) -> Path:
        return self._source_directory(source_name) / hashlib.sha256(url.encode()).hexdigest()

    async def load_page(self, source_name: str, url: str) -> Page | None:
        return await asyncio.to_thread(_read_latest_version, self._url_directory(source_name, url))

    async def save_page(self, source_name: str, page: Page) -> None:
        await asyncio.to_thread(_save_version, self._url_directory(source_name, page.url), page)

    async def iter_pages(self, source_name: str) -> AsyncIterator[Page]:
        for url_directory in await asyncio.to_thread(_url_directories, self._source_directory(source_name)):
            page = await asyncio.to_thread(_read_latest_version, url_directory)
            if page is not None:
                yield page

    async def iter_page_versions(self, source_name: str) -> AsyncIterator[StoredPageVersion]:
        for url_directory in await asyncio.to_thread(_url_directories, self._source_directory(source_name)):
            versions = await asyncio.to_thread(_versions_oldest_first, url_directory)
            for position, version_file in enumerate(versions):
                page = _page_from_gzipped_json(await asyncio.to_thread(version_file.read_bytes))
                yield StoredPageVersion(
                    page=page,
                    storage_path=version_file.relative_to(self.root).as_posix(),
                    is_latest=position == len(versions) - 1,
                )

    async def save_run(self, run: CrawlRun) -> None:
        source_dir = _require_safe_path_segment(run.source_name, "source name")
        run_file = f"{_require_safe_path_segment(run.id, 'run id')}.json"
        run_json = json.dumps(_run_as_json_dict(run), indent=2).encode()
        await asyncio.to_thread(_write_file_atomically, self.root / "runs" / source_dir / run_file, run_json)

    async def iter_runs(self, source_name: str) -> AsyncIterator[CrawlRun]:
        directory = self.root / "runs" / _require_safe_path_segment(source_name, "source name")
        for path in await asyncio.to_thread(_run_files_in, directory):
            yield await asyncio.to_thread(_run_from_json_file, path)
