from datetime import datetime
from urllib.parse import quote, urlparse

from apify_client import ApifyClient

from config import APIFY_TOKEN, SHEET_NAME
from scorer import get_score
from sheets import get_gspread_client

WORKSHEET_NAME = "Jobs"
EXPECTED_HEADERS = [
    "Job Title",
    "Company",
    "Company Type",
    "Job Link",
    "Score",
    "Posted Date",
    "Date Added",
]
JOB_LINK_COLUMN = 4
DEFAULT_MIN_SCORE = 85
DEFAULT_DAYS_FILTER = "3"

TIME_FILTERS = {
    "1": "r86400",      
    "3": "r259200",     
    "4": "r345600",     
    "7": "r604800",     
    "15": "r1296000",   
    "30": "r2592000"    
}

SEARCH_KEYWORDS = [
    "Senior Java Developer",
    "Java Full Stack Developer",
    "Java Backend Developer",
    "Spring Boot Developer",
    "Java Microservices Developer",
    "Senior Backend Engineer",
    "Java React Developer",
    "Lead Java Developer",
    "Senior Software Engineer",
    "Software Engineer III",
    "Member of Technical Staff"
]

SEARCH_LOCATION = "Hyderabad"


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


def resolve_time_filter(days_filter: str) -> str:
    key = str(days_filter).strip()
    if key not in TIME_FILTERS:
        key = DEFAULT_DAYS_FILTER
    return TIME_FILTERS[key]


def build_linkedin_search_urls(days_filter: str) -> list:
    time_filter = resolve_time_filter(days_filter)
    encoded_location = quote(SEARCH_LOCATION)

    urls = []
    for keyword in SEARCH_KEYWORDS:
        encoded_keyword = quote(keyword)
        urls.append(
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={encoded_keyword}&location={encoded_location}&f_TPR={time_filter}"
        )
    return urls


def ensure_worksheet_headers(worksheet, emit) -> None:
    try:
        row1 = worksheet.row_values(1)
    except Exception:
        row1 = []

    if row1 == EXPECTED_HEADERS:
        return

    if not row1:
        worksheet.append_row(EXPECTED_HEADERS)
        emit("log", "Initialized worksheet headers.")
        return

    if row1 and row1[0] == "Job Title" and "Company Type" not in row1:
        emit("log", "Migrating sheet: inserting 'Company Type' column...")
        try:
            worksheet.insert_cols([["Company Type"]], col=3, inherit_from_before=False)
        except TypeError:
            worksheet.insert_cols([["Company Type"]], col=3)

        row1 = worksheet.row_values(1)
        if row1 != EXPECTED_HEADERS:
            end_col = chr(64 + len(EXPECTED_HEADERS))
            worksheet.update(
                range_name=f"A1:{end_col}1",
                values=[EXPECTED_HEADERS],
            )
        emit("log", "Sheet migration complete.")
        return

    if row1[0] != "Job Title":
        emit("log", "Headers not found in Google Sheet. Adding them to row 1...")
        worksheet.insert_row(EXPECTED_HEADERS, index=1)


def get_or_create_worksheet(spreadsheet, emit):
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        ensure_worksheet_headers(worksheet, emit)
        return worksheet
    except Exception:
        worksheet = spreadsheet.add_worksheet(
            title=WORKSHEET_NAME,
            rows=10000,
            cols=len(EXPECTED_HEADERS),
        )
        worksheet.append_row(EXPECTED_HEADERS)
        emit("log", f"Created worksheet '{WORKSHEET_NAME}'.")
        return worksheet


def run_job_scraper(
    count=10,
    min_score=DEFAULT_MIN_SCORE,
    days_filter=DEFAULT_DAYS_FILTER,
    status_callback=None,
):
    def emit(event_type, message, **kwargs):
        if status_callback:
            status_callback({"type": event_type, "message": message, **kwargs})
        else:
            print(f"[{event_type.upper()}] {message}")

    emit("log", f"Connecting to Google Sheets '{SHEET_NAME}'...")
    try:
        gc = get_gspread_client()
        spreadsheet = gc.open(SHEET_NAME)
        worksheet = get_or_create_worksheet(spreadsheet, emit)
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

    search_urls = build_linkedin_search_urls(days_filter)
    time_filter = resolve_time_filter(days_filter)
    emit(
        "log",
        f"Starting LinkedIn Scraper (posted within {days_filter} day(s), filter={time_filter})...",
    )
    try:
        client = ApifyClient(APIFY_TOKEN)
        run = client.actor("curious_coder/linkedin-jobs-scraper").call(
            run_input={
                "count": count,
                "scrapeCompany": True,
                "splitByLocation": False,
                "splitCountry": "IN",
                "urls": search_urls,
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
    emit(
        "start_processing",
        f"Found {total_jobs} jobs. Beginning AI scoring and filtering...",
        total=total_jobs,
    )

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
            score_result = get_score(
                description,
                company_name=company,
                log_callback=lambda msg, status="info": emit("log", msg, status=status)
            )
            score = score_result["score"]
            company_type = score_result["company_type"]

            if score < min_score:
                jobs_skipped += 1
                emit(
                    "job_processed",
                    f"Low Match Score ({score}, {company_type}): {title} at {company}",
                    title=title,
                    company=company,
                    score=score,
                    company_type=company_type,
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
                    company_type=company_type,
                    action="Duplicate (Skipped)",
                    link=link,
                    index=index + 1,
                )
                continue

            worksheet.append_row([
                title,
                company,
                company_type,
                link,
                score,
                posted_date,
                date_added,
            ])

            existing_links.add(normalized_link)
            jobs_added += 1
            emit(
                "job_processed",
                f"Added: {title} at {company} (Score: {score}, Type: {company_type})",
                title=title,
                company=company,
                score=score,
                company_type=company_type,
                action="Added to Sheet",
                link=link,
                index=index + 1,
            )

        except Exception as e:
            jobs_skipped += 1
            emit(
                "log",
                f"Failed to process job '{title}': {str(e)}",
                status="error",
            )

    emit(
        "completed",
        "COMPLETED",
        added=jobs_added,
        skipped=jobs_skipped,
        duplicates=duplicate_jobs,
    )

    return {
        "added": jobs_added,
        "skipped": jobs_skipped,
        "duplicates": duplicate_jobs,
    }


if __name__ == "__main__":
    print("Starting Job Scrapper in CLI mode...")
    run_job_scraper(count=10, min_score=DEFAULT_MIN_SCORE)
