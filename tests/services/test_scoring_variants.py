import pytest

from soundshark.models.graph_scoring import GraphScoring
from soundshark.services.scoring_variants import (
    ScoringSpecError,
    default_variants,
    describe_overrides,
    parse_settings,
    parse_variant,
)


def test_a_variant_overrides_named_settings_with_their_own_types():
    variant = parse_variant("tight:room_profile_floor=1, related_per_artist=20")
    assert variant.name == "tight"
    assert variant.overrides == {"room_profile_floor": 1.0, "related_per_artist": 20}
    assert isinstance(variant.overrides["room_profile_floor"], float)
    assert isinstance(variant.overrides["related_per_artist"], int)
    assert variant.scoring == GraphScoring(room_profile_floor=1.0, related_per_artist=20)
    assert describe_overrides(variant.overrides) == "room_profile_floor=1.0, related_per_artist=20"


def test_an_unknown_setting_is_refused_with_the_known_ones():
    with pytest.raises(ScoringSpecError, match="unknown setting 'room_floor'.*room_profile_floor"):
        parse_variant("typo:room_floor=1")


@pytest.mark.parametrize(
    "spec",
    ["count:related_per_artist=1.5", "word:b2b_weight=lots", "empty:b2b_weight=", "no-settings:", "floor-1"],
)
def test_bad_values_and_shapes_are_refused(spec):
    with pytest.raises(ScoringSpecError):
        parse_variant(spec)


def test_a_bad_value_names_the_setting_and_its_type():
    with pytest.raises(ScoringSpecError, match="related_per_artist='1.5' is not a valid int"):
        parse_variant("count:related_per_artist=1.5")


def test_a_setting_given_twice_is_refused():
    with pytest.raises(ScoringSpecError, match="set twice"):
        parse_settings(["b2b_weight=2", "b2b_weight=3"])


def test_default_variants():
    assert [v.name for v in default_variants()] == ["floor-1", "floor-0", "half-life-5"]
    assert default_variants()[2].scoring.recency_half_life_years == 5.0
