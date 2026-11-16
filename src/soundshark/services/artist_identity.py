import re
import string
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

_CURLY_QUOTES_TO_STRAIGHT = str.maketrans({c: "'" for c in "‘’‚‛′`´"} | {c: '"' for c in "“”„‟″"})
_DASHES_TO_HYPHEN = str.maketrans({c: "-" for c in "‐‑‒–—―−"})
_EDGE_CHARACTERS = string.punctuation + string.whitespace

_B2B_SEPARATOR = re.compile(r"\s+(?:b[2-9]b|vs\.?)\s+", re.IGNORECASE)
_PRESENTED_PROJECT = re.compile(r"\s+presents?:?\s+(?P<project>\S.*)$", re.IGNORECASE)
_KNOWN_TAGS = ("live set", "dj set", "all night long", "hybrid", "live", "dj", "a/v")
_TRAILING_TAG = re.compile(
    r"\s*(?:\((?P<paren>" + "|".join(map(re.escape, _KNOWN_TAGS)) + r")\)|\s(?P<bare>live|hybrid))\s*$",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def matching_key(name: str) -> str:
    folded = _strip_accents(_strip_accents(name).casefold())
    unified = folded.translate(_CURLY_QUOTES_TO_STRAIGHT).translate(_DASHES_TO_HYPHEN)
    single_spaced = " ".join(unified.split())
    return single_spaced.strip(_EDGE_CHARACTERS) or single_spaced


@dataclass(slots=True)
class LineupSlot:
    raw_text: str
    acts: list[str] = field(default_factory=list)
    is_b2b: bool = False
    tags: list[str] = field(default_factory=list)
    presented_projects: list[str] = field(default_factory=list)


def _split_off_trailing_tags(act: str) -> tuple[str, list[str]]:
    tags: list[str] = []
    while (match := _TRAILING_TAG.search(act)) and match.start() > 0:
        tags.insert(0, (match["paren"] or match["bare"]).lower())
        act = act[: match.start()]
    return act, tags


def _split_off_presented_project(act: str) -> tuple[str, str | None]:
    match = _PRESENTED_PROJECT.search(act)
    if match is None or match.start() == 0:
        return act, None
    return act[: match.start()], match["project"].strip()


def split_lineup_slot(raw_text: str) -> LineupSlot:
    slot = LineupSlot(raw_text=raw_text)
    for part in _B2B_SEPARATOR.split(" ".join(raw_text.split())):
        act, tags = _split_off_trailing_tags(part.strip())
        act, project = _split_off_presented_project(act)
        if act := act.strip():
            slot.acts.append(act)
        if project:
            slot.presented_projects.append(project)
        slot.tags.extend(t for t in tags if t not in slot.tags)
    slot.is_b2b = len(slot.acts) > 1
    return slot


def group_by_matching_key(names: Iterable[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for name in names:
        group = groups.setdefault(matching_key(name), [])
        if name not in group:
            group.append(name)
    return groups


@dataclass(frozen=True, slots=True)
class MergeSuggestion:
    name_a: str
    name_b: str
    score: float


def suggest_merges(names: Iterable[str], min_score: float = 90) -> list[MergeSuggestion]:
    names_by_key = group_by_matching_key(names)
    keys = list(names_by_key)
    suggestions = []
    for position, key in enumerate(keys):
        later_keys = keys[position + 1 :]
        for _, score, index_in_later in process.extract(
            key, later_keys, scorer=fuzz.WRatio, score_cutoff=min_score, limit=None
        ):
            similar_key = later_keys[index_in_later]
            suggestions.append(MergeSuggestion(names_by_key[key][0], names_by_key[similar_key][0], score))
    return sorted(suggestions, key=lambda s: (-s.score, s.name_a, s.name_b))
