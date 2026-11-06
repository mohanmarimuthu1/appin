"""Steps 2b + 3 - content plan (topic, slug, outline) and blog generation.

Mode "claude": Claude (claude-opus-5-5) via the Anthropic SDK with structured outputs,
so the plan and the draft come back as validated Pydantic objects.
Mode "offline": deterministic templates, used when no ANTHROPIC_API_KEY is set (or the
API call fails), so the end-to-end demo always runs.
"""
import os

from pydantic import BaseModel

from .research import INFORMATIONAL_START, tokens

MODEL = "claude-opus-5-5"


# ---------- schemas shared by both modes ----------
class OutlineSection(BaseModel):
    h2: str
    h3: list[str]


class BlogPlan(BaseModel):
    topic: str
    slug: str
    target_audience: str
    search_intent: str
    angle: str
    differentiation: str  # why this does not duplicate existing Appin posts
    outline: list[OutlineSection]


class SubSection(BaseModel):
    heading: str
    paragraphs: list[str]
    bullets: list[str]


class Section(BaseModel):
    heading: str
    paragraphs: list[str]
    bullets: list[str]
    subsections: list[SubSection]


class FAQ(BaseModel):
    question: str
    answer: str


class InternalLink(BaseModel):
    anchor_text: str
    url: str
    placement: str


class ImageSuggestion(BaseModel):
    placement: str
    description: str
    alt_text: str
    file_name: str


class CTA(BaseModel):
    heading: str
    text: str
    button_text: str


class BlogDraft(BaseModel):
    seo_title: str
    meta_description: str
    h1: str
    intro: list[str]
    sections: list[Section]
    conclusion: list[str]
    faqs: list[FAQ]
    internal_links: list[InternalLink]
    images: list[ImageSuggestion]
    cta: CTA


def llm_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("BLOG_AGENT_MODE") != "offline"


# ---------- Claude mode ----------
SYSTEM = """You are an SEO content strategist and writer for Appin Technology, a training
institute in Coimbatore, Tamil Nadu that offers a Digital Marketing Course
(https://appincoimbatore.com/digital-marketing-course-in-coimbatore/).
Write for Indian students, freshers and career-switchers. Rules:
- Original, specific, genuinely useful content; no filler or keyword stuffing.
- Use the primary keyword naturally in the H1, the first 100 words, one H2 and the
  meta description. Work each secondary keyword in once where it reads naturally.
- Never invent statistics, fees, placement numbers, rankings or testimonials for Appin.
  Salary figures may only be given as approximate ranges and must be labelled as indicative.
- Internal links must use only URLs from the provided list."""


def _call_claude(prompt, schema):
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"Claude returned no usable output (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def plan_with_claude(cluster, related_titles):
    secondary = ", ".join(k["keyword"] for k in cluster["secondary"])
    prompt = f"""Plan one blog post.
Primary keyword: {cluster['primary']['keyword']} (intent: {cluster['primary']['intent']})
Secondary keywords: {secondary}
Existing Appin posts on nearby topics (do NOT duplicate them; take a distinct angle):
{chr(10).join('- ' + t for t in related_titles)}

Return: topic (the blog title idea), an SEO-friendly slug (lowercase, hyphens, <= 60 chars,
contains the primary keyword's main words), target audience, search intent, the angle,
how it differs from the existing posts, and an outline of 5-7 H2s, each with 0-3 H3s.
Do not include FAQ or conclusion sections in the outline (they are added separately)."""
    return _call_claude(prompt, BlogPlan)


