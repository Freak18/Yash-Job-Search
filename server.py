import json
import queue
import threading

from flask import Flask, Response, render_template, request

from main import DEFAULT_DAYS_FILTER, TIME_FILTERS, run_job_scraper
from config import SHEET_NAME
from resume_parser import ResumeParseError, parse_resume_pdf
from paths import BASE_DIR, normalize_companies, read_resume, write_resume
from sheets import get_gspread_client, read_companies, write_companies

MAX_UPLOAD_BYTES = 6 * 1024 * 1024

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)


app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


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


@app.route("/api/resume/upload", methods=["POST"])
def upload_resume_pdf():
    file = request.files.get("file")
    if not file or not file.filename:
        return {"success": False, "message": "No file uploaded."}, 400
    if not file.filename.lower().endswith(".pdf"):
        return {"success": False, "message": "Only PDF files are supported."}, 400
    try:
        result = parse_resume_pdf(file.read())
        return {"success": True, **result}
    except ResumeParseError as e:
        return {"success": False, "message": str(e)}, 400
    except Exception as e:
        return {"success": False, "message": str(e)}, 500


@app.route("/api/companies", methods=["GET", "POST"])
def manage_companies():
    try:
        if request.method == "POST":
            data = request.json or {}
            try:
                companies = normalize_companies(data.get("companies", []))
            except ValueError as e:
                return {"success": False, "message": str(e)}, 400
            spreadsheet = get_gspread_client().open(SHEET_NAME)
            write_companies(spreadsheet, companies)
            return {"success": True, "companies": companies}
        spreadsheet = get_gspread_client().open(SHEET_NAME)
        return {"success": True, "companies": read_companies(spreadsheet)}
    except Exception as e:
        return {"success": False, "message": str(e)}, 500


@app.route("/api/run")
def run_scraper():
    count = int(request.args.get("jobCount", request.args.get("count", 10)))
    min_score = int(
        request.args.get("confidenceScore", request.args.get("min_score", 80))
    )
    days_filter = request.args.get("daysFilter", DEFAULT_DAYS_FILTER)
    if str(days_filter) not in TIME_FILTERS:
        days_filter = DEFAULT_DAYS_FILTER

    job_source = request.args.get("jobSource", "sheet")
    if job_source not in ("sheet", "all"):
        job_source = "sheet"
    company_type = request.args.get("companyType", "all")
    if company_type not in ("product", "all"):
        company_type = "all"

    selected_companies = None
    raw_selected = request.args.get("selectedCompanies")
    if raw_selected is not None:
        try:
            parsed = json.loads(raw_selected)
            if isinstance(parsed, list):
                selected_companies = [str(x) for x in parsed]
        except ValueError:
            selected_companies = None

    def generate():
        q = queue.Queue()

        def callback(event):
            q.put(event)

        def thread_worker():
            try:
                run_job_scraper(
                    count=count,
                    min_score=min_score,
                    days_filter=str(days_filter),
                    job_source=job_source,
                    company_type=company_type,
                    selected_companies=selected_companies,
                    status_callback=callback,
                )
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
