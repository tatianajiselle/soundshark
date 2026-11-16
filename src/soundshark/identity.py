"""Who is who: matching keys for artist names, splitting lineup slots into acts, merge suggestions.

Names that share a normalized key are the same artist. Names that only look alike become
suggestions for a person to approve; nothing fuzzy is ever merged automatically.
"""

import re
import string
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

_QUOTES = str.maketrans({c: "'" for c in "‘’‚‛′`´"} | {c: '"' for c in "“”„‟″"})
_DASHES = str.maketrans({c: "-" for c in "‐‑‒–—―−"})
_EDGES = string.punctuation + string.whitespace

_SEPARATOR = re.compile(r"\s+(?:b[2-9]b|vs\.?)\s+", re.IGNORECASE)
_TAG_WORDS = ("live set", "dj set", "all night long", "hybrid", "live", "dj", "a/v")
_TAG = re.compile(
    r"\s*(?:\((?P<paren>" + "|".join(map(re.escape, _TAG_WORDS)) + r")\)|\s(?P<bare>live|hybrid))\s*$",
    re.IGNORECASE,
)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize(name: str) -> str:
    """The matching key for a name. Display names are never changed, only compared through this."""
    key = _fold(_fold(name).casefold()).translate(_QUOTES).translate(_DASHES)
    key = " ".join(key.split())
    return key.strip(_EDGES) or key


@dataclass(slots=True)
class Slot:
    raw: str
    acts: list[str] = field(default_factory=list)
    is_b2b: bool = False
    tags: list[str] = field(default_factory=list)


def _strip_tags(act: str) -> tuple[str, list[str]]:
    tags: list[str] = []
    while (match := _TAG.search(act)) and match.start() > 0:
        tags.insert(0, (match["paren"] or match["bare"]).lower())
        act = act[: match.start()]
    return act, tags


def split_slot(raw: str) -> Slot:
    """One lineup entry into its acts. "A b2b B" and "A vs B" are two acts; "A & B" stays one act."""
    slot = Slot(raw=raw)
    for part in _SEPARATOR.split(" ".join(raw.split())):
        act, tags = _strip_tags(part.strip())
        if act := act.strip():
            slot.acts.append(act)
        slot.tags.extend(t for t in tags if t not in slot.tags)
    slot.is_b2b = len(slot.acts) > 1
    return slot


def group_exact(names: Iterable[str]) -> dict[str, list[str]]:
    """Names grouped by matching key, in first-seen order. Each group is one artist."""
    groups: dict[str, list[str]] = {}
    for name in names:
        group = groups.setdefault(normalize(name), [])
        if name not in group:
            group.append(name)
    return groups


@dataclass(frozen=True, slots=True)
class Suggestion:
    a: str
    b: str
    score: float


def suggest_merges(names: Iterable[str], threshold: float = 90) -> list[Suggestion]:
    """Pairs of different artists whose names look alike, best first. Never applied automatically."""
    groups = group_exact(names)
    keys = list(groups)
    suggestions = []
    for i, key in enumerate(keys):
        for _, score, j in process.extract(
            key, keys[i + 1 :], scorer=fuzz.WRatio, score_cutoff=threshold, limit=None
        ):
            suggestions.append(Suggestion(groups[key][0], groups[keys[i + 1 + j]][0], score))
    return sorted(suggestions, key=lambda s: (-s.score, s.a, s.b))
