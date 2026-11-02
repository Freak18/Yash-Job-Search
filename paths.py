import json
import os
import re
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


def get_companies_path() -> Path:
    if os.getenv("VERCEL"):
        tmp_path = Path("/tmp/Companies.txt")
        default_companies = BASE_DIR / "Companies.txt"
        if not tmp_path.exists() and default_companies.exists():
            shutil.copy(default_companies, tmp_path)
        return tmp_path
    return BASE_DIR / "Companies.txt"


def read_companies_raw() -> str:
    path = get_companies_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


KNOWN_COMPANY_CLEANUPS = {
    "charles schwab’s": "Charles Schwab",
    "charles schwabs": "Charles Schwab",
    "marriott tech accelerator": "Marriott",
    "adp global": "ADP",
    "costco it": "Costco",
    "gap inc": "Gap",
    "duestche borse group": "Deutsche Boerse",
    "service now": "ServiceNow",
    "johnson & johnson innovative medicine": "Johnson & Johnson",
    "de shaw and co": "D. E. Shaw",
    "t mobile": "T-Mobile",
    "warner bros": "Warner Bros",
}

SHORT_ACRONYMS = {"ice", "msd", "tjx", "cibc", "adp", "ge"}

COMPANY_LINKEDIN_IDS = {
    "t-mobile": "1392",
    "wells fargo": "1235",
    "pepsico": "1431",
    "vanguard": "3184",
    "charles schwab": "1855",
    "warner bros": "73234923",
    "marriott": "2311",
    "ge vernova": "82315716",
    "adp": "1463",
    "costco": "163225",
    "bank of america": "1123",
    "experian": "2534",
    "gap": "1677",
    "cibc": "1826",
    "deutsche boerse": "163430",
    "aa tech hub": "2640",
    "bristol myers squibb": "1773",
    "tjx": "5121",
    "chubb": "1269",
    "swiss re": "3845",
    "servicenow": "29352",
    "stripe": "2135371",
    "atlassian": "22688",
    "amazon": "1586",
    "google": "1441",
    "microsoft": "1035",
    "apple": "162479",
    "idfc first bank": "21175",
    "idfc bank": "21175",
    "johnson & johnson": "1207",
    "honeywell": "1344",
    "amgen": "2068",
    "d. e. shaw": "2408262",
    "de shaw": "2408262",
    "broadcom": "3072",
    "wise": "1769571",
    "ice": "252398",
    "micron": "3690",
    "micron technology": "3690",
    "fanatics": "68543",
    "factset": "163755",
    "msd": "2848937",
    "macquarie group": "3537",
    "teradata": "1466",
}


def load_company_ids_mapping() -> dict:
    mapping = {k.lower(): v for k, v in COMPANY_LINKEDIN_IDS.items()}
    json_path = BASE_DIR / "company_ids.json"
    if json_path.exists():
        try:
            file_data = json.loads(json_path.read_text(encoding="utf-8"))
            for k, v in file_data.items():
                if v:
                    mapping[k.strip().lower()] = str(v).strip()
        except Exception:
            pass
    return mapping


def get_target_company_ids() -> list[str]:
    mapping = load_company_ids_mapping()
    target_names = load_target_companies()
    ids = []
    seen = set()
    for name in target_names:
        norm = name.strip().lower()
        cid = mapping.get(norm)
        if not cid:
            # Fallback check against keys
            for k, v in mapping.items():
                if k in norm or norm in k:
                    cid = v
                    break
        if cid and cid not in seen:
            seen.add(cid)
            ids.append(cid)
    return ids



def load_target_companies() -> list[str]:
    raw = read_companies_raw()
    companies = []
    seen = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("companies"):
            continue
        cleaned = re.sub(r"^\d+\s*[\.\)]\s*", "", line).strip()
        if not cleaned:
            continue
        normalized = KNOWN_COMPANY_CLEANUPS.get(cleaned.lower(), cleaned)
        if normalized.lower() not in seen:
            seen.add(normalized.lower())
            companies.append(normalized)
    return companies


def is_target_company(company_name: str, target_companies: list[str]) -> bool:
    if not company_name or not company_name.strip():
        return False

    inc_lower = company_name.strip().lower()
    inc_words = set(re.findall(r"\b\w+\b", inc_lower))
    inc_norm = re.sub(r"[^a-z0-9]", "", inc_lower)

    for target in target_companies:
        t_lower = target.strip().lower()
        t_norm = re.sub(r"[^a-z0-9]", "", t_lower)

        # For short acronyms (e.g. ICE, MSD, TJX, CIBC, ADP, GE), require full word match
        if t_lower in SHORT_ACRONYMS or len(t_norm) <= 3:
            if t_lower in inc_words or t_norm in inc_words:
                return True
            continue

        # For multi-word / longer target names, check normalized substring
        if t_norm in inc_norm:
            return True

        # Word boundary regex match
        pattern = r"\b" + re.escape(t_lower) + r"\b"
        if re.search(pattern, inc_lower):
            return True

    return False

