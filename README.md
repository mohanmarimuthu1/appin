# AI SEO Blog Creation Agent: Digital Marketing Course in Coimbatore

A working prototype for the Appin Technology AI Agent Developer assignment.
One click on **Create Blog Page** runs the full agent: keyword research, keyword selection, a content audit against Appin's existing posts, a content plan, the AI-written blog, SEO checks, a preview, and a saved HTML page in the local test environment.

Nothing is written to appincoimbatore.com. The agent only *reads* the site's public post list (WordPress REST API) to avoid duplicate topics.

---

## Quick start (Windows / macOS / Linux)

```bash
cd appin
pip install -r requirements.txt

# Optional: use Claude for planning + writing (otherwise offline templates are used)
#   PowerShell:  $env:ANTHROPIC_API_KEY = "sk-ant-..."
#   bash:        export ANTHROPIC_API_KEY=sk-ant-...

python app.py
```

Open **http://127.0.0.1:5000** and click **Create Blog Page**.

- Generated pages are served at `http://127.0.0.1:5000/blog/<slug>`.
- Files are saved in `output/blogs/<slug>/index.html`, plus `meta.json` with the full research trail.
- Each click picks the *next* best keyword. Blogs already generated count as existing content, so the agent never targets the same keyword twice.

| Environment variable | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Enables Claude (`claude-opus-5-5`) for the plan and the blog |
| `BLOG_AGENT_MODE=offline` | Forces the offline template writer even if a key is set |

---

## How it works

```
[Create Blog Page] ──SSE──> Flask /api/create ──> agent/pipeline.py
   1. research.py   Google Autocomplete expansion → score keywords (verified vs estimated)
   2. planner.py    load existing Appin content → cannibalisation check → pick keyword cluster
   3. writer.py     plan (topic, slug, audience, outline) → full blog (Claude or offline)
   4. publisher.py  validate links → 14 SEO checks → render HTML + JSON-LD
   5. publisher.py  save output/blogs/<slug>/ → preview in the UI
```

### 1. Keyword research (`agent/research.py`)
- Starts from 10 seed phrases (for example "digital marketing course in coimbatore" and "digital marketing course fees"). Each seed is combined with modifiers (for, with, vs, online, after), plus 5 question seeds. That gives 65 Google Autocomplete calls and about 300 unique real queries.
- **Verified data:** the keyword exists in Google Autocomplete (real searches people type), its autocomplete rank, and how many seed queries surfaced it.
- **Estimated data** (labelled in the UI):
  - *Volume tier:* from autocomplete rank, frequency across seeds, and keyword length.
  - *Difficulty:* head terms and commercial terms are harder; long-tail questions are easier.
  - *Intent:* informational, commercial, comparison, job search, or navigational (brand).
- Relevance rules penalise keywords for other cities (Chennai, Bangalore and so on), other languages, competitor brands, and "free" seekers. They boost local Coimbatore intent.
- `opportunity = relevance × volume × (1 − difficulty) × blog-fit × local-boost`
- If Google is unreachable, the agent falls back to a saved keyword snapshot, labelled "not live-verified".

### 2. Content planning and cannibalisation (`agent/planner.py`)
- Existing content is made up of:
  - about 300 Appin blog posts (live from `/wp-json/wp/v2/posts`, cached for 24h, with a bundled snapshot as fallback);
  - Appin's key landing pages (course pages, internship page, contact page);
  - every blog this agent has already generated.
- For each candidate keyword the planner scores its overlap with every existing title: coverage of the keyword's words, Jaccard similarity, and whether the *distinctive* words are covered.
  - **High** risk: the keyword is rejected. The UI shows which page it conflicts with. For example, "how long does it take to learn digital marketing" already exists as a post.
  - **Medium** risk: the keyword is penalised.
- The head term "digital marketing course in coimbatore" is always rejected because the course page owns it. Blogs target long-tail queries and link back to the course page. This is the standard hub-and-spoke SEO structure.
- **Primary keyword:** the highest-scoring candidate with no conflict. **Secondary cluster:** related keywords that share its distinctive words or intent, with near-duplicates removed.

### 3. AI blog generation (`agent/writer.py`)
- Two Claude calls with **structured outputs**: Pydantic schemas `BlogPlan` and `BlogDraft`, so the response is validated JSON rather than free text.
  - Call 1 (plan): topic, slug, audience, search intent, angle, why it isn't a duplicate, and an H2/H3 outline.
  - Call 2 (write): SEO title, meta description, H1, sections, FAQs, internal links, image suggestions with alt text, and the CTA.
- Guardrails in the system prompt:
  - no invented statistics, fees, placement numbers or testimonials;
  - salary figures only as labelled indicative ranges;
  - internal links only from the supplied list of real Appin URLs. The code also removes any link that isn't on that list.
- **Offline mode:** deterministic templates fill the same schema. The demo works without an API key, and the agent falls back to it automatically if the Claude call fails.

### 4. SEO checks and the page (`agent/publisher.py`, `templates/blog.html`)
- 14 automated checks:
  - title length ≤ 60 characters; meta description 120–160 characters;
  - keyword in the title, meta, H1, first 100 words and slug;
  - exact keyword uses between 2 and 12 (no stuffing); at least half the secondary keywords used;
  - word count ≥ 900; at least 4 H2s and 3 H3s; at least 4 FAQs; at least 3 internal links; every image has alt text.
- The page includes:
  - semantic headings, meta description and keywords, canonical and Open Graph tags;
  - **BlogPosting** and **FAQPage** JSON-LD;
  - image placeholders showing the suggested image, alt text and file name;
  - a related-reading box and the Appin course CTA.
- `noindex` and a banner mark it as a test-environment page.

---

## Project layout

```
app.py                      Flask: UI, SSE stream, blog routes
agent/research.py           Step 1 keyword research + scoring
agent/planner.py            Step 2 content audit, cannibalisation, cluster selection
agent/writer.py             Step 3 plan + blog (Claude structured outputs / offline)
agent/publisher.py          Steps 4-5 SEO checks, render, save
agent/pipeline.py           Orchestrates all steps, yields progress events
templates/index.html        One-page UI with the Create Blog Page button
templates/blog.html         Generated blog page template
data/sample_keywords.json   Offline fallback keyword snapshot
data/sample_existing_posts.json  Offline snapshot of Appin's post titles
output/blogs/<slug>/        Generated pages (index.html + meta.json)
```

## Limitations and next steps
- Real search volume and keyword difficulty need a paid API (Google Ads Keyword Planner, DataForSEO, Semrush). `research.py` is the single place to plug one in. Its numbers would then move from "estimated" to "verified".
- Cannibalisation uses title-level lexical overlap. Embeddings over full post content would catch paraphrased duplicates.
- Image generation and CMS publishing (for example a WordPress draft through the REST API on a test site) are natural next steps. They are left out because the brief forbids touching Appin's site.
