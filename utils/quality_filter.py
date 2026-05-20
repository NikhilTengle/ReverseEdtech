"""
quality_filter.py
─────────────────
Lightweight, deterministic quality scoring for educational YouTube content.

Score breakdown (max ~95):
  Duration score      0 – 20   long-form rewards depth
  Chapter score       0 – 30   structure + specificity
  Edu keyword score   0 – 25   title/description signals
  View count score    0 – 15   social proof of usefulness
  Rich description    0 –  5   bonus for detailed descriptions

Hard rejects (score = 0, video skipped immediately):
  - Duration under 2 minutes
  - YouTube Shorts (#shorts in URL or title)
  - Explicit non-educational keywords in title

The reject log is returned so the pipeline can report WHY content
was rejected — useful for understanding the content landscape of a niche.
"""

from utils.fetcher import chapter_specificity

# ── Signal dictionaries ───────────────────────────────────────────────────────

EDUCATIONAL_KEYWORDS = [
    "tutorial", "course", "lesson", "guide", "masterclass",
    "explained", "learn", "how to", "introduction to", "crash course",
    "beginner", "advanced", "deep dive", "fundamentals", "basics",
    "step by step", "complete", "full course", "bootcamp", "workshop",
    "walkthrough", "hands-on", "project", "overview", "lecture",
]

# Any of these in the title → immediate reject, no further scoring
REJECT_KEYWORDS = [
    "#shorts", "shorts",
    "reaction", "reacts to",
    "funny moments", "meme compilation",
    "motivation", "motivational",
    "vlog", "day in my life",
    "aesthetic", "satisfying",
    "asmr", "challenge",
    "tiktok compilation", "best moments",
    "highlights", "montage",
]


# ── Sub-scorers ───────────────────────────────────────────────────────────────

def _duration_score(seconds: float) -> int:
    minutes = seconds / 60
    if minutes >= 60: return 20
    if minutes >= 30: return 15
    if minutes >= 15: return 10
    if minutes >= 8:  return 5
    return 2


def _chapter_score(chapters: list[dict]) -> int:
    n = len(chapters)
    if n == 0:   return 0
    if n >= 15:  base = 30
    elif n >= 8: base = 22
    elif n >= 4: base = 15
    else:        base = 8

    # Specificity bonus: reward chapters with meaningful topic titles
    spec = chapter_specificity(chapters)
    bonus = 8 if spec >= 0.7 else 4 if spec >= 0.4 else 0

    return min(base + bonus, 30)


def _edu_keyword_score(title: str, description: str) -> tuple[int, list[str]]:
    # Only scan the first 600 chars of description to avoid noise in long bodies
    text    = f"{title} {description[:600]}".lower()
    matched = [kw for kw in EDUCATIONAL_KEYWORDS if kw in text]
    return min(len(matched) * 5, 25), matched[:6]


def _view_score(view_count: int) -> int:
    if view_count >= 500_000: return 15
    if view_count >= 100_000: return 10
    if view_count >= 10_000:  return 5
    return 0


# ── Main scorer ───────────────────────────────────────────────────────────────

def score_video(raw: dict, chapters: list[dict]) -> tuple[int, dict]:
    """
    Score a video for educational quality.

    Returns:
        (score, signals)
        score = 0 means hard-rejected; signals["rejected"] explains why.
        score > 0 means eligible; compare against threshold to accept.
    """
    title       = (raw.get("title") or "").lower()
    description =  raw.get("description") or ""
    duration    =  raw.get("duration") or 0
    view_count  =  raw.get("view_count") or 0
    url         =  raw.get("webpage_url") or ""

    # ── Hard rejects ──────────────────────────────────────────────────────────
    if duration < 120:
        return 0, {"rejected": "too_short", "duration_seconds": duration}

    if "shorts" in url.lower() or "#shorts" in title:
        return 0, {"rejected": "is_short"}

    for kw in REJECT_KEYWORDS:
        if kw in title:
            return 0, {"rejected": "reject_keyword", "matched_keyword": kw}

    # ── Soft scoring ──────────────────────────────────────────────────────────
    dur_score              = _duration_score(duration)
    ch_score               = _chapter_score(chapters)
    edu_score, matched_kws = _edu_keyword_score(title, description)
    view_score             = _view_score(view_count)
    # Bonus for descriptions with real structure (many lines = detailed outline)
    desc_bonus             = 5 if description.count("\n") > 15 else 0

    total = dur_score + ch_score + edu_score + view_score + desc_bonus

    signals = {
        # Duration
        "duration_minutes":     round(duration / 60, 1),
        "duration_score":       dur_score,
        # Chapters
        "has_chapters":         len(chapters) > 0,
        "chapter_count":        len(chapters),
        "chapter_specificity":  chapter_specificity(chapters),
        "chapter_score":        ch_score,
        # Keywords
        "educational_keywords": matched_kws,
        "edu_score":            edu_score,
        # Views
        "view_count":           view_count,
        "view_score":           view_score,
        # Misc
        "desc_bonus":           desc_bonus,
        "total_score":          total,
    }

    return total, signals


def passes_threshold(score: int, threshold: int = 45) -> bool:
    return score >= threshold
