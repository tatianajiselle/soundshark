"""Identity rules, on fictional names only."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from soundshark.identity import group_exact, normalize, split_slot, suggest_merges


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
    assert normalize(a) == normalize(b)


def test_normalize_keeps_all_punctuation_names():
    assert normalize("!!!") == "!!!"


@pytest.mark.parametrize("sep", ["b2b", "B2B", "b3b", "vs", "vs.", "VS"])
def test_split_slot_separators(sep):
    slot = split_slot(f"Ora Vance {sep} Mirek Sol")
    assert slot.acts == ["Ora Vance", "Mirek Sol"]
    assert slot.is_b2b


def test_split_slot_three_acts():
    assert split_slot("Ora Vance b2b Mirek Sol B2B Juno Hale").acts == ["Ora Vance", "Mirek Sol", "Juno Hale"]


@pytest.mark.parametrize("raw", ["Ora Vance & Mirek Sol", "Ora Vance and Mirek Sol"])
def test_split_slot_ampersand_is_one_act(raw):
    slot = split_slot(raw)
    assert slot.acts == [raw]
    assert not slot.is_b2b


def test_split_slot_does_not_split_inside_words():
    assert split_slot("Vsevolod Rubb2bin").acts == ["Vsevolod Rubb2bin"]


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
    slot = split_slot(raw)
    assert slot.acts == [act]
    assert slot.tags == tags


def test_split_slot_tags_from_every_act_deduped():
    slot = split_slot("Ora Vance (live) b2b Mirek Sol (live)")
    assert slot.acts == ["Ora Vance", "Mirek Sol"]
    assert slot.tags == ["live"]


def test_group_exact_merges_by_key():
    groups = group_exact(["Säule Fan", "saule fan", "Ora Vance", "Säule Fan"])
    assert groups == {"saule fan": ["Säule Fan", "saule fan"], "ora vance": ["Ora Vance"]}


def test_suggest_merges_alter_egos_are_suggested_not_merged():
    names = ["DJ Tamsin", "DJ Tamsin 313", "dj tamsin", "Mirek Sol"]
    assert len(group_exact(names)) == 3
    [suggestion] = suggest_merges(names)
    assert {suggestion.a, suggestion.b} == {"DJ Tamsin", "DJ Tamsin 313"}
    assert suggestion.score >= 90


def test_suggest_merges_ignores_unrelated_names():
    assert suggest_merges(["Ora Vance", "Mirek Sol", "Juno Hale"]) == []


@given(st.text())
def test_normalize_is_idempotent(name):
    assert normalize(normalize(name)) == normalize(name)


_WORD = st.text(alphabet="abcdefghijklmnopqrstuvwxyzäöü&'", min_size=1, max_size=8).filter(
    lambda w: w.lower() not in {"live", "hybrid", "vs"}
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
    assert split_slot(raw).acts == acts
