from datetime import datetime

import httpx
import pytest

from soundshark.crawler import crawl
from soundshark.models import Event
from soundshark.sources.base import Source
from soundshark.sources.demo import DemoSource
from soundshark.sources.loader import load_source, load_sources


async def test_demo_crawls_its_fake_site():
    source = DemoSource(min_interval=0)
    async with httpx.AsyncClient(transport=source.transport) as client:
        result = await crawl(source, client)
    events = sorted(result.events, key=lambda e: e.starts_at)
    assert [e.source_id for e in events] == ["d1", "d2", "d3", "d4"]
    assert events[0].rooms["Main"][0] == "Ora Vance"
    assert "Juno Hale" in events[0].artists
    assert result.run.fetched == 3


def test_demo_implements_interface():
    assert isinstance(DemoSource(), Source)


def test_event_requires_timezone():
    with pytest.raises(ValueError):
        Event(source="x", source_id="1", starts_at=datetime(2026, 1, 1), venue="V", city="C")


def test_loader_defaults_to_demo(monkeypatch):
    monkeypatch.delenv("SOUNDSHARK_SOURCES", raising=False)
    assert [s.name for s in load_sources()] == ["demo"]


def test_loader_reads_env(monkeypatch):
    monkeypatch.setenv(
        "SOUNDSHARK_SOURCES", "soundshark.sources.demo:DemoSource, soundshark.sources.demo:DemoSource"
    )
    assert len(load_sources()) == 2


@pytest.mark.parametrize("spec", ["no_colon", "module:", ":Class"])
def test_loader_rejects_bad_specs(spec):
    with pytest.raises(ValueError):
        load_source(spec)


def test_loader_rejects_non_sources():
    with pytest.raises(TypeError):
        load_source("soundshark.models:Event")
