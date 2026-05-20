# ReverseEdtech

A lightweight YouTube educational content extraction pipeline.  
Search any topic, pull transcripts, export structured CSVs — no LLMs, no paid APIs, no UI.

---

## Scripts

| Script | What it does |
|---|---|
| `youtube_search_extract.py` | Search YouTube for a query, export video metadata to CSV |
| `transcript_extract_export.py` | Read metadata CSV, fetch transcripts, export timestamped rows |
| `multi_search.py` | Full pipeline — decomposes any topic into multiple search angles, searches all of them, merges results, pulls transcripts |

---

## Quickstart

```bash
pip install -r requirements.txt
```

### Option A — step by step

```bash
# 1. Search YouTube
python youtube_search_extract.py -q "python for beginners" -n 10

# 2. Pull transcripts
python transcript_extract_export.py
```

### Option B — single command (recommended)

```bash
python multi_search.py -q "cyberpunk post renaissance neo noir film making"
```

---

## multi_search.py — how topic decomposition works

Given a compound topic, the script splits it into focused sub-queries using a sliding-window heuristic over content words (stop words removed). No AI required.

**Example**

```
Topic   : "cyberpunk post renaissance neo noir film making"

Angle 1 : "cyberpunk post renaissance neo noir film making"  (full topic)
Angle 2 : "cyberpunk post renaissance"                       (first 3 content words)
Angle 3 : "renaissance neo noir"                             (middle 3)
Angle 4 : "noir film making"                                 (last 3)
```

Each angle is searched independently on YouTube. Results are merged and deduplicated by `video_id` before transcript extraction.

---

## Outputs

Both CSVs are written to `outputs/` (gitignored).

**`outputs/youtube_search_results.csv`**

| Column | Description |
|---|---|
| `query` | Original topic entered |
| `search_angle` | Sub-query used to find this video (`multi_search.py` only) |
| `video_title` | Video title |
| `channel` | Channel name |
| `duration` | Duration string (e.g. `10:30`) |
| `url` | Full YouTube URL |
| `video_id` | YouTube video ID |
| `thumbnail` | Highest-resolution thumbnail URL |

**`outputs/video_transcripts.csv`**

| Column | Description |
|---|---|
| `video_id` | YouTube video ID |
| `video_title` | Video title |
| `timestamp` | Segment start time (`HH:MM:SS`) |
| `duration` | Segment duration in seconds |
| `transcript_text` | Transcript text for this segment |
| `video_url` | Full YouTube URL |

---

## CLI reference

```bash
# youtube_search_extract.py
python youtube_search_extract.py                          # interactive prompt
python youtube_search_extract.py -q "query" -n 15

# transcript_extract_export.py
python transcript_extract_export.py
python transcript_extract_export.py --delay 2.0

# multi_search.py
python multi_search.py                                    # interactive prompt
python multi_search.py -q "jazz theory improvisation"
python multi_search.py -q "stoic philosophy" -n 10 --max-angles 5
python multi_search.py -q "machine learning math" --skip-transcripts
python multi_search.py -q "topic" --delay 2.0
```

---

## Stack

- Python 3.11+
- [youtube-search-python](https://github.com/alexmercerind/youtube-search-python)
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)
- pandas

No LangChain. No OpenAI. No paid APIs. No UI. No database.
