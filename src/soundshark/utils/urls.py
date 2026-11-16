from urllib.parse import urldefrag, urlsplit


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def without_fragment(url: str) -> str:
    return urldefrag(url).url


def is_web_url(url: str) -> bool:
    return urlsplit(url).scheme in ("http", "https")
