"""Step 1 - SEO keyword research.

VERIFIED data: every keyword here was returned by Google Autocomplete, i.e. it is a
real query people type. We also record its autocomplete rank and how many seed
queries surfaced it.

ESTIMATED data: search-volume tier, difficulty and intent are heuristics derived
from those signals. No free tool exposes real search volume, so the UI labels
these as estimates.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
SAMPLE_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_keywords.json"

SEEDS = [
    "digital marketing course in coimbatore",
    "digital marketing course",
    "digital marketing training in coimbatore",
    "digital marketing course fees",
    "digital marketing course with placement",
    "digital marketing course for beginners",
    "seo course in coimbatore",
    "digital marketing jobs in coimbatore",
    "digital marketing career",
    "learn digital marketing",
]
MODIFIERS = ["", " for", " with", " vs", " online", " after"]
QUESTION_SEEDS = [
    "is digital marketing", "how to learn digital marketing", "what is digital marketing",
    "which digital marketing course", "best digital marketing course",
]

STOPWORDS = {"in", "for", "with", "the", "a", "an", "and", "of", "to", "is", "near", "me",
             "vs", "or", "on", "at", "by", "how", "what", "which", "why", "can", "does", "do",
             "best", "top", "after", "from", "it", "i", "my", "are", "be", "good"}
CORE_TERMS = {"marketing", "seo", "sem", "smm", "ads", "advertising"}
COURSE_TERMS = {"course", "courses", "training", "institute", "learn", "learning", "study",
                "certification", "certificate", "class", "classes", "syllabus", "career",
                "salary", "scope", "skills", "beginners", "worth", "fees"}
OTHER_LOCATIONS = {"chennai", "trichy", "madurai", "salem", "bangalore", "delhi", "mumbai",
                   "pune", "kolkata", "hyderabad", "noida", "thane", "dubai", "kerala", "jaipur",
                   "pakistan", "uk", "usa", "africa", "worth", "anna", "nagar", "tamilnadu"}
OTHER_LANGUAGES = {"hindi", "urdu", "malayalam", "telugu", "kannada"}
KNOWN_BRANDS = {"xplore", "pw", "iim", "hubspot", "coursera", "udemy", "simplilearn", "upgrad"}
OWN_BRAND = {"appin"}
JOB_SEARCH = {"vacancy", "today", "yesterday", "since", "last", "hiring", "openings"}

COMMERCIAL = {"fees", "fee", "cost", "price", "institute", "institutes", "admission",
              "placement", "placements", "certification", "near", "best", "top", "join"}
INFORMATIONAL_START = ("how", "what", "why", "is", "can", "which", "does", "do", "should", "are")
INFORMATIONAL = {"salary", "scope", "future", "career", "careers", "syllabus", "duration",
                 "eligibility", "worth", "skills", "learn", "beginners", "roadmap", "path"}


def _suggest(query):
    try:
        r = requests.get(SUGGEST_URL, params={"client": "firefox", "hl": "en", "gl": "in", "q": query},
                         timeout=8)
        r.raise_for_status()
        return query, json.loads(r.text)[1]
    except Exception:
        return query, None


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def classify_intent(kw):
    toks = set(tokens(kw))
    if OWN_BRAND & toks:
        return "navigational (own brand)"
    if KNOWN_BRANDS & toks:
        return "navigational (competitor brand)"
    if JOB_SEARCH & toks or (toks & {"job", "jobs"} and not toks & COURSE_TERMS):
        return "job search"
    if " vs " in f" {kw} ":
        return "comparison"
    first = tokens(kw)[0] if toks else ""
    if first in INFORMATIONAL_START:
        return "informational"
    if COMMERCIAL & toks or "near me" in kw:
        return "commercial"
    if INFORMATIONAL & toks:
        return "informational"
    return "commercial"


def _score(kw, info):
    toks = tokens(kw)
    tokset = set(toks)
    intent = classify_intent(kw)

    # Relevance to "Digital Marketing Course in Coimbatore" - rule based, explained in flags.
    flags = []
    relevance = 1.0 if CORE_TERMS & tokset else 0.3
    if not CORE_TERMS & tokset:
        flags.append("not about digital marketing")
    if OTHER_LOCATIONS & tokset and "coimbatore" not in tokset:
        relevance *= 0.2
        flags.append("targets another city")
    if OTHER_LANGUAGES & tokset:
        relevance *= 0.3
        flags.append("other language")
    if {"there", "any", "some"} & tokset:
        relevance *= 0.8
        flags.append("vague phrasing")
    if "free" in tokset:
        relevance *= 0.75
        flags.append("free-seeker (low course fit)")
    local_boost = 1.2 if "coimbatore" in tokset else 1.0
    if local_boost > 1:
        flags.append("local Coimbatore intent (+20%)")

    words = len(toks)
    volume = (0.45 * (1 - info["best_rank"] / 10)
              + 0.35 * min(info["appearances"], 4) / 4
              + 0.20 * (1 - min(max(words - 3, 0), 6) / 6))
    difficulty = {1: 0.95, 2: 0.9, 3: 0.8, 4: 0.65, 5: 0.5, 6: 0.4}.get(words, 0.3)
    if intent == "commercial":
        difficulty += 0.15
    elif intent in ("informational", "comparison"):
        difficulty -= 0.1
    difficulty = min(max(difficulty, 0.05), 1.0)

    # How well a *blog post* serves this intent (commercial head terms belong to the course page).
    fit = {"informational": 1.0, "comparison": 1.0, "commercial": 0.8, "job search": 0.4}.get(intent, 0.0)
    opportunity = relevance * (0.5 + 0.5 * volume) * (1 - 0.6 * difficulty) * fit * local_boost

    return {
        "keyword": kw,
        "verified": {
            "source": info["source"],
            "autocomplete_rank": info["best_rank"] + 1,
            "seen_in_seed_queries": info["appearances"],
        },
        "estimated": {
            "volume_tier": "High" if volume >= 0.62 else "Medium" if volume >= 0.42 else "Low",
            "volume_score": round(volume, 2),
            "difficulty": round(difficulty, 2),
            "difficulty_label": "Hard" if difficulty >= 0.7 else "Medium" if difficulty >= 0.45 else "Easy",
        },
        "intent": intent,
        "flags": flags,
        "relevance": round(relevance, 2),
        "opportunity": round(opportunity, 3),
    }


def research_keywords():
    """Expand seeds through Google Autocomplete and score every unique suggestion."""
    queries = [s + m for s in SEEDS for m in MODIFIERS] + QUESTION_SEEDS
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_suggest, queries))

    found = {}
    ok = 0
    for query, suggestions in results:
        if suggestions is None:
            continue
        ok += 1
        for rank, s in enumerate(suggestions):
            kw = re.sub(r"\s+", " ", s.strip().lower())
            entry = found.setdefault(kw, {"best_rank": rank, "appearances": 0,
                                          "source": "Google Autocomplete (live)"})
            entry["best_rank"] = min(entry["best_rank"], rank)
            entry["appearances"] += 1

    source = "live"
    if not found:  # offline: fall back to a saved snapshot, clearly labelled
        source = "sample"
        for item in json.loads(SAMPLE_FILE.read_text(encoding="utf-8")):
            found[item["keyword"]] = {"best_rank": item["rank"], "appearances": 1,
                                      "source": "Saved sample (not live-verified)"}

    scored = sorted((_score(kw, info) for kw, info in found.items()),
                    key=lambda k: k["opportunity"], reverse=True)
    return {"source": source, "queries_sent": len(queries), "queries_ok": ok, "keywords": scored}
