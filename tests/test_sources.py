import httpx
import pytest

from wavelength.sources.base import Source
from wavelength.sources.demo import DemoSource
from wavelength.sources.loader import load_source, load_sources


async def test_demo_source_yields_events():
    async with httpx.AsyncClient() as client:
        events = [e async for e in DemoSource(delay=0).events(client)]
    assert len(events) == 4
    assert events[0].rooms["Main"][0] == "Ora Vance"
    assert "Juno Hale" in events[0].artists


def test_demo_implements_interface():
    assert isinstance(DemoSource(), Source)


def test_loader_defaults_to_demo(monkeypatch):
    monkeypatch.delenv("WAVELENGTH_SOURCES", raising=False)
    assert [s.name for s in load_sources()] == ["demo"]


def test_loader_reads_env(monkeypatch):
    monkeypatch.setenv("WAVELENGTH_SOURCES", "wavelength.sources.demo:DemoSource, wavelength.sources.demo:DemoSource")
    assert len(load_sources()) == 2


@pytest.mark.parametrize("spec", ["no_colon", "module:", ":Class"])
def test_loader_rejects_bad_specs(spec):
    with pytest.raises(ValueError):
        load_source(spec)


def test_loader_rejects_non_sources():
    with pytest.raises(TypeError):
        load_source("wavelength.models:Event")
