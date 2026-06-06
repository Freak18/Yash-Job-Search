# Start

See **Architecture.md** for system design and component details.

## Prerequisites

Create a `.env` file in this directory with:

```text
APIFY_TOKEN=
OPENROUTER_API_KEY=
SHEET_NAME=Job Scrapping
GOOGLE_CREDENTIALS=
```

`GOOGLE_CREDENTIALS` should be the full service-account JSON on a single line.

## Local

```bash
cd job-automation
source venv/bin/activate
pip install -r requirements.txt
python server.py
```

Or:

```bash
./start.sh
```

Open **http://localhost:8000**

## CLI only (no UI)

```bash
python main.py
```

## Vercel

1. Set the Vercel project root to `job-automation`.
2. Add the same environment variables in the Vercel dashboard.
3. Deploy from GitHub or run `vercel` from this folder.