def write_with_claude(plan, cluster, links):
    link_list = "\n".join(f"- {l['title']}: {l['url']}" for l in links)
    outline = "\n".join(f"H2: {s.h2}" + "".join(f"\n   H3: {h}" for h in s.h3) for s in plan.outline)
    prompt = f"""Write the full blog post from this plan.
Topic: {plan.topic}
Audience: {plan.target_audience}
Intent: {plan.search_intent}
Angle: {plan.angle}
Primary keyword: {cluster['primary']['keyword']}
Secondary keywords: {', '.join(k['keyword'] for k in cluster['secondary'])}
Outline (follow it; you may refine wording):
{outline}

Requirements:
- seo_title <= 60 characters, meta_description 140-155 characters, both with the primary keyword.
- 1,300-1,800 words of body content in total; 2-4 short paragraphs per section; use bullets where they help.
- 5-6 FAQs that real searchers ask, with concise answers.
- 4-6 internal_links chosen ONLY from this list, with natural anchor text and where to place each:
{link_list}
- 3-4 image suggestions with a descriptive file name and alt text (alt text <= 125 chars).
- A call to action promoting Appin Technology's Digital Marketing Course in Coimbatore."""
    return _call_claude(prompt, BlogDraft)


# ---------- offline mode ----------
SMALL = {"in", "for", "with", "and", "of", "to", "the", "a", "an", "vs", "at", "on", "or"}
UPPER = {"seo": "SEO", "ai": "AI", "sem": "SEM", "smm": "SMM", "12th": "12th", "10th": "10th"}


def kw_title(text):
    words = text.split()
    return " ".join(UPPER.get(w, w if (i and w in SMALL) else w.capitalize()) for i, w in enumerate(words))


def _bucket(kw):
    t = set(tokens(kw))
    if t & {"fees", "fee", "cost", "price", "much"}:
        return "fees"
    if t & {"salary", "jobs", "job", "career", "placement", "scope", "future"}:
        return "career"
    if " vs " in f" {kw} ":
        return "comparison"
    if t & {"12th", "10th", "beginners", "beginner", "after", "home", "online", "learn", "start"}:
        return "getting_started"
    return "general"


INTENT_SECTIONS = {
    "fees": ("What Decides the Fees of a Digital Marketing Course",
             ["Course length and depth", "Live projects and tool access", "Certification and placement support"]),
    "career": ("Digital Marketing Career Paths Open to Freshers",
               ["SEO and content roles", "Social media and performance marketing roles", "What salary to expect"]),
    "comparison": ("How the Options Compare", ["Skills you build", "Job market and growth", "Which suits you"]),
    "getting_started": ("Can You Really Learn Digital Marketing From Scratch?",
                        ["Who it suits", "What you need before you start"]),
    "general": ("What Digital Marketing Is and Why It Matters Now",
                ["How Coimbatore businesses use it", "Skills employers ask for"]),
}


def plan_offline(cluster, related_titles):
    kw = cluster["primary"]["keyword"]
    bucket = _bucket(kw)
    if tokens(kw)[0] in INFORMATIONAL_START:
        topic = f"{kw_title(kw)}? A Practical 2026 Guide for Coimbatore Learners"
    else:
        topic = {
            "fees": f"{kw_title(kw)}: What You Pay For and How to Compare Courses",
            "career": f"{kw_title(kw)}: Roles, Skills and How to Get Started in 2026",
            "comparison": f"{kw_title(kw)}: Which Should You Choose?",
        }.get(bucket, f"{kw_title(kw)}: A Complete Beginner's Guide for 2026")
    h2, h3 = INTENT_SECTIONS[bucket]
    return BlogPlan(
        topic=topic,
        slug="-".join(t for t in tokens(kw) if t not in {"a", "an", "the", "is", "there", "any"})[:60],
        target_audience="College students, freshers and career-switchers in Coimbatore exploring a digital marketing career",
        search_intent=cluster["primary"]["intent"],
        angle=f"Answer '{kw}' directly, then give a practical path from learning to a first job.",
        differentiation="Targets a long-tail query no existing Appin post covers; links to the course page "
                        "for the head term instead of competing with it. Nearest existing posts: "
                        + "; ".join(related_titles[:3]),
        outline=[
            OutlineSection(h2=h2, h3=h3),
            OutlineSection(h2="What a Good Digital Marketing Course Should Cover",
                           h3=["SEO and content marketing", "Google Ads and Meta Ads",
                               "Social media marketing", "Analytics, AI tools and reporting"]),
            OutlineSection(h2="How to Choose the Right Digital Marketing Course in Coimbatore",
                           h3=["Check the syllabus and live projects", "Ask about certification and placement support",
                               "Compare class format, batch size and fees"]),
            OutlineSection(h2="A Simple 90-Day Learning Roadmap",
                           h3=["Month 1: foundations", "Month 2: hands-on campaigns", "Month 3: portfolio and job prep"]),
            OutlineSection(h2="Common Mistakes Beginners Make", h3=[]),
            OutlineSection(h2="Learn Digital Marketing with Appin Technology", h3=[]),
        ],
    )


