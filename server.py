import json
import queue
import threading

from flask import Flask, Response, render_template, request

from main import run_job_scraper
from paths import BASE_DIR, read_resume, write_resume

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/resume", methods=["GET", "POST"])
def manage_resume():
    if request.method == "POST":
        data = request.json or {}
        content = data.get("content", "")
        try:
            write_resume(content)
            return {"success": True, "message": "Resume updated successfully."}
        except Exception as e:
            return {"success": False, "message": str(e)}, 500

    try:
        return {"success": True, "content": read_resume()}
    except Exception as e:
        return {"success": False, "message": str(e)}, 500


@app.route("/api/run")
def run_scraper():
    count = int(request.args.get("count", 10))
    min_score = int(request.args.get("min_score", 80))

    def generate():
        q = queue.Queue()

        def callback(event):
            q.put(event)

        def thread_worker():
            try:
                run_job_scraper(count=count, min_score=min_score, status_callback=callback)
            except Exception as e:
                q.put({"type": "log", "message": f"Fatal execution error: {str(e)}", "status": "error"})
            finally:
                q.put(None)

        thread = threading.Thread(target=thread_worker)
        thread.start()

        while True:
            event = q.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    print("Starting Flask web server on http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=True)
