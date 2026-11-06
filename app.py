"""Flask app: the "Create Blog Page" UI, the agent's live event stream, and the saved blogs."""
import json
import threading

from flask import Flask, Response, abort, jsonify, render_template, send_from_directory

from agent import pipeline, writer
from agent.planner import OUTPUT_DIR

app = Flask(__name__)
run_lock = threading.Lock()


@app.get("/")
def index():
    return render_template("index.html", llm=writer.llm_available(), model=writer.MODEL)


@app.get("/api/create")
def create():
    """Server-Sent Events: runs the whole agent and streams each step to the browser."""
    def stream():
        if not run_lock.acquire(blocking=False):
            yield f"data: {json.dumps({'step': 'error', 'message': 'The agent is already running.'})}\n\n"
            return
        try:
            for event in pipeline.run():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'message': f'{type(e).__name__}: {e}'})}\n\n"
        finally:
            run_lock.release()
        yield "data: {\"step\": \"end\"}\n\n"

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/blogs")
def blogs():
    items = []
    for meta in sorted(OUTPUT_DIR.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        m = json.loads(meta.read_text(encoding="utf-8"))
        items.append({k: m[k] for k in ("slug", "seo_title", "primary_keyword", "created_at", "mode")})
    return jsonify(items)


@app.get("/api/blogs/<slug>")
def blog_meta(slug):
    path = OUTPUT_DIR / slug / "meta.json"
    if not path.is_file() or path.parent.parent != OUTPUT_DIR:
        abort(404)
    return Response(path.read_text(encoding="utf-8"), mimetype="application/json")


@app.get("/blog/<slug>")
def blog(slug):
    if not (OUTPUT_DIR / slug / "index.html").is_file():
        abort(404)
    return send_from_directory(OUTPUT_DIR / slug, "index.html")


if __name__ == "__main__":
    app.run(debug=False, threaded=True, port=5000)
