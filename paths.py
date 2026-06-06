import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def get_resume_path() -> Path:
    if os.getenv("VERCEL"):
        tmp_path = Path("/tmp/resume.txt")
        default_resume = BASE_DIR / "resume.txt"
        if not tmp_path.exists() and default_resume.exists():
            shutil.copy(default_resume, tmp_path)
        return tmp_path
    return BASE_DIR / "resume.txt"


def read_resume() -> str:
    path = get_resume_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_resume(content: str) -> None:
    path = get_resume_path()
    path.write_text(content, encoding="utf-8")
