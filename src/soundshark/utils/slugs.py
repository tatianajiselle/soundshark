import hashlib
import re
import unicodedata

_NOT_LETTER_OR_DIGIT = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    ascii_only = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _NOT_LETTER_OR_DIGIT.sub("-", ascii_only.lower()).strip("-")


def slug_with_short_hash(text: str) -> str:
    short_hash = hashlib.sha256(text.encode()).hexdigest()[:6]
    return f"{slugify(text) or 'x'}-{short_hash}"