H2_COPY = {
    "What Decides the Fees of a Digital Marketing Course": "Fees vary widely between institutes, so the useful question is not only how much a course costs but what you get for it. These are the factors that drive the price and the value.",
    "Digital Marketing Career Paths Open to Freshers": "Digital marketing is one of the few fields where freshers from any degree can get hired on the strength of their skills and portfolio. These are the most common entry routes.",
    "How the Options Compare": "Both paths can lead to rewarding careers. The right choice depends on the kind of work you enjoy doing every day and the skills you want to build.",
    "Can You Really Learn Digital Marketing From Scratch?": "Yes. Most of the core tools run in a browser and many learning resources are free. What makes the difference between dabbling and getting hired is structure, feedback from experienced trainers and practice on real campaigns.",
    "What Digital Marketing Is and Why It Matters Now": "Digital marketing is the work of reaching customers through search engines, social media, email, websites and online ads, and measuring the result of every rupee spent.",
    "What a Good Digital Marketing Course Should Cover": "A job-ready course goes well beyond definitions. Look for these core modules, each taught with hands-on exercises rather than slides alone.",
    "How to Choose the Right Digital Marketing Course in Coimbatore": "Coimbatore has many training options, from weekend workshops to full job-oriented programmes. Use this checklist to compare them on the things that actually affect your outcome.",
    "A Simple 90-Day Learning Roadmap": "Whether you study at home, online or in a classroom, a clear plan keeps you moving. Here is a realistic three-month path for a complete beginner.",
    "Common Mistakes Beginners Make": "Most learners who stall do not lack talent; they fall into a few predictable traps. Avoiding these will save you months.",
}
H2_BULLETS = {
    "Common Mistakes Beginners Make": [
        "Collecting certificates without running a single real campaign",
        "Trying to master every platform at once instead of going deep on two or three",
        "Ignoring analytics, so you cannot explain what worked and why",
        "Waiting until the course ends to build a portfolio instead of documenting work from week one",
        "Copying AI-generated content without editing it for accuracy, tone and search intent",
    ],
}

