"""
transcript_parser.py
────────────────────
Fetch YouTube transcripts using yt-dlp's subtitle downloader.

Why yt-dlp instead of youtube-transcript-api:
  - youtube-transcript-api is blocked by YouTube IP rate-limiting
  - yt-dlp uses browser/client impersonation that bypasses this
  - The subtitle URLs are already in the search result dict —
    we write them to a temp file and parse, so no extra API call per video

Fetch strategy:
  1. Use yt-dlp to download subtitles (manual EN first, auto-generated fallback)
  2. Write JSON3 subtitle file to a temp directory
  3. Parse the JSON3 events into our structured segment format
  4. Return None if no subtitles available

Each segment returned:
  {
    "segment_id": 1,
    "start":      12.5,
    "end":        16.2,
    "duration":   3.7,
    "text":       "Welcome to Power BI"
  }
"""

import os
import json
import glob
import tempfile
import yt_dlp


def fetch_transcript(video_id: str,
                     cookies_from_browser: str | None = None) -> list[dict] | None:
    """
    Download and parse subtitles for a video.
    Uses a temp directory — no files persist after the call.
    Returns None if the video has no accessible subtitles.

    Pass cookies_from_browser='chrome' (or 'firefox') to bypass YouTube
    IP rate-limiting (HTTP 429 / IpBlocked errors).
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = os.path.join(tmpdir, "%(id)s")

        ydl_opts = {
            "quiet":             True,
            "no_warnings":       True,
            "noprogress":        True,
            "skip_download":     True,      # video file not needed
            "writesubtitles":    True,      # manual captions
            "writeautomaticsub": True,      # auto-generated captions
            "subtitleslangs":    ["en", "en-US", "en-GB"],
            "subtitlesformat":   "json3",   # structured, easy to parse
            "outtmpl":           out_template,
        }

        if cookies_from_browser:
            ydl_opts["cookiesfrombrowser"] = (cookies_from_browser, None, None, None)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception:
            return None   # network error or unavailable video

        # Find whatever .json3 subtitle file was written
        matches = glob.glob(os.path.join(tmpdir, f"{video_id}.*.json3"))
        if not matches:
            return None

        try:
            with open(matches[0], encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

    return _parse_json3(data)


def _parse_json3(data: dict) -> list[dict] | None:
    """
    Convert YouTube's JSON3 subtitle format into flat segment dicts.

    JSON3 structure:
      { "events": [
          { "tStartMs": 1200, "dDurationMs": 3700,
            "segs": [{"utf8": "Welcome "}, {"utf8": "to Power BI"}] },
          ...
      ]}
    """
    events   = data.get("events", [])
    segments = []
    seg_id   = 1

    for event in events:
        segs = event.get("segs", [])
        if not segs:
            continue

        text = "".join(s.get("utf8", "") for s in segs).strip()
        # Skip positioning/styling events that have no real text
        if not text or text == "\n":
            continue

        start = event.get("tStartMs", 0) / 1000
        dur   = event.get("dDurationMs", 0) / 1000

        segments.append({
            "segment_id": seg_id,
            "start":      round(start, 2),
            "end":        round(start + dur, 2),
            "duration":   round(dur, 2),
            "text":       text,
        })
        seg_id += 1

    return segments if segments else None
