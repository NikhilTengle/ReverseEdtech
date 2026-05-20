# ReverseEdtech

A quality-filtered YouTube educational corpus builder.  
Search any topic, score each video for educational value, pull transcripts, save structured JSON — no LLMs, no paid APIs, no UI.

---

## How it works

1. **Search** — yt-dlp fetches up to N YouTube results with full metadata (description, chapters, view count, duration)
2. **Score** — each video is scored 0–95 across duration, chapters, educational keywords, and view count
3. **Filter** — only videos above the threshold get transcripts fetched
4. **Save** — one JSON file per accepted video + a running CSV index

---

## Quickstart

```bash
pip install -r requirements.txt

python pipeline.py -q "Power BI tutorial"
python pipeline.py -q "machine learning math" -n 30 --threshold 50
```

---

## CLI reference

```
python pipeline.py -q "your topic"

  -q / --query               Learning goal / search query (prompted if omitted)
  -n / --num-results INT     Candidates to fetch from YouTube (default: 20)
  --threshold INT            Min quality score to accept a video (default: 45 / 95)
  --delay FLOAT              Seconds between transcript requests (default: 0.5)
  --cookies-from-browser     Use browser session to bypass rate-limiting: chrome, edge, firefox
```

---

## Outputs

Both are gitignored (can be large).

**`raw_transcripts/<video_id>.json`**

```json
{
  "video_id": "...",
  "metadata": { "title", "channel", "url", "duration_formatted", "view_count", "upload_date", ... },
  "quality":  { "score", "threshold", "signals" },
  "chapters": [ { "timestamp": "0:00", "title": "Introduction" }, ... ],
  "transcript": [ { "segment_id": 1, "start": 12.5, "end": 16.2, "duration": 3.7, "text": "..." }, ... ]
}
```

**`outputs/corpus_index.csv`**

| Column | Description |
|---|---|
| `video_id` | YouTube video ID |
| `title` | Video title |
| `channel` | Channel name |
| `duration` | Duration string |
| `quality_score` | Score out of 95 |
| `chapter_count` | Number of chapters extracted |
| `transcript_segs` | Number of transcript segments |
| `view_count` | YouTube view count |
| `query` | Query used to find this video |
| `json_path` | Path to the full JSON file |
| `fetched_at` | ISO timestamp of extraction |

---

## Quality scoring

| Signal | Max points |
|---|---|
| Duration (2–20 min scores highest) | 20 |
| Chapter count and specificity | 30 |
| Educational keywords in title | 25 |
| View count | 15 |
| Rich description (>200 chars) | 5 |
| **Total** | **95** |

Hard rejects (score = 0, no transcript fetched): duration under 2 min, YouTube Shorts, reaction/meme/vlog keywords in title.

---

## Stack

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — search, metadata, subtitle download
- pandas

No LangChain. No OpenAI. No paid APIs. No UI. No database.
