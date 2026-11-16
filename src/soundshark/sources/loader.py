import importlib
import os

from soundshark.sources.base import Source

DEFAULT_SOURCES = "soundshark.sources.demo:DemoSource"


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
    specs = specs if specs is not None else os.environ.get("SOUNDSHARK_SOURCES", DEFAULT_SOURCES)
    return [load_source(s) for s in specs.split(",") if s.strip()]
