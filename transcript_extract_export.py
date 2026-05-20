"""
transcript_extract_export.py
─────────────────────────────
Read video metadata from youtube_search_results.csv, fetch transcripts,
and export timestamped rows to video_transcripts.csv.

Run youtube_search_extract.py first to generate the input CSV.

Installation:
    pip install youtube-transcript-api pandas

Usage:
    python transcript_extract_export.py                  # defaults
    python transcript_extract_export.py --delay 2.0      # 2 s between requests
    python transcript_extract_export.py --input my.csv   # custom input file
"""

import os
import sys
import time
import argparse

# Force UTF-8 output so video titles with non-ASCII chars print correctly on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# v1.x uses an instance; create one shared instance for all requests
_api = YouTubeTranscriptApi()

INPUT_FILE  = os.path.join("outputs", "youtube_search_results.csv")
OUTPUT_FILE = os.path.join("outputs", "video_transcripts.csv")

# Languages tried in order for manual captions; falls back to auto-generated
PREFERRED_LANGUAGES = ["en", "en-US", "en-GB"]


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch YouTube transcripts and export to CSV."
    )
    parser.add_argument(
        "--input",
        type=str, default=INPUT_FILE,
        help=f"Path to video metadata CSV (default: {INPUT_FILE})"
    )
    parser.add_argument(
        "--delay",
        type=float, default=1.0,
        help="Seconds to wait between transcript requests to avoid rate-limiting (default: 1.0)"
    )
    return parser.parse_args()


# ── Helpers ───────────────────────────────────────────────────────────────────

def seconds_to_hms(seconds: float) -> str:
    """Convert a float number of seconds into HH:MM:SS."""
    total = int(seconds)
    h =  total // 3600
    m = (total %  3600) // 60
    s =  total %  60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── Data loading ──────────────────────────────────────────────────────────────

def load_video_list(filepath: str) -> pd.DataFrame:
    """
    Read the metadata CSV produced by youtube_search_extract.py.
    Validates required columns, drops rows with missing IDs,
    and deduplicates so each video is processed only once.
    """
    df = pd.read_csv(filepath, encoding="utf-8")

    required = {"video_id", "video_title", "url"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV is missing expected columns: {missing}")

    df = df.dropna(subset=["video_id"])
    # Deduplication matters when the same video appears across multiple queries
    df = df.drop_duplicates(subset=["video_id"]).reset_index(drop=True)
    return df


# ── Transcript fetching ───────────────────────────────────────────────────────

def fetch_transcript(video_id: str) -> list[dict] | None:
    """
    Try to retrieve a transcript for the given video ID.

    Strategy:
      1. Request manually uploaded captions in PREFERRED_LANGUAGES.
      2. If none found, iterate available transcripts and pick the first
         auto-generated one (common for educational content).
      3. Return None if transcripts are disabled or unavailable.
    """
    # Attempt 1 — preferred manual languages
    try:
        return _api.fetch(video_id, languages=PREFERRED_LANGUAGES)
    except NoTranscriptFound:
        pass  # continue to auto-generated fallback
    except TranscriptsDisabled:
        print("    [!] Transcripts are disabled for this video.")
        return None
    except VideoUnavailable:
        print("    [!] Video is unavailable (private or deleted).")
        return None
    except Exception as exc:
        print(f"    [!] Unexpected error: {exc}")
        return None

    # Attempt 2 — first available auto-generated caption track
    try:
        transcript_list = _api.list(video_id)
        for t in transcript_list:
            if t.is_generated:
                return t.fetch()
    except Exception as exc:
        print(f"    [!] Could not retrieve auto-generated transcript: {exc}")

    return None


# ── Row building ──────────────────────────────────────────────────────────────

def build_rows(
    video_id: str,
    video_title: str,
    video_url: str,
    transcript: list[dict],
) -> list[dict]:
    """
    Convert raw transcript segments into flat CSV rows.

    Each segment from youtube-transcript-api looks like:
        {"text": "Hello world", "start": 4.32, "duration": 1.8}
    """
    rows = []
    for seg in transcript:
        # v1.x returns objects with attributes; v0.x returned plain dicts
        try:
            text  = seg.text
            start = seg.start
            dur   = seg.duration
        except AttributeError:
            text  = seg["text"]
            start = seg["start"]
            dur   = seg["duration"]

        rows.append({
            "video_id":        video_id,
            "video_title":     video_title,
            "timestamp":       seconds_to_hms(start),
            "duration":        round(dur, 2),
            "transcript_text": text.strip(),
            "video_url":       video_url,
        })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    if not os.path.exists(args.input):
        print(f"[!] Input file not found: {args.input}")
        print("    Run youtube_search_extract.py first, then re-run this script.")
        return

    videos = load_video_list(args.input)
    total  = len(videos)
    print(f"[*] Loaded {total} unique videos from {args.input}\n")

    all_rows      = []
    success_count = 0
    skip_count    = 0

    for i, row in videos.iterrows():
        video_id    = str(row["video_id"]).strip()
        video_title = str(row.get("video_title", "")).strip()
        video_url   = str(row.get("url", "")).strip()

        label = video_title[:65] + "…" if len(video_title) > 65 else video_title
        print(f"  [{i + 1}/{total}] {label}")
        print(f"         id: {video_id}")

        transcript = fetch_transcript(video_id)

        if transcript is None:
            print("    [~] Skipped — no transcript available.\n")
            skip_count += 1
        else:
            rows = build_rows(video_id, video_title, video_url, transcript)
            all_rows.extend(rows)
            print(f"    [+] {len(rows)} segments extracted.\n")
            success_count += 1

        # Polite pause between requests — avoids hitting YouTube rate limits
        if i < total - 1:
            time.sleep(args.delay)

    # ── Save ──────────────────────────────────────────────────────────────────
    if not all_rows:
        print("[!] No transcripts were extracted. Nothing to save.")
        return

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

    print("─" * 50)
    print(f"[+] Videos transcribed : {success_count}")
    print(f"[+] Videos skipped     : {skip_count}")
    print(f"[+] Total rows saved   : {len(df)}")
    print(f"[+] Output file        : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
