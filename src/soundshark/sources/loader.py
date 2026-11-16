import importlib
import os

from soundshark.interfaces import Source

SOURCES_ENV_VAR = "SOUNDSHARK_SOURCES"
DEFAULT_SOURCE_SPECS = "soundshark.sources.demo:DemoSource"


def load_source_from_spec(spec: str) -> Source:
    module_path, separator, class_name = spec.strip().partition(":")
    if not separator or not module_path or not class_name:
        raise ValueError(f"bad source spec {spec!r}; expected 'module.path:ClassName'")
    source_class = getattr(importlib.import_module(module_path), class_name)
    source = source_class()
    if not isinstance(source, Source):
        raise TypeError(f"{spec} doesn't implement the Source interface")
    return source


def load_configured_sources(specs: str | None = None) -> list[Source]:
    if specs is None:
        specs = os.environ.get(SOURCES_ENV_VAR, DEFAULT_SOURCE_SPECS)
    return [load_source_from_spec(spec) for spec in specs.split(",") if spec.strip()]
