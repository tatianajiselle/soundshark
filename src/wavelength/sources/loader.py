"""Load sources named in config, so the public repo never imports a real source.

WAVELENGTH_SOURCES is a comma-separated list of "module.path:ClassName" specs.
It defaults to the demo source. Put real specs in your gitignored .env.
"""

import importlib
import os

from wavelength.sources.base import Source

DEFAULT_SOURCES = "wavelength.sources.demo:DemoSource"


def load_source(spec: str) -> Source:
    module_path, sep, class_name = spec.strip().partition(":")
    if not sep or not module_path or not class_name:
        raise ValueError(f"bad source spec {spec!r}; expected 'module.path:ClassName'")
    cls = getattr(importlib.import_module(module_path), class_name)
    source = cls()
    if not isinstance(source, Source):
        raise TypeError(f"{spec} doesn't implement the Source interface")
    return source


def load_sources(specs: str | None = None) -> list[Source]:
    specs = specs if specs is not None else os.environ.get("WAVELENGTH_SOURCES", DEFAULT_SOURCES)
    return [load_source(s) for s in specs.split(",") if s.strip()]
