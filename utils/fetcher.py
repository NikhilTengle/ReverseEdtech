"""
fetcher.py
──────────
yt-dlp wrapper for YouTube search and metadata extraction.

Why yt-dlp over youtube-search-python:
  - Returns full video description (needed for timestamp parsing)
  - Returns native YouTube chapters when creators set them
  - Returns view count, upload date, duration in seconds
  - No paid API key required

Chapter extraction strategy:
  1. Use native YouTube chapters if present (most reliable)
  2. Fall back to regex parsing of video description
"""

import re
from datetime import datetime
import yt_dlp

# Base yt-dlp options — extended at call time with optional cookie config
_BASE_OPTS = {
    "quiet":       True,
    "no_warnings": True,
}


def _ydl_opts(cookies_from_browser: str | None = None) -> dict:
    """Build yt-dlp options, optionally injecting browser cookies."""
    opts = dict(_BASE_OPTS)
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser, None, None, None)
    return opts

# Matches timestamps in descriptions:
#   00:00 Introduction
#   0:00:00 - Power Query
#   (05:12) DAX Basics
#   1:02:45 | Time Intelligence
TIMESTAMP_RE = re.compile(
    r"(?m)^\s*\(?(\d{1,2}:\d{2}(?::\d{2})?)\)?\s*[-–—|:.]?\s*(.+)$"
)

# Chapter titles that carry no structural information
GENERIC_CHAPTER_WORDS = {
    "introduction", "intro", "part", "section", "chapter",
    "outro", "end", "beginning", "start", "overview",
    "conclusion", "thanks", "subscribe", "like", "comment",
}


# ── Search ────────────────────────────────────────────────────────────────────

def search_videos(query: str, max_results: int = 20,
                  cookies_from_browser: str | None = None) -> list[dict]:
    """
    Search YouTube and return a list of raw yt-dlp info dicts.
    Each dict contains full metadata: description, chapters, view_count, etc.
    Pass cookies_from_browser='chrome' (or 'firefox') to use browser session
    and avoid YouTube IP rate-limiting.
    """
    search_url = f"ytsearch{max_results}:{query}"
    try:
        with yt_dlp.YoutubeDL(_ydl_opts(cookies_from_browser)) as ydl:
            info = ydl.extract_info(search_url, download=False)
            return info.get("entries") or []
    except Exception as exc:
        print(f"[!] Search error: {exc}")
        return []


# ── Chapter parsing ───────────────────────────────────────────────────────────

def _format_native_chapters(raw_chapters: list[dict]) -> list[dict]:
    """
    Convert yt-dlp's native chapter format to ours.
    yt-dlp gives: {"title": "...", "start_time": 0.0, "end_time": 120.5}
    """
    chapters = []
    for ch in raw_chapters:
        start = int(ch.get("start_time", 0))
        h = start // 3600
        m = (start % 3600) // 60
        s = start % 60
        ts = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
        chapters.append({
            "timestamp": ts,
            "title":     ch.get("title", "").strip(),
        })
    return chapters


def _parse_description_timestamps(description: str) -> list[dict]:
    """
    Regex-extract timestamps from video descriptions.
    Deduplicates by timestamp to avoid double entries.
    """
    if not description:
        return []

    chapters = []
    seen_ts  = set()

    for ts, topic in TIMESTAMP_RE.findall(description):
        topic = topic.strip().rstrip(".,;")[:120]
        if ts not in seen_ts and len(topic) > 1:
            chapters.append({"timestamp": ts, "title": topic})
            seen_ts.add(ts)

    return chapters


def parse_chapters(raw: dict) -> list[dict]:
    """
    Extract structured chapters from a video.
    Prefers native YouTube chapters; falls back to description parsing.
    """
    native = raw.get("chapters") or []
    if native:
        return _format_native_chapters(native)
    return _parse_description_timestamps(raw.get("description") or "")


def chapter_specificity(chapters: list[dict]) -> float:
    """
    Fraction of chapters with meaningful (non-generic) titles.
    Used by the quality filter to reward well-structured content.
    """
    if not chapters:
        return 0.0
    specific = sum(
        1 for ch in chapters
        if not all(w in GENERIC_CHAPTER_WORDS for w in ch["title"].lower().split())
    )
    return round(specific / len(chapters), 2)


# ── Metadata extraction ───────────────────────────────────────────────────────

def _format_duration(seconds: int) -> str:
    if not seconds:
        return "0:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def extract_metadata(raw: dict, query: str) -> dict:
    """
    Pull clean, typed metadata fields from a raw yt-dlp result dict.
    Caps stored description at 2000 chars to keep JSON files lean.
    """
    upload_raw = raw.get("upload_date") or ""
    upload_fmt = (
        f"{upload_raw[:4]}-{upload_raw[4:6]}-{upload_raw[6:]}"
        if len(upload_raw) == 8 else upload_raw
    )

    duration_sec = int(raw.get("duration") or 0)

    return {
        "title":              raw.get("title", ""),
        "channel":            raw.get("uploader") or raw.get("channel", ""),
        "url":                raw.get("webpage_url")
                              or f"https://www.youtube.com/watch?v={raw.get('id', '')}",
        "duration_seconds":   duration_sec,
        "duration_formatted": _format_duration(duration_sec),
        "thumbnail":          raw.get("thumbnail", ""),
        "query":              query,
        "description":        (raw.get("description") or "")[:2000],
        "view_count":         raw.get("view_count") or 0,
        "upload_date":        upload_fmt,
        "fetched_at":         datetime.now().isoformat(),
    }
