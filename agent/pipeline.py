"""The agent: runs every step end-to-end and yields progress events for the UI."""
import time

from . import planner, publisher, research, writer


def _trim(k):
    keep = ("keyword", "intent", "verified", "estimated", "flags", "relevance", "opportunity",
            "cannibalisation", "final_score")
    return {key: k[key] for key in keep if key in k}


def run():
    t0 = time.time()
    use_llm = writer.llm_available()
    mode = f"claude ({writer.MODEL})" if use_llm else "offline templates (no ANTHROPIC_API_KEY)"
    yield {"step": "start", "message": f"Agent started - writer mode: {mode}"}

    # 1. Keyword research
    yield {"step": "research", "status": "running", "message": "Expanding seed keywords via Google Autocomplete..."}
    r = research.research_keywords()
    research_summary = {"source": r["source"], "queries_sent": r["queries_sent"],
                        "queries_ok": r["queries_ok"], "keywords_found": len(r["keywords"])}
    yield {"step": "research", "status": "done",
           "message": f"{len(r['keywords'])} real search queries found ({r['queries_ok']}/{r['queries_sent']} autocomplete calls succeeded)",
           "data": {**research_summary, "top": [_trim(k) for k in r["keywords"][:25]]}}

    # 2a. Content audit + keyword selection
    yield {"step": "select", "status": "running", "message": "Checking existing Appin content for cannibalisation..."}
    existing = planner.load_existing_content()
    cluster = planner.select_cluster(r["keywords"], existing["items"])
    audit_summary = {"source": existing["source"], "pages_checked": len(existing["items"])}
    yield {"step": "select", "status": "done",
           "message": f"Primary keyword: “{cluster['primary']['keyword']}” ({len(existing['items'])} existing pages checked)",
           "data": {**audit_summary,
                    "primary": _trim(cluster["primary"]),
                    "secondary": [_trim(k) for k in cluster["secondary"]],
                    "rejected": [_trim(k) for k in cluster["rejected_cannibalising"]],
                    "shortlist": [_trim(k) for k in cluster["shortlist"]]}}

    # 2b. Content plan
    links = planner.internal_link_candidates(cluster["primary"]["keyword"], existing["items"])
    related_titles = [l["title"] for l in links if l["type"] == "appin blog post"]
    yield {"step": "plan", "status": "running", "message": "Planning topic, slug, audience and outline..."}
    plan = None
    if use_llm:
        try:
            plan = writer.plan_with_claude(cluster, related_titles)
        except Exception as e:
            use_llm = False
            mode = "offline templates (Claude call failed)"
            yield {"step": "plan", "status": "warning", "message": f"Claude unavailable ({e}); using offline writer"}
    if plan is None:
        plan = writer.plan_offline(cluster, related_titles)
    slug = planner.unique_slug(plan.slug)
    plan.slug = slug
    yield {"step": "plan", "status": "done", "message": f"Topic: {plan.topic}", "data": plan.model_dump()}

    # 3. Blog generation
    yield {"step": "write", "status": "running",
           "message": "Writing the blog with Claude (this can take a minute)..." if use_llm else "Writing the blog..."}
    draft = None
    if use_llm:
        try:
            draft = writer.write_with_claude(plan, cluster, links)
        except Exception as e:
            mode = "offline templates (Claude call failed)"
            yield {"step": "write", "status": "warning", "message": f"Claude unavailable ({e}); using offline writer"}
    if draft is None:
        draft = writer.write_offline(plan, cluster, links)
    removed = publisher.validate_links(draft, links)
    yield {"step": "write", "status": "done",
           "message": f"Draft ready: {len(draft.sections)} sections, {len(draft.faqs)} FAQs, {len(draft.internal_links)} internal links"
                      + (f" ({len(removed)} invalid links removed)" if removed else "")}

    # 4. SEO checks + preview, 5. save
    qa = publisher.seo_checks(draft, slug, cluster)
    passed = sum(c["pass"] for c in qa)
    yield {"step": "qa", "status": "done", "message": f"SEO checks: {passed}/{len(qa)} passed", "data": qa}

    publisher.publish(slug, draft, plan, cluster, research_summary, audit_summary, qa, mode, links[0]["url"])
    yield {"step": "publish", "status": "done",
           "message": f"Blog page saved to output/blogs/{slug}/index.html in {time.time() - t0:.0f}s",
           "data": {"slug": slug, "url": f"/blog/{slug}", "mode": mode}}