H3_COPY = {
    "Course length and depth": "Short crash courses cover the basics in a few weeks, while job-oriented programmes run for two to four months and include practice. Compare the number of hours and modules, not just the price.",
    "Live projects and tool access": "Courses that let you run real campaigns, use paid tools and work on live client projects cost more to deliver, but they are what employers look for in a portfolio.",
    "Certification and placement support": "Check which certificates are included (for example Google Ads or Meta Blueprint preparation) and what placement help actually means: mock interviews, referrals or only a job list.",
    "SEO and content roles": "SEO executives research keywords, optimise pages and track rankings. Content marketers plan and write blogs, landing pages and email campaigns that bring in organic traffic.",
    "Social media and performance marketing roles": "Social media executives manage brand pages and creatives, while performance marketers run and optimise paid campaigns on Google and Meta against targets such as cost per lead.",
    "What salary to expect": "As an indicative range only, entry-level digital marketing roles in Coimbatore often start around ₹2-3.5 lakh per year, rising with proven results and specialisation. Check current listings on job portals for up-to-date figures.",
    "Skills you build": "Digital marketing combines analytical skills (data, testing, budgets) with creative skills (copy, design, storytelling), so it suits people who enjoy both.",
    "Job market and growth": "Almost every business now needs an online presence, which keeps demand steady for people who can bring in measurable leads and sales.",
    "Which suits you": "If you like measurable results, experimenting and working with brands, digital marketing is a strong fit.",
    "Who it suits": "Digital marketing has no coding requirement, so students from commerce, arts, science and engineering backgrounds can all learn it. Curiosity and consistent practice matter more than your degree.",
    "What you need before you start": "A laptop, a reliable internet connection and a few hours a week. A personal blog or social page to practise on helps you learn faster than theory alone.",
    "How Coimbatore businesses use it": "Manufacturers, textile brands, clinics, schools and startups in Coimbatore use search, social media and ads to reach customers across India and abroad.",
    "Skills employers ask for": "Job listings commonly mention SEO, Google Ads, Meta Ads, content writing, analytics and, increasingly, the ability to use AI tools efficiently.",
    "SEO and content marketing": "Learn keyword research, on-page optimisation, technical basics and how to write content that ranks and converts.",
    "Google Ads and Meta Ads": "Set up search, display and social campaigns, choose audiences, write ad copy and manage budgets against clear goals.",
    "Social media marketing": "Plan content calendars, create engaging posts and reels, and grow communities on Instagram, LinkedIn and YouTube.",
    "Analytics, AI tools and reporting": "Use Google Analytics 4 and Search Console to measure results, and AI tools to speed up research, copywriting and reporting.",
    "Check the syllabus and live projects": "Ask for the module-by-module syllabus and confirm you will work on real or simulated client projects, not only slides.",
    "Ask about certification and placement support": "Find out which certificates you earn, whether internships are offered and how the institute supports interviews and referrals.",
    "Compare class format, batch size and fees": "Classroom, online and hybrid formats suit different schedules. Smaller batches mean more trainer attention. Compare total fees against hours and support included.",
    "Month 1: foundations": "Learn how search engines, social platforms and ads work. Set up a practice website or page and install analytics.",
    "Month 2: hands-on campaigns": "Run small SEO, social and paid campaigns, track results weekly and learn from what does not work.",
    "Month 3: portfolio and job prep": "Document your campaigns as case studies, earn certifications and practise interviews for executive-level roles.",
}


