import os

from dotenv import load_dotenv

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN")
DATASET_ID = os.getenv("DATASET_ID")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if GEMINI_API_KEY:
    LLM_PROVIDER = "gemini"
    LLM_API_KEY = GEMINI_API_KEY
    LLM_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
    DEFAULT_MODEL = "gemini-3.5-flash-lite"
else:
    LLM_PROVIDER = "openrouter"
    LLM_API_KEY = OPENROUTER_API_KEY
    LLM_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "openrouter/free"

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL") or os.getenv("GEMINI_MODEL") or os.getenv("LLM_MODEL", DEFAULT_MODEL)
SHEET_NAME = os.getenv("SHEET_NAME", "Job Scrapping")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
