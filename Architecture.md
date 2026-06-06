# Job Automation Architecture

## Overview

This application scrapes LinkedIn jobs, scores them against a resume using AI, removes duplicates, and stores matching jobs in Google Sheets. It can be run from a Flask web dashboard or directly from the CLI.

---

# Architecture Flow

```text
Flask Dashboard (server.py)
        ↓
User sets job count + score cutoff
        ↓
SSE stream (/api/run)
        ↓
main.py orchestration
        ↓
Apify LinkedIn Scraper
        ↓
Retrieve jobs (Hyderabad searches)
        ↓
AI Resume Matching (DeepSeek via OpenRouter)
        ↓
Filter by minimum score
        ↓
Remove duplicate job links
        ↓
Google Sheet (Jobs worksheet)
```

---

# Technologies Used

## Python

Main orchestration layer.

Packages:

* apify-client
* Flask
* gspread
* openai
* python-dotenv

---

## Flask Web UI

Purpose:

* Dashboard to run the scraper, view progress, edit resume, and inspect results

Entry points:

```text
server.py          # local development
api/index.py       # Vercel serverless entrypoint
```

Routes:

```text
GET  /             Dashboard UI
GET  /api/resume   Load resume text
POST /api/resume   Save resume text
GET  /api/run      Start scraper (SSE progress stream)
```

---

## Apify

Purpose:

* Scrape LinkedIn jobs

Actor Used:

```text
curious_coder/linkedin-jobs-scraper
```

Source:

https://console.apify.com

Token Source:

```text
Apify Console
→ Settings
→ Integrations
→ API Tokens
```

Stored In:

```text
APIFY_TOKEN
```

---

## OpenRouter

Purpose:

* AI-based resume matching

Website:

https://openrouter.ai

API Key Source:

```text
OpenRouter
→ Settings
→ Keys
→ Create Key
```

Stored In:

```text
OPENROUTER_API_KEY
```

Model Used:

```text
deepseek/deepseek-chat-v3
```

---

## Google Sheets

Purpose:

* Store matched jobs

Sheet Name:

```text
Job Scrapping
```

Worksheet:

```text
Jobs
```

Columns:

```text
Job Title
Company
Job Link
Score
Posted Date
Date Added
```

---

## Google Service Account

Purpose:

* Programmatic access to Google Sheets

Creation:

```text
Google Cloud Console
→ Create Project
→ Enable:
    - Google Sheets API
    - Google Drive API
→ Create Service Account
→ Generate JSON Key
```

Stored In:

```text
GOOGLE_CREDENTIALS
```

Loaded by:

```python
sheets.py → get_gspread_client()
```

`credentials.json` is no longer used by the app. Keep it out of Git.

---

# Configuration

File:

```python
config.py
```

Loads values from `.env` using:

```python
from dotenv import load_dotenv
load_dotenv()
```

Environment variables:

```text
APIFY_TOKEN
DATASET_ID
OPENROUTER_API_KEY
SHEET_NAME
GOOGLE_CREDENTIALS
```

Local secrets live in `.env`. On Vercel, set the same variables in the project dashboard.

---

# Resume

File:

```text
resume.txt
```

Purpose:

* Used by AI to compare against job descriptions
* Editable from the web dashboard

Path handling:

```python
paths.py
```

* Local: reads/writes `resume.txt`
* Vercel: uses `/tmp/resume.txt` (ephemeral per instance)

---

# AI Scoring Logic

Input:

```text
Resume
+
Job Description
```

Output:

```text
0 - 100
```

Rules:

* Java
* Spring Boot
* Microservices
* React
* AWS
* Kafka
* Redis

increase score.

Roles focused on:

* .NET
* C#
* QA
* Power BI
* Python-only
* DevOps-only
* SAP
* Salesforce

receive low scores.

Threshold:

* Configurable in the dashboard
* Default cutoff: 80

Only jobs at or above the cutoff are stored.

---

# Duplicate Prevention

Unique Identifier:

```text
Job Link
```

Logic:

```text
If Job Link already exists in sheet
→ Skip

Else
→ Insert
```

---

# Execution Modes

## Web dashboard

```bash
python server.py
```

Steps:

1. Open the dashboard.
2. Set job count and minimum score.
3. Click **Run Scraper**.
4. Watch live logs and results via SSE.
5. Review added, duplicate, and skipped jobs.

## CLI

```bash
python main.py
```

Runs the scraper without the web UI.

---

# Project Structure

```text
.
├── api/
│   └── index.py          # Vercel entrypoint
├── templates/
│   └── index.html        # Dashboard UI
├── main.py               # Scraper orchestration
├── server.py             # Flask app
├── scorer.py             # OpenRouter scoring
├── sheets.py             # Google Sheets auth
├── paths.py              # Resume path helper
├── config.py             # Environment config
├── resume.txt
├── requirements.txt
├── vercel.json
├── start.sh
├── Start.md
├── Architecture.md
├── .env                  # local only (gitignored)
└── venv/
```

---

# Deployment

## Local

```bash
source venv/bin/activate
pip install -r requirements.txt
python server.py
```

See **Start.md** for full setup steps.

## Vercel

* Set this folder as the Vercel project root
* Entrypoint: `api/index.py`
* Routing: `vercel.json`
* Secrets: Vercel environment variables

Note: long scraper runs may hit Vercel serverless timeouts. `vercel.json` sets `maxDuration` to 300 seconds.

---

# Future Enhancements

* Naukri Scraper
* Indeed Scraper
* Email Notifications
* Daily Cron Scheduling
* Auto Resume Tailoring
* Multi-Resume Support
* Job Trend Analytics
