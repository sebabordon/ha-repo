"""Fuzzy title+artist matching between Spotify and Apple Music track records.

No ISRC is available from Music.app's AppleScript interface, so matching
falls back to normalized title/primary-artist comparison.
"""
import re
import unicodedata
from difflib import SequenceMatcher

_NOISE_PATTERNS = [
    r"\(feat\.[^)]*\)", r"\[feat\.[^)]*\]",
    r"\(with [^)]*\)",
    r"\(remaster(ed)?[^)]*\)", r"-\s*remaster(ed)?[^-]*$",
    r"\(live[^)]*\)", r"-\s*live[^-]*$",
    r"\(deluxe[^)]*\)", r"\(bonus track\)",
    r"\(radio edit\)", r"\(single version\)", r"\(album version\)",
]

MATCH_THRESHOLD = 0.87


def _strip_noise(text: str) -> str:
    for pattern in _NOISE_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return text


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = _strip_noise(text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def primary_artist(artist: str) -> str:
    return re.split(r"[,&]|feat\.|ft\.", artist, flags=re.IGNORECASE)[0].strip()


def artist_tokens(artist: str) -> list[str]:
    parts = re.split(r"[,&/]|feat\.|ft\.", artist, flags=re.IGNORECASE)
    return [_normalize(p) for p in parts if _normalize(p)]


def norm_key(name: str, artist: str) -> str:
    return f"{_normalize(name)}::{_normalize(primary_artist(artist))}"


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def artist_similarity(a: str, b: str) -> float:
    """Best pairwise similarity across every listed artist on each side.

    Spotify and Apple Music don't agree on artist order — classical tracks
    in particular list composers first on one service and the performer
    first on the other — so comparing only the first artist misses real
    matches. Checking every token against every token catches those.
    """
    a_tokens = artist_tokens(a)
    b_tokens = artist_tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    return max(similarity(x, y) for x in a_tokens for y in b_tokens)


def score_candidate(name: str, artist: str, cand: dict) -> float:
    name_score = similarity(_normalize(name), _normalize(cand["name"]))
    artist_score = artist_similarity(artist, cand["artist"])
    return 0.7 * name_score + 0.3 * artist_score


def best_candidate(name: str, artist: str, candidates: list[dict]):
    """Returns (candidate, score) for the closest candidate regardless of
    threshold, or (None, 0.0) if candidates is empty. Meant for
    human-reviewed matching — score is not gated by MATCH_THRESHOLD.
    """
    best = None
    best_score = 0.0
    for cand in candidates:
        score = score_candidate(name, artist, cand)
        if score > best_score:
            best_score = score
            best = cand
    return best, best_score


def best_match(name: str, artist: str, candidates: list[dict]):
    """candidates: list of {"name":..., "artist":..., ...}. Returns best candidate dict or None."""
    cand, score = best_candidate(name, artist, candidates)
    if cand is not None and score >= MATCH_THRESHOLD:
        return cand
    return None
