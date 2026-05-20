"""
multi_search.py
───────────────
Enter any topic — however niche or compound — and this script will:
  1. Decompose it into multiple focused YouTube search angles
  2. Search YouTube for each angle independently
  3. Merge and deduplicate all results into one CSV
  4. Pull transcripts for every unique video (unless --skip-transcripts)

No AI/LLM used. Decomposition is pure text heuristics.

Installation:
    pip install youtube-search-python youtube-transcript-api pandas

Usage:
    python multi_search.py
    python multi_search.py -q "cyberpunk neo noir film making"
    python multi_search.py -q "machine learning calculus" -n 8 --max-angles 3
    python multi_search.py -q "jazz theory improvisation" --skip-transcripts
"""

import os
import sys
import time
import argparse

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from youtubesearchpython import VideosSearch
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

OUTPUT_DIR     = "outputs"
SEARCH_CSV     = os.path.join(OUTPUT_DIR, "youtube_search_results.csv")
TRANSCRIPT_CSV = os.path.join(OUTPUT_DIR, "video_transcripts.csv")

PREFERRED_LANGUAGES = ["en", "en-US", "en-GB"]
_api = YouTubeTranscriptApi()

# Words filtered out before building sub-query windows
STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at",
    "to", "for", "with", "by", "from", "as", "vs", "versus",
    "about", "into", "through", "between", "is", "are", "was",
}


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-angle YouTube search + transcript pipeline."
    )
    parser.add_argument(
        "-q", "--query",
        type=str, default=None,
        help="Topic to research (prompted interactively if omitted)"
    )
    parser.add_argument(
        "-n", "--num-results",
        type=int, default=8,
        help="Videos to fetch per search angle (default: 8)"
    )
    parser.add_argument(
        "--max-angles",
        type=int, default=4,
        help="Maximum number of search angles to generate (default: 4)"
    )
    parser.add_argument(
        "--delay",
        type=float, default=1.0,
        help="Seconds between transcript requests (default: 1.0)"
    )
    parser.add_argument(
        "--skip-transcripts",
        action="store_true",
        help="Export search CSV only, skip transcript extraction"
    )
    return parser.parse_args()


# ── Topic decomposition ───────────────────────────────────────────────────────

def content_words(topic: str) -> list[str]:
    """Strip stop words and return remaining meaningful tokens."""
    return [w for w in topic.lower().split() if w not in STOP_WORDS]


def generate_angles(topic: str, max_angles: int) -> list[str]:
    """
    Decompose a complex topic into focused search sub-queries.

    Strategy:
      - Angle 1: the full topic exactly as typed
      - Remaining angles: sliding windows of 3 content words,
        spread evenly across the token list so they cover
        early, middle, and late concepts without too much overlap.

    Example — "cyberpunk post renaissance neo noir film making":
      content words : [cyberpunk, post, renaissance, neo, noir, film, making]
      angle 1       : "cyberpunk post renaissance neo noir film making"
      angle 2       : "cyberpunk post renaissance"
      angle 3       : "renaissance neo noir"
      angle 4       : "noir film making"
    """
    angles = [topic.strip()]

    words = content_words(topic)

    if len(words) < 3:
        # Topic is short enough — just use it as-is
        return angles

    window = 3
    slots  = max_angles - 1  # how many window-based angles we want

    # Generate all possible 3-word windows (no stop-word run)
    candidates = []
    for i in range(len(words) - window + 1):
        chunk = " ".join(words[i : i + window])
        candidates.append((i, chunk))

    # Pick `slots` candidates spread evenly across the list
    if len(candidates) <= slots:
        chosen = candidates
    else:
        # Even spread: pick indices 0, step, 2*step, …
        step   = (len(candidates) - 1) / max(slots - 1, 1)
        chosen = [candidates[round(i * step)] for i in range(slots)]

    for _, chunk in chosen:
        if chunk not in angles:
            angles.append(chunk)

    return angles[:max_angles]


# ── Search ────────────────────────────────────────────────────────────────────

def search_angle(query: str, limit: int, angle_label: str) -> list[dict]:
    """Search YouTube for one angle and return structured rows."""
    print(f"\n  Angle: '{query}'")
    try:
        search  = VideosSearch(query, limit=limit)
        results = search.result().get("result", [])
    except Exception as exc:
        print(f"  [!] Search failed: {exc}")
        return []

    rows = []
    for video in results:
        try:
            thumbnails    = video.get("thumbnails", [])
            thumbnail_url = thumbnails[-1]["url"] if thumbnails else ""
            rows.append({
                "query":        angle_label,   # original full topic
                "search_angle": query,         # actual sub-query used
                "video_title":  video.get("title", ""),
                "channel":      video.get("channel", {}).get("name", ""),
                "duration":     video.get("duration", ""),
                "url":          video.get("link", ""),
                "video_id":     video.get("id", ""),
                "thumbnail":    thumbnail_url,
            })
        except Exception:
            pass

    print(f"  -> {len(rows)} videos found")
    return rows


