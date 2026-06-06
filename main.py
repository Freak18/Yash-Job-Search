from datetime import datetime
from urllib.parse import urlparse

from apify_client import ApifyClient

from config import APIFY_TOKEN, SHEET_NAME
from scorer import get_score
from sheets import get_gspread_client

JOB_LINK_COLUMN = 3


def normalize_job_link(link: str) -> str:
    link = (link or "").strip()
    if not link:
        return ""

    parsed = urlparse(link)
    if not parsed.scheme or not parsed.netloc:
        return link.lower().rstrip("/")

    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{netloc}{path}"


def load_existing_job_links(worksheet) -> set:
    links = set()
    try:
        for raw_link in worksheet.col_values(JOB_LINK_COLUMN)[1:]:
            normalized = normalize_job_link(raw_link)
            if normalized:
                links.add(normalized)
    except Exception:
        pass
    return links


def is_duplicate_job(link: str, existing_links: set) -> bool:
    normalized = normalize_job_link(link)
    return bool(normalized) and normalized in existing_links


def run_job_scraper(count=10, min_score=80, status_callback=None):
    def emit(event_type, message, **kwargs):
        if status_callback:
            status_callback({"type": event_type, "message": message, **kwargs})
        else:
            print(f"[{event_type.upper()}] {message}")

    emit("log", f"Connecting to Google Sheets '{SHEET_NAME}'...")
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open(SHEET_NAME)
        WORKSHEET_NAME = "Jobs"
        expected_headers = [
            "Job Title",
            "Company",
            "Job Link",
            "Score",
            "Posted Date",
            "Date Added",
        ]
        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
            try:
                row1 = worksheet.row_values(1)
            except Exception:
                row1 = []
            if not row1 or row1[0] != "Job Title":
                emit("log", "Headers not found in Google Sheet. Adding them to row 1...")
                worksheet.insert_row(expected_headers, index=1)
        except Exception:
            worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows=10000, cols=10)
            worksheet.append_row(expected_headers)
    except Exception as e:
        error_msg = f"Google Sheets connection failed: {str(e)}"
        emit("log", error_msg, status="error")
        return {"error": error_msg}

    try:
        existing_links = load_existing_job_links(worksheet)
    except Exception as e:
        existing_links = set()
        emit("log", f"Warning: Failed to retrieve existing links from sheet: {str(e)}")

    emit("log", f"Loaded {len(existing_links)} existing job links for duplicate check")

    emit("log", "Starting LinkedIn Scraper...")
    try:
        client = ApifyClient(APIFY_TOKEN)
        run = client.actor("curious_coder/linkedin-jobs-scraper").call(
            run_input={
                "count": count,
                "scrapeCompany": True,
                "splitByLocation": False,
                "splitCountry": "IN",
                "urls": [
                    "https://www.linkedin.com/jobs/search/?keywords=Java%20Developer&location=Hyderabad",
                    "https://www.linkedin.com/jobs/search/?keywords=Senior%20Java%20Developer&location=Hyderabad",
                    "https://www.linkedin.com/jobs/search/?keywords=Full%20Stack%20Developer&location=Hyderabad",
                    "https://www.linkedin.com/jobs/search/?keywords=Senior%20Software%20Engineer&location=Hyderabad",
                    "https://www.linkedin.com/jobs/search/?keywords=Java%20React%20Developer&location=Hyderabad",
                ],
            }
        )
        dataset_id = run["defaultDatasetId"]
        emit("log", f"Scraper run completed. Dataset ID: {dataset_id}")
        dataset = client.dataset(dataset_id)
        items = dataset.list_items().items
    except Exception as e:
        error_msg = f"Apify scraping failed: {str(e)}"
        emit("log", error_msg, status="error")
        return {"error": error_msg}

    total_jobs = len(items)
    emit("log", f"Jobs Found: {total_jobs}")
    emit("start_processing", f"Found {total_jobs} jobs. Beginning AI scoring and filtering...", total=total_jobs)

    jobs_added = 0
    jobs_skipped = 0
    duplicate_jobs = 0
    date_added = datetime.now().strftime("%Y-%m-%d")

    for index, job in enumerate(items):
        title = job.get("title", "")
        company = job.get("companyName", "")
        link = job.get("link", "")
        posted_date = job.get("postedAt", "")
        description = job.get("descriptionText", "")

        try:
            if not link:
                jobs_skipped += 1
                emit(
                    "job_processed",
                    f"Skipped (no link): {title}",
                    title=title,
                    company=company,
                    score=0,
                    action="Skipped (No Link)",
                    link="",
                    index=index + 1,
                )
                continue

            normalized_link = normalize_job_link(link)

            if is_duplicate_job(link, existing_links):
                duplicate_jobs += 1
                emit(
                    "job_processed",
                    f"Duplicate (skipped): {title} at {company}",
                    title=title,
                    company=company,
                    score=None,
                    action="Duplicate (Skipped)",
                    link=link,
                    index=index + 1,
                )
                continue

            emit("log", f"Scoring job {index + 1}/{total_jobs}: {title} at {company}")
            score = get_score(description)

            if score < min_score:
                jobs_skipped += 1
                emit(
                    "job_processed",
                    f"Low Match Score ({score}): {title} at {company}",
                    title=title,
                    company=company,
                    score=score,
                    action=f"Skipped (Score < {min_score})",
                    link=link,
                    index=index + 1,
                )
                continue

            if is_duplicate_job(link, existing_links):
                duplicate_jobs += 1
                emit(
                    "job_processed",
                    f"Duplicate (skipped): {title} at {company}",
                    title=title,
                    company=company,
                    score=score,
                    action="Duplicate (Skipped)",
                    link=link,
                    index=index + 1,
                )
                continue

            worksheet.append_row([
                title,
                company,
                link,
                score,
                posted_date,
                date_added,
            ])

            existing_links.add(normalized_link)
            jobs_added += 1
            emit(
                "job_processed",
                f"Added: {title} at {company} (Score: {score})",
                title=title,
                company=company,
                score=score,
                action="Added to Sheet",
                link=link,
                index=index + 1,
            )

        except Exception as e:
            emit("log", f"Failed to process job '{title}': {str(e)}", status="error")

    emit("completed", "COMPLETED", added=jobs_added, skipped=jobs_skipped, duplicates=duplicate_jobs)

    return {
        "added": jobs_added,
        "skipped": jobs_skipped,
        "duplicates": duplicate_jobs,
    }


if __name__ == "__main__":
    print("Starting Job Scrapper in CLI mode...")
    run_job_scraper(count=10, min_score=80)