def write_offline(plan, cluster, links):
    kw = cluster["primary"]["keyword"]
    secondary = [k["keyword"] for k in cluster["secondary"]]
    sec = (secondary + [kw] * 6)[:6]

    intro = [
        f"If you have been searching “{kw}”, you are probably weighing whether digital marketing is the right next step "
        "and how to get started without wasting time or money. This guide answers that question directly and gives you a practical path.",
        "We cover what to learn, how to choose a course in Coimbatore, a 90-day roadmap and the questions students ask us most often.",
    ]
    sec_lines = [
        f"Many learners also ask “{sec[0]}”; the short answer is that structured practice matters more than where you start.",
        f"When people search for {sec[1]}, they usually want a clear syllabus and proof that the skills lead to jobs.",
        f"This is also why “{sec[2]}” is such a common question among students and freshers.",
        f"If {sec[3]} is on your mind, look for programmes that combine theory with live projects.",
        f"Questions like “{sec[4]}” come down to the same thing: practical skills plus a portfolio.",
        f"Keep “{sec[5]}” in mind as you compare options - the right course should answer it clearly.",
    ]
    sections = []
    for i, o in enumerate(plan.outline):
        if o.h2.startswith("Learn Digital Marketing with Appin"):
            paras = ["Appin Technology's Digital Marketing Course in Coimbatore is built around hands-on practice: "
                     "you work with the same tools and campaign types employers use, guided by working trainers.",
                     "You can ask the team for the current syllabus, batch timings, fees and internship options before you decide."]
            bullets = ["Practical, project-based modules", "SEO, Google Ads, Meta Ads, social media and analytics",
                       "Classroom and online options", "Internship and career guidance"]
        else:
            paras = [H2_COPY.get(o.h2, ""), sec_lines[i % len(sec_lines)]]
            bullets = H2_BULLETS.get(o.h2, [])
        subs = [SubSection(heading=h, paragraphs=[H3_COPY.get(h, "")], bullets=[]) for h in o.h3]
        sections.append(Section(heading=o.h2, paragraphs=paras, bullets=bullets, subsections=subs))

    course = links[0]["url"]
    chosen_links = [InternalLink(anchor_text="digital marketing course in Coimbatore", url=course,
                                 placement="Learn Digital Marketing with Appin Technology section")]
    for l in links[1:5]:
        chosen_links.append(InternalLink(anchor_text=l["title"], url=l["url"], placement="Related reading box"))

    seo_title = f"{kw_title(kw)} | Appin Technology"
    if len(seo_title) > 60:
        seo_title = kw_title(kw)[:60]
    is_question = tokens(kw)[0] in INFORMATIONAL_START
    meta = (f"{kw_title(kw)}{'?' if is_question else ':'} Learn what to study, how to choose a course in Coimbatore "
            "and a 90-day roadmap to your first digital marketing job.")
    if is_question:
        first_faq = FAQ(question=f"{kw_title(kw)}?", answer="Yes. With a structured course, regular practice and a few real projects, most beginners can build job-ready digital marketing skills - at home, online or in a classroom.")
    else:
        first_faq = FAQ(question=f"What should I know about {kw}?", answer="Focus on practical skills, live projects and a portfolio. Those matter more to Coimbatore employers than certificates alone.")
    return BlogDraft(
        seo_title=seo_title,
        meta_description=meta[:158],
        h1=plan.topic,
        intro=intro,
        sections=sections,
        conclusion=[f"Getting clarity on {kw} is the first step. Pick a course with a practical syllabus, live projects and "
                    "real placement support, then practise consistently for three months - that combination is what gets freshers hired."],
        faqs=[
            first_faq,
            FAQ(question="Do I need a technical background to learn digital marketing?", answer="No. Digital marketing does not require coding. Students from any stream can learn it with practice."),
            FAQ(question="How long does it take to become job-ready?", answer="With a structured course and regular practice, most learners can apply for entry-level roles within three to four months."),
            FAQ(question="Which tools should a beginner learn first?", answer="Start with Google Search Console, Google Analytics 4, Google Ads, Meta Ads Manager and a simple website platform such as WordPress."),
            FAQ(question="Does Appin Technology offer placement support?", answer="Appin Technology provides career guidance and internship opportunities; contact the team for current placement support details."),
        ],
        internal_links=chosen_links,
        images=[
            ImageSuggestion(placement="Hero, below the H1", description="Students working on a digital marketing campaign dashboard in a Coimbatore classroom",
                            alt_text=f"Students learning digital marketing in Coimbatore - {kw}", file_name=f"{plan.slug}-hero.webp"),
            ImageSuggestion(placement="Course coverage section", description="Infographic of course modules: SEO, Google Ads, Meta Ads, social media, analytics",
                            alt_text="Infographic of digital marketing course modules: SEO, ads, social media and analytics", file_name="digital-marketing-course-modules.webp"),
            ImageSuggestion(placement="90-day roadmap section", description="Three-step timeline graphic for month 1, 2 and 3",
                            alt_text="90-day digital marketing learning roadmap for beginners", file_name="digital-marketing-90-day-roadmap.webp"),
        ],
        cta=CTA(heading="Start Your Digital Marketing Career with Appin Technology",
                text="Join Appin Technology's Digital Marketing Course in Coimbatore and learn SEO, Google Ads, Meta Ads, social media and analytics through hands-on projects.",
                button_text="Explore the Course"),
    )
