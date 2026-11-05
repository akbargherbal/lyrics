"""HTTP sources: iTunes catalog and LRCLIB lyrics, with caching and rate limits."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from .quality import key_is_safe, latin_key, normalize_arabic, normalize_latin

LOG = logging.getLogger(__name__)

ITUNES_URL = "https://itunes.apple.com/search"
LRCLIB_GET = "https://lrclib.net/api/get"
LRCLIB_SEARCH = "https://lrclib.net/api/search"


class HttpClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        min_interval: float = 0.75,
        user_agent: str = "ArabicLyricsDB/1.0 (personal research)",
        timeout: int = 30,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.timeout = timeout
        self.last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request = time.monotonic()

    def get_json(self, url: str, params: dict | None = None, *, force: bool = False):
        if params:
            url = f"{url}?{urlencode(params)}"
        cache_path = self._cache_path(url)
        if not force and cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached, dict) and cached.get("__status__") == 404:
                    return None
                return cached
            except Exception:
                pass

        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                self._throttle()
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 404:
                    cache_path.write_text(json.dumps({"__status__": 404}), encoding="utf-8")
                    return None
                if response.status_code == 429:
                    retry = response.headers.get("Retry-After", "5")
                    wait = float(retry) if retry.replace(".", "", 1).isdigit() else 5.0
                    LOG.warning("429 rate limit, waiting %.1fs", wait)
                    time.sleep(wait)
                    continue
                if response.status_code >= 500:
                    raise RuntimeError(f"HTTP {response.status_code}")
                response.raise_for_status()
                data = response.json()
                cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(min(8.0, 1.5 * attempt))
        LOG.warning("request failed: %s (%s)", url, last_error)
        return None


def _alias_norms(artist: dict) -> list[str]:
    values = [artist.get("name_en"), artist.get("name_ar"), *(artist.get("aliases") or [])]
    norms = []
    for value in values:
        if not value:
            continue
        norms.append(normalize_latin(value))
        norms.append(normalize_arabic(value))
    return [norm for norm in dict.fromkeys(norms) if norm]


def _alias_keys(artist: dict) -> list[str]:
    values = [artist.get("name_en"), *(artist.get("aliases") or [])]
    keys = []
    for value in values:
        if not value:
            continue
        key = latin_key(value)
        if key_is_safe(key):
            keys.append(key)
    return list(dict.fromkeys(keys))


def _artist_matches(candidate: str | None, artist: dict) -> bool:
    if not candidate:
        return False
    cand_latin = normalize_latin(candidate)
    cand_arabic = normalize_arabic(candidate)
    for alias in _alias_norms(artist):
        if alias and (alias in cand_latin or alias in cand_arabic or cand_latin in alias or cand_arabic in alias):
            return True

    cand_key = latin_key(candidate)
    if cand_key and key_is_safe(cand_key):
        for alias_key in _alias_keys(artist):
            if alias_key in cand_key or cand_key in alias_key:
                return True
    return False


def _duration_bucket(duration: int | None) -> int | None:
    if not duration:
        return None
    return int(round(duration / 5.0) * 5)


def itunes_catalog(client: HttpClient, artist: dict, *, country: str = "US", limit: int = 200) -> list[dict]:
    """Fetch up to 200 songs for an artist from the public iTunes Search API."""
    terms = [artist.get("name_en"), artist.get("name_ar")]
    results: list[dict] = []
    for term in [value for value in terms if value]:
        data = client.get_json(
            ITUNES_URL,
            {"term": term, "entity": "song", "limit": limit, "country": country},
        )
        if not data:
            continue
        for item in data.get("results", []):
            if not _artist_matches(item.get("artistName"), artist):
                continue
            title = item.get("trackName")
            if not title:
                continue
            duration_ms = item.get("trackTimeMillis")
            duration = int(round(duration_ms / 1000)) if duration_ms else None
            results.append(
                {
                    "title": title,
                    "artist": item.get("artistName") or artist.get("name_en"),
                    "album": item.get("collectionName"),
                    "duration": duration,
                    "track_id": str(item.get("trackId") or ""),
                    "isrc": item.get("isrc"),
                    "source": "itunes",
                }
            )
        if results:
            break

    dedup: dict[str, dict] = {}
    for item in results:
        key = f"{normalize_arabic(item['title'])}|{_duration_bucket(item['duration'])}"
        dedup.setdefault(key, item)
    return list(dedup.values())


def _score_candidate(record: dict, title: str, artist: dict, duration: int | None) -> int:
    rec_title = normalize_arabic(record.get("trackName") or record.get("name") or "")
    want_title = normalize_arabic(title)
    if not rec_title or not want_title:
        return -999
    if rec_title == want_title:
        score = 10
    elif want_title in rec_title or rec_title in want_title:
        score = 6
    else:
        return -999

    rec_artist = f"{record.get('artistName') or ''} {record.get('trackName') or ''}"
    if _artist_matches(rec_artist, artist):
        score += 5

    rec_duration = record.get("duration")
    if duration and rec_duration:
        diff = abs(duration - float(rec_duration))
        if diff <= 2:
            score += 5
        elif diff <= 5:
            score += 3
        elif diff <= 10:
            score += 1
        elif diff <= 30:
            score -= 2
        else:
            score -= 6
    return score


def fetch_lrclib(client: HttpClient, artist: dict, song: dict) -> dict | None:
    """Return {'record': ..., 'score': ..., 'method': ...} or None."""
    title = song.get("title") or ""
    album = song.get("album")
    duration = song.get("duration")
    artist_names = [value for value in [artist.get("name_en"), artist.get("name_ar"), *(artist.get("aliases") or [])] if value]

    for name in artist_names:
        params = {"artist_name": name, "track_name": title}
        if album:
            params["album_name"] = album
        if duration:
            params["duration"] = int(duration)
        record = client.get_json(LRCLIB_GET, params)
        if record and record.get("plainLyrics") is not None:
            score = _score_candidate(record, title, artist, duration)
            if score >= 10:
                return {"record": record, "score": score, "method": "get"}

    candidates: dict[int, dict] = {}
    for name in artist_names[:3]:
        data = client.get_json(LRCLIB_SEARCH, {"artist_name": name, "track_name": title})
        if isinstance(data, list):
            for record in data:
                if record.get("id") is not None:
                    candidates[record["id"]] = record

    best = None
    best_score = -999
    for record in candidates.values():
        score = _score_candidate(record, title, artist, duration)
        if score > best_score:
            best_score = score
            best = record
    if best and best_score >= 12:
        return {"record": best, "score": best_score, "method": "search"}
    return None
