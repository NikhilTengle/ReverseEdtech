"""
youtube_search_extract.py
─────────────────────────
Search YouTube for educational videos and export metadata to CSV.

Installation:
    pip install youtube-search-python pandas

Usage:
    python youtube_search_extract.py                         # interactive prompt
    python youtube_search_extract.py -q "python loops"       # inline query
    python youtube_search_extract.py -q "python loops" -n 15 # custom result count
"""

import os
import sys
import argparse
import pandas as pd
from youtubesearchpython import VideosSearch

# Force UTF-8 output so video titles with non-ASCII chars print correctly on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUTPUT_DIR  = "outputs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "youtube_search_results.csv")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search YouTube and export video metadata to CSV."
    )
    parser.add_argument(
        "-q", "--query",
        type=str, default=None,
        help="Search query (prompted interactively if omitted)"
    )
    parser.add_argument(
        "-n", "--num-results",
        type=int, default=10,
        help="Number of videos to fetch (default: 10)"
    )
    return parser.parse_args()


# ── Search ────────────────────────────────────────────────────────────────────

def search_youtube(query: str, limit: int) -> list[dict]:
    """Run a YouTube search and return the raw result list."""
    print(f"[*] Searching YouTube for: '{query}'  (limit={limit}) ...")
    search  = VideosSearch(query, limit=limit)
    results = search.result()
    return results.get("result", [])


# ── Parse ─────────────────────────────────────────────────────────────────────

def extract_metadata(raw_results: list[dict], query: str) -> list[dict]:
    """
    Pull the fields we care about from each raw result dict.

    youtube-search-python returns a list of video dicts that look like:
        {
          "id":         "dQw4w9WgXcQ",
          "title":      "...",
          "channel":    {"name": "..."},
          "duration":   "3:33",
          "link":       "https://www.youtube.com/watch?v=...",
          "thumbnails": [{"url": "...", "width": ..., "height": ...}, ...]
        }
    """
    rows = []

    for video in raw_results:
        try:
            thumbnails = video.get("thumbnails", [])
            # Last thumbnail in the list is typically the highest resolution
            thumbnail_url = thumbnails[-1]["url"] if thumbnails else ""

            rows.append({
                "query":       query,
                "video_title": video.get("title", ""),
                "channel":     video.get("channel", {}).get("name", ""),
                "duration":    video.get("duration", ""),
                "url":         video.get("link", ""),
                "video_id":    video.get("id", ""),
                "thumbnail":   thumbnail_url,
            })

        except Exception as exc:
            print(f"  [!] Skipping one video due to parse error: {exc}")

    return rows


# ── Export ────────────────────────────────────────────────────────────────────

def save_csv(rows: list[dict], filepath: str) -> pd.DataFrame:
    """Convert rows to a DataFrame and write to CSV."""
    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_csv(filepath, index=False, encoding="utf-8")
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # Fall back to interactive prompt if no -q flag was given
    query = args.query or input("Enter your search query: ").strip()
    if not query:
        print("[!] No query provided. Exiting.")
        return

    raw = search_youtube(query, limit=args.num_results)

    if not raw:
        print("[!] No results returned. Check your query or network connection.")
        return

    rows = extract_metadata(raw, query)
    df   = save_csv(rows, OUTPUT_FILE)

    # Print a quick preview table
    print(f"\n[+] {len(df)} videos extracted -> {OUTPUT_FILE}\n")
    preview_cols = ["video_title", "channel", "duration"]
    print(df[preview_cols].to_string(index=False))


if __name__ == "__main__":
    main()
