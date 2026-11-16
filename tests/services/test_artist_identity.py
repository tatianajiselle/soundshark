import pytest
from hypothesis import given
from hypothesis import strategies as st

from soundshark.services import group_by_matching_key, matching_key, split_lineup_slot, suggest_merges


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Säule Fan", "Saule Fan"),
        ("ORA VANCE", "ora vance"),
        ("  Mirek   Sol ", "Mirek Sol"),
        ("Tamsin’s Rook", "Tamsin's Rook"),
        ("Dax–Ferro", "Dax-Ferro"),
        ("“Juno Hale”", "Juno Hale"),
    ],
)
def test_normalize_equal_keys(a, b):
    assert matching_key(a) == matching_key(b)


def test_normalize_keeps_all_punctuation_names():
    assert matching_key("!!!") == "!!!"


@pytest.mark.parametrize("sep", ["b2b", "B2B", "b3b", "vs", "vs.", "VS"])
def test_split_slot_separators(sep):
    slot = split_lineup_slot(f"Ora Vance {sep} Mirek Sol")
    assert slot.acts == ["Ora Vance", "Mirek Sol"]
    assert slot.is_b2b


def test_split_slot_three_acts():
    assert split_lineup_slot("Ora Vance b2b Mirek Sol B2B Juno Hale").acts == [
        "Ora Vance",
        "Mirek Sol",
        "Juno Hale",
    ]


@pytest.mark.parametrize("raw", ["Ora Vance & Mirek Sol", "Ora Vance and Mirek Sol"])
def test_split_slot_ampersand_is_one_act(raw):
    slot = split_lineup_slot(raw)
    assert slot.acts == [raw]
    assert not slot.is_b2b


def test_split_slot_does_not_split_inside_words():
    assert split_lineup_slot("Vsevolod Rubb2bin").acts == ["Vsevolod Rubb2bin"]


@pytest.mark.parametrize(
    ("raw", "act", "tags"),
    [
        ("Petra Ilse (live)", "Petra Ilse", ["live"]),
        ("Petra Ilse live", "Petra Ilse", ["live"]),
        ("Petra Ilse (Hybrid)", "Petra Ilse", ["hybrid"]),
        ("Petra Ilse (DJ Set)", "Petra Ilse", ["dj set"]),
        ("Petra Ilse (dj)", "Petra Ilse", ["dj"]),
        ("Petra Ilse (Live) (A/V)", "Petra Ilse", ["live", "a/v"]),
        ("Petra Ilse (Lakeport)", "Petra Ilse (Lakeport)", []),
        ("Live", "Live", []),
    ],
)
def test_split_slot_tags(raw, act, tags):
    slot = split_lineup_slot(raw)
    assert slot.acts == [act]
    assert slot.tags == tags


def test_split_slot_tags_from_every_act_deduped():
    slot = split_lineup_slot("Ora Vance (live) b2b Mirek Sol (live)")
    assert slot.acts == ["Ora Vance", "Mirek Sol"]
    assert slot.tags == ["live"]


def test_group_exact_merges_by_key():
    groups = group_by_matching_key(["Säule Fan", "saule fan", "Ora Vance", "Säule Fan"])
    assert groups == {"saule fan": ["Säule Fan", "saule fan"], "ora vance": ["Ora Vance"]}


def test_suggest_merges_alter_egos_are_suggested_not_merged():
    names = ["DJ Tamsin", "DJ Tamsin 313", "dj tamsin", "Mirek Sol"]
    assert len(group_by_matching_key(names)) == 3
    [suggestion] = suggest_merges(names)
    assert {suggestion.name_a, suggestion.name_b} == {"DJ Tamsin", "DJ Tamsin 313"}
    assert suggestion.score >= 90


def test_suggest_merges_ignores_unrelated_names():
    assert suggest_merges(["Ora Vance", "Mirek Sol", "Juno Hale"]) == []


@given(st.text())
def test_normalize_is_idempotent(name):
    assert matching_key(matching_key(name)) == matching_key(name)


_WORD = st.text(alphabet="abcdefghijklmnopqrstuvwxyzäöü&'", min_size=1, max_size=8).filter(
    lambda w: w.lower() not in {"live", "hybrid", "vs", "present", "presents"}
)
_ACT = st.lists(_WORD, min_size=1, max_size=3).map(" ".join)


@given(
    st.lists(_ACT, min_size=1, max_size=4),
    st.lists(st.sampled_from(["b2b", "B2B", "vs", "vs.", "b3b"]), min_size=3, max_size=3),
    st.lists(st.sampled_from(["", " (live)", " live", " (DJ Set)"]), min_size=4, max_size=4),
)
def test_split_slot_never_loses_act_text(acts, seps, tags):
    raw = acts[0] + tags[0]
    for i, act in enumerate(acts[1:]):
        raw += f" {seps[i]} {act}{tags[i + 1]}"
    assert split_lineup_slot(raw).acts == acts


@pytest.mark.parametrize(
    ("raw", "acts", "projects"),
    [
        ("Ora Vance presents Night Garden", ["Ora Vance"], ["Night Garden"]),
        ("Ora Vance Presents: Night Garden", ["Ora Vance"], ["Night Garden"]),
        ("Ora Vance & Juno Hale present Tidewater", ["Ora Vance & Juno Hale"], ["Tidewater"]),
        ("Ora Vance & Juno Hale present: Tidewater", ["Ora Vance & Juno Hale"], ["Tidewater"]),
        ("Ora Vance presents Night Garden b2b Mirek Sol", ["Ora Vance", "Mirek Sol"], ["Night Garden"]),
    ],
)
def test_presenting_a_project_credits_who_presents(raw, acts, projects):
    slot = split_lineup_slot(raw)
    assert slot.acts == acts
    assert slot.presented_projects == projects


def test_tags_come_off_before_the_project():
    slot = split_lineup_slot("Ora Vance presents Night Garden (live)")
    assert (slot.acts, slot.presented_projects, slot.tags) == (["Ora Vance"], ["Night Garden"], ["live"])


@pytest.mark.parametrize("raw", ["The Harbour Present", "The Presents", "Presents of Mind"])
def test_present_inside_a_name_is_not_split(raw):
    slot = split_lineup_slot(raw)
    assert slot.acts == [raw]
    assert slot.presented_projects == []
