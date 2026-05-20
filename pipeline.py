"""
pipeline.py
───────────
ReverseEdtech — quality-filtered YouTube educational corpus builder.

Single entry point. Given a learning goal, it:
  1. Searches YouTube via yt-dlp (full metadata, no paid API)
  2. Scores each video for educational quality
  3. Fetches transcripts only for videos that pass the threshold
  4. Saves one structured JSON per accepted video  -> raw_transcripts/<video_id>.json
  5. Maintains a corpus index CSV                 -> outputs/corpus_index.csv

Install:
    pip install yt-dlp youtube-transcript-api pandas

Usage:
    python pipeline.py
    python pipeline.py -q "Power BI tutorial"
    python pipeline.py -q "Become Data Analyst" -n 25
    python pipeline.py -q "Neo Noir Film Making" --threshold 40
    python pipeline.py -q "machine learning math" --threshold 50 -n 30
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from utils.fetcher          import search_videos, extract_metadata, parse_chapters
from utils.quality_filter   import score_video, passes_threshold
from utils.transcript_parser import fetch_transcript

RAW_DIR    = "raw_transcripts"
OUTPUT_DIR = "outputs"
INDEX_CSV  = os.path.join(OUTPUT_DIR, "corpus_index.csv")

DEFAULT_THRESHOLD = 45
DEFAULT_N         = 20


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ReverseEdtech: quality-filtered educational corpus builder."
    )
    p.add_argument("-q", "--query",       type=str, default=None,
                   help="Learning goal / search query")
    p.add_argument("-n", "--num-results", type=int, default=DEFAULT_N,
                   help=f"Candidates to fetch from YouTube (default: {DEFAULT_N})")
    p.add_argument("--threshold",         type=int, default=DEFAULT_THRESHOLD,
                   help=f"Min quality score to accept a video (default: {DEFAULT_THRESHOLD}/95)")
    p.add_argument("--delay",             type=float, default=0.5,
                   help="Seconds between transcript requests (default: 0.5)")
    p.add_argument("--cookies-from-browser", type=str, default=None,
                   metavar="BROWSER",
                   help="Use browser cookies to bypass YouTube rate-limiting. "
                        "Values: chrome, firefox, edge, safari")
    return p.parse_args()


# ── Corpus index ──────────────────────────────────────────────────────────────

def update_index(new_rows: list[dict]) -> None:
    """
    Append newly accepted videos to corpus_index.csv.
    Deduplicates by video_id so re-running a query doesn't create duplicates.
    """
    if not new_rows:
        return

    new_df = pd.DataFrame(new_rows)

    if os.path.exists(INDEX_CSV):
        existing = pd.read_csv(INDEX_CSV, encoding="utf-8")
        # Drop rows whose video_id will be replaced by the new run
        existing = existing[~existing["video_id"].isin(new_df["video_id"])]
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(INDEX_CSV, index=False, encoding="utf-8")


# ── Per-video processing ──────────────────────────────────────────────────────

def process_video(raw: dict, query: str, threshold: int,
                  cookies_from_browser: str | None = None) -> tuple[dict | None, dict]:
    """
    Run the full quality + transcript pipeline on one video.

    Returns:
        (doc, signals)  if accepted
        (None, signals) if rejected — signals["rejected"] gives the reason
    """
    video_id = raw.get("id") or ""
    chapters = parse_chapters(raw)

    score, signals = score_video(raw, chapters)

    if not passes_threshold(score, threshold):
        return None, signals

    transcript = fetch_transcript(video_id, cookies_from_browser=cookies_from_browser)
    if not transcript:
        signals["rejected"] = "no_transcript"
        return None, signals

    metadata = extract_metadata(raw, query)

    doc = {
        "video_id": video_id,
        "metadata": metadata,
        "quality": {
            "score":     score,
            "threshold": threshold,
            "signals":   signals,
        },
        "chapters":   chapters,
        "transcript": transcript,
    }

    return doc, signals


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run(query: str, num_results: int, threshold: int, delay: float,
        cookies_from_browser: str | None = None) -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n{'═' * 60}")
    print(f"  ReverseEdtech Pipeline")
    print(f"  Query      : {query}")
    print(f"  Candidates : {num_results}")
    print(f"  Threshold  : {threshold} / 95")
    print(f"  Started    : {datetime.now().strftime('%Y-%m-%d %H:%M')} local")
    print(f"{'═' * 60}\n")
    if cookies_from_browser:
        print(f"  Cookies    : from {cookies_from_browser}")
    print(f"{'═' * 60}\n")
    print(f"[*] Fetching {num_results} candidates from YouTube...\n")

    raw_videos = search_videos(query, max_results=num_results,
                               cookies_from_browser=cookies_from_browser)

    if not raw_videos:
        print("[!] No videos returned. Check query or network.")
        return

    print(f"[*] Scoring {len(raw_videos)} candidates against threshold {threshold}...\n")

    index_rows   = []
    reject_log   = {}
    accepted     = 0
    rejected     = 0

    for i, raw in enumerate(raw_videos, 1):
        video_id = raw.get("id") or ""
        title    = raw.get("title") or ""
        label    = (title[:62] + "...") if len(title) > 62 else title

        print(f"  [{i:>2}/{len(raw_videos)}] {label}")

        # Skip videos already in corpus
        json_path = os.path.join(RAW_DIR, f"{video_id}.json")
        if os.path.exists(json_path):
            print(f"           [~] Already in corpus — skipped\n")
            continue

        doc, signals = process_video(raw, query, threshold,
                                     cookies_from_browser=cookies_from_browser)

        if doc is None:
            reason = signals.get("rejected") or f"score:{signals.get('total_score', 0)}"
            print(f"           [x] Rejected — {reason}\n")
            reject_log[reason] = reject_log.get(reason, 0) + 1
            rejected += 1
        else:
            score       = doc["quality"]["score"]
            ch_count    = signals.get("chapter_count", 0)
            seg_count   = len(doc["transcript"])
            view_count  = signals.get("view_count", 0)

            # Save JSON
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)

            print(
                f"           [+] Accepted  "
                f"score:{score}  "
                f"chapters:{ch_count}  "
                f"segments:{seg_count}  "
                f"views:{view_count:,}\n"
            )

            index_rows.append({
                "video_id":        video_id,
                "title":           doc["metadata"]["title"],
                "channel":         doc["metadata"]["channel"],
                "duration":        doc["metadata"]["duration_formatted"],
                "quality_score":   score,
                "chapter_count":   ch_count,
                "transcript_segs": seg_count,
                "view_count":      view_count,
                "query":           query,
                "json_path":       json_path,
                "fetched_at":      doc["metadata"]["fetched_at"],
            })
            accepted += 1

        if i < len(raw_videos):
            time.sleep(delay)

    # ── Finalise ──────────────────────────────────────────────────────────────
    update_index(index_rows)

    print(f"{'═' * 60}")
    print(f"  Accepted  : {accepted} videos")
    print(f"  Rejected  : {rejected} videos")
    print(f"  Corpus    : {RAW_DIR}/")
    print(f"  Index     : {INDEX_CSV}")

    if reject_log:
        print(f"\n  Rejection breakdown:")
        for reason, count in sorted(reject_log.items(), key=lambda x: -x[1]):
            print(f"    {count:>3}  {reason}")

    print(f"{'═' * 60}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args  = parse_args()
    query = args.query or input("Enter your learning goal: ").strip()

    if not query:
        print("[!] No query provided. Exiting.")
        return

    run(
        query                = query,
        num_results          = args.num_results,
        threshold            = args.threshold,
        delay                = args.delay,
        cookies_from_browser = args.cookies_from_browser,
    )


if __name__ == "__main__":
    main()
