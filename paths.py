import json
import os
import re
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

COMPANY_TYPES = ("Product", "Service")
SHORT_ACRONYMS = {"msd", "tjx", "cibc", "adp", "ge"}


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


def load_seed_companies() -> list[dict]:
    """Initial companies used to populate the Companies sheet tab the first time."""
    json_path = BASE_DIR / "company_ids.json"
    if not json_path.exists():
        return []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [
        {"name": name.strip(), "id": str(cid or "").strip(), "type": ""}
        for name, cid in data.items()
        if name.strip()
    ]


def normalize_companies(items) -> list[dict]:
    """Validate user-supplied companies: trim, dedupe by name, check ID and type."""
    cleaned = []
    seen = set()
    for item in items or []:
        name = re.sub(r"\s+", " ", str(item.get("name", ""))).strip()
        if not name:
            continue
        company_id = str(item.get("id", "")).strip()
        if company_id and not company_id.isdigit():
            raise ValueError(f"LinkedIn ID for '{name}' must be numeric.")
        raw_type = str(item.get("type", "")).strip().title()
        if raw_type and raw_type not in COMPANY_TYPES:
            raise ValueError(f"Type for '{name}' must be Product or Service.")
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"name": name, "id": company_id, "type": raw_type})
    return cleaned


def get_target_company_ids(companies: list[dict]) -> list[str]:
    ids = []
    for company in companies:
        company_id = company.get("id")
        if company_id and company_id not in ids:
            ids.append(company_id)
    return ids


def _name_matches(company_name: str, target: str) -> bool:
    inc_lower = company_name.strip().lower()
    inc_words = set(re.findall(r"\b\w+\b", inc_lower))
    inc_norm = re.sub(r"[^a-z0-9]", "", inc_lower)

    t_lower = target.strip().lower()
    t_norm = re.sub(r"[^a-z0-9]", "", t_lower)
    if not t_norm:
        return False

    # Short acronyms (MSD, TJX, CIBC, ADP, GE) need a full word match
    if t_lower in SHORT_ACRONYMS or len(t_norm) <= 3:
        return t_lower in inc_words or t_norm in inc_words

    if t_norm in inc_norm:
        return True
    return bool(re.search(r"\b" + re.escape(t_lower) + r"\b", inc_lower))


def find_matching_company(company_name: str, companies: list[dict]):
    """Return the first company entry matching the scraped company name, else None."""
    if not company_name or not company_name.strip():
        return None
    for company in companies:
        if _name_matches(company_name, company["name"]):
            return company
    return None
