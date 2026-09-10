import os

from dotenv import load_dotenv

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
DATASET_ID = os.getenv("DATASET_ID")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
SHEET_NAME = os.getenv("SHEET_NAME", "Job Scrapping")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
