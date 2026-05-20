"""
app.py
──────
Web UI for ReverseEdtech pipeline.
Serves a single-page dark terminal-style interface with real-time output streaming.
"""

import os
import sys
import json
import subprocess
import pandas as pd
from flask import Flask, render_template, request, Response, stream_with_context, jsonify

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_CSV = os.path.join(BASE_DIR, "outputs", "corpus_index.csv")

_running = False


@app.route("/")
def index():
    """Serve the main UI page."""
    return render_template("index.html")


@app.route("/run")
def run():
    """Stream pipeline execution as server-sent events (SSE)."""
    global _running
    if _running:
        return Response("data: [!] Pipeline already running.\n\ndata: __done__\n\n",
                        mimetype="text/event-stream")

    query = request.args.get("query", "").strip()
    n = request.args.get("n", "20")
    threshold = request.args.get("threshold", "45")

    if not query:
        return Response("data: [!] No query provided.\n\ndata: __done__\n\n",
                        mimetype="text/event-stream")

    def generate():
        global _running
        _running = True
        try:
            cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "pipeline.py"),
                "-q", query,
                "-n", n,
                "--threshold", threshold,
            ]

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=BASE_DIR,
                env=env,
                bufsize=1,
            )

            for line in proc.stdout:
                yield f"data: {json.dumps(line.rstrip())}\n\n"

            proc.wait()
            yield "data: __done__\n\n"
        finally:
            _running = False

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/corpus")
def corpus():
    """Return corpus_index.csv as JSON."""
    if not os.path.exists(INDEX_CSV):
        return jsonify([])
    try:
        df = pd.read_csv(INDEX_CSV, encoding="utf-8")
        # Sort by quality score descending
        df = df.sort_values("quality_score", ascending=False)
        return jsonify(df.to_dict(orient="records"))
    except Exception:
        return jsonify([])


if __name__ == "__main__":
    app.run(debug=True, threaded=True, port=5000)
