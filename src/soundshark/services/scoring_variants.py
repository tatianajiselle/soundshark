import dataclasses
import typing
from dataclasses import dataclass

from soundshark.models.graph_scoring import GraphScoring

type SettingValue = int | float


class ScoringSpecError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ScoringVariant:
    name: str
    overrides: dict[str, SettingValue]

    @property
    def scoring(self) -> GraphScoring:
        return dataclasses.replace(GraphScoring(), **self.overrides)


DEFAULT_VARIANT_SPECS = (
    "floor-1:room_profile_floor=1.0",
    "floor-0:room_profile_floor=0.0",
    "half-life-5:recency_half_life_years=5.0",
)


def setting_types() -> dict[str, type]:
    hints = typing.get_type_hints(GraphScoring)
    return {f.name: hints[f.name] for f in dataclasses.fields(GraphScoring)}


def parse_setting(text: str) -> tuple[str, SettingValue]:
    field_name, equals, raw_value = text.partition("=")
    field_name, raw_value = field_name.strip(), raw_value.strip()
    if not equals or not field_name or not raw_value:
        raise ScoringSpecError(f"expected field=value, got {text!r}")
    types = setting_types()
    if field_name not in types:
        raise ScoringSpecError(f"unknown setting {field_name!r}; known settings: {', '.join(types)}")
    field_type = types[field_name]
    try:
        return field_name, field_type(raw_value)
    except ValueError:
        raise ScoringSpecError(f"{field_name}={raw_value!r} is not a valid {field_type.__name__}") from None


def parse_settings(texts: typing.Iterable[str]) -> dict[str, SettingValue]:
    overrides: dict[str, SettingValue] = {}
    for text in texts:
        field_name, value = parse_setting(text)
        if field_name in overrides:
            raise ScoringSpecError(f"{field_name} is set twice")
        overrides[field_name] = value
    return overrides


def parse_variant(spec: str) -> ScoringVariant:
    name, colon, settings = spec.partition(":")
    name = name.strip()
    if not colon or not name or not settings.strip():
        raise ScoringSpecError(f"expected name:field=value[,field=value...], got {spec!r}")
    return ScoringVariant(name, parse_settings(settings.split(",")))


def default_variants() -> list[ScoringVariant]:
    return [parse_variant(spec) for spec in DEFAULT_VARIANT_SPECS]


def describe_overrides(overrides: dict[str, SettingValue]) -> str:
    return ", ".join(f"{field_name}={value}" for field_name, value in overrides.items())