# ── Transcript helpers ────────────────────────────────────────────────────────

def seconds_to_hms(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def fetch_transcript(video_id: str) -> list | None:
    """Fetch transcript: preferred languages first, then auto-generated fallback."""
    try:
        return _api.fetch(video_id, languages=PREFERRED_LANGUAGES)
    except NoTranscriptFound:
        pass
    except TranscriptsDisabled:
        print("    [!] Transcripts disabled.")
        return None
    except VideoUnavailable:
        print("    [!] Video unavailable.")
        return None
    except Exception as exc:
        print(f"    [!] {exc}")
        return None

    # Fallback: auto-generated captions
    try:
        for t in _api.list(video_id):
            if t.is_generated:
                return t.fetch()
    except Exception as exc:
        print(f"    [!] Auto-caption fallback failed: {exc}")

    return None


def build_transcript_rows(video_id, video_title, video_url, transcript) -> list[dict]:
    rows = []
    for seg in transcript:
        try:
            text, start, dur = seg.text, seg.start, seg.duration
        except AttributeError:
            text, start, dur = seg["text"], seg["start"], seg["duration"]

        rows.append({
            "video_id":        video_id,
            "video_title":     video_title,
            "timestamp":       seconds_to_hms(start),
            "duration":        round(dur, 2),
            "transcript_text": text.strip(),
            "video_url":       video_url,
        })
    return rows


def run_transcript_extraction(videos: pd.DataFrame, delay: float) -> None:
    total         = len(videos)
    all_rows      = []
    success_count = 0
    skip_count    = 0

    print(f"\n{'─'*55}")
    print(f"[*] Extracting transcripts for {total} unique videos ...\n")

    for i, row in videos.iterrows():
        video_id    = str(row["video_id"]).strip()
        video_title = str(row.get("video_title", "")).strip()
        video_url   = str(row.get("url", "")).strip()

        label = (video_title[:62] + "...") if len(video_title) > 62 else video_title
        print(f"  [{i + 1}/{total}] {label}")

        transcript = fetch_transcript(video_id)

        if transcript is None:
            print("    [~] Skipped.\n")
            skip_count += 1
        else:
            rows = build_transcript_rows(video_id, video_title, video_url, transcript)
            all_rows.extend(rows)
            print(f"    [+] {len(rows)} segments\n")
            success_count += 1

        if i < total - 1:
            time.sleep(delay)

    if not all_rows:
        print("[!] No transcripts extracted.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = pd.DataFrame(all_rows)
    df.to_csv(TRANSCRIPT_CSV, index=False, encoding="utf-8")

    print("─" * 55)
    print(f"[+] Transcribed : {success_count} videos")
    print(f"[+] Skipped     : {skip_count} videos")
    print(f"[+] Total rows  : {len(df)}")
    print(f"[+] Saved       : {TRANSCRIPT_CSV}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    topic = args.query or input("Enter your topic: ").strip()
    if not topic:
        print("[!] No topic provided. Exiting.")
        return

    # ── Step 1: Generate angles ───────────────────────────────────────────────
    angles = generate_angles(topic, max_angles=args.max_angles)

    print(f"\n[*] Topic   : {topic}")
    print(f"[*] Angles  : {len(angles)}")
    for i, a in enumerate(angles, 1):
        print(f"    {i}. {a}")
    print(f"[*] Results : up to {args.num_results} per angle\n")
    print("─" * 55)

    # ── Step 2: Search each angle ─────────────────────────────────────────────
    all_rows = []
    for angle in angles:
        rows = search_angle(angle, limit=args.num_results, angle_label=topic)
        all_rows.extend(rows)

    if not all_rows:
        print("\n[!] No results found across any angle.")
        return

    # ── Step 3: Merge + deduplicate by video_id ───────────────────────────────
    df = pd.DataFrame(all_rows)
    before = len(df)
    df = df.drop_duplicates(subset=["video_id"]).reset_index(drop=True)
    after  = len(df)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(SEARCH_CSV, index=False, encoding="utf-8")

    print(f"\n{'─'*55}")
    print(f"[+] Raw results     : {before}")
    print(f"[+] After dedupe    : {after} unique videos")
    print(f"[+] Saved           : {SEARCH_CSV}\n")

    # Quick angle breakdown
    breakdown = df["search_angle"].value_counts()
    print("Unique videos per angle:")
    for angle, count in breakdown.items():
        print(f"  {count:>3}  {angle}")

    # ── Step 4: Transcripts (optional) ───────────────────────────────────────
    if not args.skip_transcripts:
        run_transcript_extraction(df, delay=args.delay)
    else:
        print("\n[*] Transcript extraction skipped (--skip-transcripts).")


if __name__ == "__main__":
    main()
