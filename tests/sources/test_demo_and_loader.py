import httpx
import pytest

from soundshark.interfaces import Source
from soundshark.services import crawl
from soundshark.sources import DemoSource, load_configured_sources, load_source_from_spec


async def test_demo_source_crawls_its_offline_site():
    source = DemoSource(seconds_between_requests=0)
    async with httpx.AsyncClient(transport=source.http_transport) as http_client:
        result = await crawl(source, http_client)
    events = sorted(result.events, key=lambda event: event.starts_at)
    assert [event.source_id for event in events] == ["d1", "d2", "d3", "d4"]
    assert events[0].rooms["Main"][0] == "Ora Vance"
    assert "Juno Hale" in events[0].artists
    assert result.run.pages_fetched == 3


def test_demo_source_implements_the_source_interface():
    assert isinstance(DemoSource(), Source)


def test_loader_defaults_to_the_demo_source(monkeypatch):
    monkeypatch.delenv("SOUNDSHARK_SOURCES", raising=False)
    assert [source.name for source in load_configured_sources()] == ["demo"]


def test_loader_reads_specs_from_the_environment(monkeypatch):
    monkeypatch.setenv(
        "SOUNDSHARK_SOURCES", "soundshark.sources.demo:DemoSource, soundshark.sources.demo:DemoSource"
    )
    assert len(load_configured_sources()) == 2


@pytest.mark.parametrize("bad_spec", ["no_colon", "module:", ":Class"])
def test_loader_rejects_malformed_specs(bad_spec):
    with pytest.raises(ValueError):
        load_source_from_spec(bad_spec)


def test_loader_rejects_classes_that_are_not_sources():
    with pytest.raises(TypeError):
        load_source_from_spec("soundshark.models:Event")
