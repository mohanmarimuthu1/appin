"""Steps 4 + 5 - SEO quality checks, preview rendering and saving the blog page."""
import json
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .planner import OUTPUT_DIR
from .research import tokens

ROOT = Path(__file__).resolve().parent.parent
env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape())


def _covers(text, keyword, threshold=0.8):
    """True if the text contains the keyword phrase, or most of its words."""
    if keyword.lower() in text.lower():
        return True
    kw = set(tokens(keyword))
    return bool(kw) and len(kw & set(tokens(text))) / len(kw) >= threshold


def body_text(draft):
    parts = list(draft.intro)
    for s in draft.sections:
        parts += [s.heading] + s.paragraphs + s.bullets
        for sub in s.subsections:
            parts += [sub.heading] + sub.paragraphs + sub.bullets
    parts += draft.conclusion + [f.question + " " + f.answer for f in draft.faqs]
    return "\n".join(parts)


def validate_links(draft, allowed_links):
    """Drop any internal link the model invented that is not a real candidate URL."""
    allowed = {l["url"] for l in allowed_links}
    removed = [l.url for l in draft.internal_links if l.url not in allowed]
    draft.internal_links = [l for l in draft.internal_links if l.url in allowed]
    return removed


def seo_checks(draft, slug, cluster):
    kw = cluster["primary"]["keyword"]
    text = body_text(draft)
    words = len(re.findall(r"\w+", text))
    first_100 = " ".join(re.findall(r"\S+", " ".join(draft.intro))[:100])
    h2 = len(draft.sections)
    h3 = sum(len(s.subsections) for s in draft.sections)
    occurrences = text.lower().count(kw.lower())
    sec_used = [k["keyword"] for k in cluster["secondary"] if _covers(text, k["keyword"], 1.0)]
    slug_ok = len(set(tokens(kw)) - {"a", "an", "the", "is", "there", "any"} - set(slug.split("-"))) <= 1

    def check(name, ok, value, target):
        return {"check": name, "pass": bool(ok), "value": value, "target": target}

    return [
        check("SEO title length", len(draft.seo_title) <= 60, f"{len(draft.seo_title)} chars", "≤ 60 chars"),
        check("Primary keyword in SEO title", _covers(draft.seo_title, kw), draft.seo_title, "contains keyword"),
        check("Meta description length", 120 <= len(draft.meta_description) <= 160, f"{len(draft.meta_description)} chars", "120-160 chars"),
        check("Primary keyword in meta description", _covers(draft.meta_description, kw), "", "contains keyword"),
        check("Primary keyword in H1", _covers(draft.h1, kw), draft.h1, "contains keyword"),
        check("Primary keyword in first 100 words", _covers(first_100, kw), "", "contains keyword"),
        check("Keyword in URL slug", slug_ok, slug, "main keyword words"),
        check("Exact primary keyword uses", 2 <= occurrences <= 12, occurrences, "2-12 (natural, no stuffing)"),
        check("Secondary keywords used", len(sec_used) >= max(1, len(cluster["secondary"]) // 2),
              f"{len(sec_used)}/{len(cluster['secondary'])}", "≥ half"),
        check("Word count", words >= 900, words, "≥ 900 words"),
        check("Heading structure", h2 >= 4 and h3 >= 3, f"{h2} H2 / {h3} H3", "≥ 4 H2 and ≥ 3 H3"),
        check("FAQs", len(draft.faqs) >= 4, len(draft.faqs), "≥ 4"),
        check("Internal links", len(draft.internal_links) >= 3, len(draft.internal_links), "≥ 3 valid links"),
        check("Image alt text", all(0 < len(i.alt_text) <= 125 for i in draft.images) and draft.images,
              f"{len(draft.images)} images", "every image has alt ≤ 125 chars"),
    ]


def publish(slug, draft, plan, cluster, research_summary, audit_summary, qa, mode, course_url):
    created = datetime.now()
    faq_schema = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f.question, "acceptedAnswer": {"@type": "Answer", "text": f.answer}}
        for f in draft.faqs]}
    html = env.get_template("blog.html").render(
        d=draft, slug=slug, cluster=cluster, course_url=course_url, faq_schema=faq_schema,
        created=created.strftime("%d %B %Y"), created_iso=created.isoformat(timespec="seconds"),
        minutes=max(1, round(len(body_text(draft).split()) / 200)),
    )
    folder = OUTPUT_DIR / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(html, encoding="utf-8")
    meta = {
        "slug": slug, "created_at": created.isoformat(timespec="seconds"), "mode": mode,
        "seo_title": draft.seo_title, "primary_keyword": cluster["primary"]["keyword"],
        "secondary_keywords": [k["keyword"] for k in cluster["secondary"]],
        "research": research_summary, "content_audit": audit_summary, "cluster": cluster,
        "plan": plan.model_dump(), "draft": draft.model_dump(), "seo_checks": qa,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return folder
