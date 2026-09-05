import json
import logging
import re
import time
from typing import Any, Dict, Optional, Union

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from config import OPENROUTER_API_KEY
from paths import read_resume

logger = logging.getLogger(__name__)

VALID_COMPANY_TYPES = frozenset({"Product", "Service", "Unknown"})
DEFAULT_SCORE_RESULT = {"score": 0, "company_type": "Unknown"}

_client: Optional[OpenAI] = None
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY environment variable is not set")
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
    return _client


def _build_prompt(resume: str, job_description: str, company_name: str) -> str:
    company_display = company_name.strip() or "Unknown"
    return f"""
CRITICAL REQUIREMENT: RESPOND WITH ONLY THE RAW JSON OBJECT. DO NOT OUTPUT ANY PREAMBLE, REASONING, OR THINKING TEXT.

You are an extremely strict technical recruiter evaluating job fit.

==================================================
CANDIDATE RESUME
==================================================

{resume}

==================================================
JOB DETAILS
==================================================

Company Name: {company_display}

Job Description:
{job_description}

==================================================
TASK
==================================================

Perform TWO independent evaluations:

1. RESUME MATCH — compare the candidate's resume against the job description only.
   - Score ONLY based on the job description.
   - Ignore the job title completely.
   - Be extremely strict.

2. COMPANY TYPE — infer whether the employer is primarily a Product, Service, or Unknown company
   using your general knowledge of the company name and any context in the job description.
   - Do NOT use a fixed lookup list; reason from what you know about the business model.
   - Product: builds and sells its own software/products (e.g. Google, Stripe, Datadog).
   - Service: IT consulting, outsourcing, staffing, or body-shop model (e.g. TCS, Infosys, Accenture).
   - Unknown: insufficient information or ambiguous (e.g. lesser-known startup, unclear employer).

==================================================
RESUME MATCH — EXPERIENCE AND SKILLS REQUIREMENTS
==================================================

Evaluate the required years of experience and skills:
- The candidate's resume shows approximately 7 years of experience.
- The required experience for the job MUST NOT be more than 8 years.
- If the job description requires more than 8 years of experience (e.g. 9+, 10+, 12+ years, or Senior/Lead/Architect roles demanding >8 years), the match is poor and you MUST reduce the resume_match_score drastically (it should not exceed 50).
- If the job description requires 8 years of experience or less (e.g. 5-8 years, 3-5 years, or unspecified mid-senior level), it matches the candidate's experience.
- Carefully evaluate core stack matching: verify if they require Java, Spring Boot, Microservices, and optionally React.

==================================================
RESUME MATCH — STRONG POSITIVE SIGNALS
==================================================

Give strong positive weight if the job description contains:

- Java
- Spring Boot
- Microservices
- React
- AWS
- Kafka
- Redis
- REST APIs
- Full Stack Development
- Backend Development using Java
- Senior Java Development

==================================================
RESUME MATCH — NEGATIVE SIGNALS
==================================================

Give strong negative weight if the job description is mainly:

- .NET, C#, ASP.NET
- Power BI
- QA, Testing
- Data Engineer, Data Analyst
- Python-only roles
- DevOps-only roles
- SAP, Salesforce, ServiceNow
- Support Engineer, Network Engineer

==================================================
RESUME MATCH SCORING GUIDE (resume_match_score)
==================================================

95-100: Excellent match — Java + Spring Boot + Microservices + React + REST APIs
85-94:  Strong Java role — most important skills match
70-84:  Good Java role — some important skills missing
50-69:  Weak Java match
30-49:  Poor match
0-29:   Technology mismatch

Rules:
- If Java is NOT a primary skill, resume_match_score MUST be below 50.
- If Spring Boot is missing, resume_match_score should rarely exceed 80.
- If React, AWS, Kafka, Redis and Microservices are present, increase score.
- If the role is primarily .NET, C#, QA, Data Engineering, Python-only, DevOps-only,
  SAP, Salesforce or ServiceNow, resume_match_score should be below 30.
- Crucial Experience Penalty: If the job description requires more than 8 years of experience (e.g. 9+ years, 10+ years, etc.), the resume_match_score MUST be reduced drastically and MUST NOT exceed 50.

==================================================
COMPANY TYPE ADJUSTMENT (company_adjustment)
==================================================

Based on company_type, set company_adjustment as follows:

- Product  → positive integer between 10 and 20 (stronger product companies → higher bonus)
- Service  → negative integer between -30 and -20 (large consulting firms → larger penalty)
- Unknown  → 0

==================================================
FINAL SCORE
==================================================

final_score = resume_match_score + company_adjustment
Clamp final_score to an integer between 0 and 100.

==================================================
OUTPUT FORMAT
==================================================

Return ONLY a raw JSON object with NO preamble, explanation, or markdown formatting outside the JSON:

{{
  "resume_match_score": <integer 0-100>,
  "company_type": "Product" | "Service" | "Unknown",
  "company_adjustment": <integer>,
  "final_score": <integer 0-100>
}}
""".strip()


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced_matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    for match in reversed(fenced_matches):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    json_objects = re.findall(r"\{[^{}]*\"resume_match_score\"[^{}]*\}", text, re.DOTALL)
    for match in reversed(json_objects):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    object_matches = re.findall(r"\{.*\}", text, re.DOTALL)
    for match in reversed(object_matches):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _normalize_company_type(raw_type: Any) -> str:
    if not isinstance(raw_type, str):
        return "Unknown"

    normalized = raw_type.strip().title()
    if normalized in VALID_COMPANY_TYPES:
        return normalized
    return "Unknown"


def _normalize_adjustment(company_type: str, raw_adjustment: Any) -> int:
    try:
        adjustment = int(raw_adjustment)
    except (TypeError, ValueError):
        adjustment = 0

    if company_type == "Product":
        return _clamp(adjustment, 10, 20)
    if company_type == "Service":
        return _clamp(adjustment, -30, -20)
    return 0


def _parse_score_response(raw_content: str) -> Dict[str, Union[int, str]]:
    payload = _extract_json(raw_content)
    if not payload:
        logger.warning("Failed to parse AI response as JSON: %s", raw_content)
        return DEFAULT_SCORE_RESULT.copy()

    try:
        resume_match_score = _clamp(int(payload.get("resume_match_score", 0)), 0, 100)
    except (TypeError, ValueError):
        resume_match_score = 0

    company_type = _normalize_company_type(payload.get("company_type"))
    company_adjustment = _normalize_adjustment(company_type, payload.get("company_adjustment"))

    try:
        final_score = int(payload.get("final_score", resume_match_score + company_adjustment))
    except (TypeError, ValueError):
        final_score = resume_match_score + company_adjustment

    final_score = _clamp(final_score, 0, 100)

    # Reconcile if the model's final_score disagrees with the formula.
    computed_final = _clamp(resume_match_score + company_adjustment, 0, 100)
    if abs(final_score - computed_final) > 1:
        final_score = computed_final

    return {
        "score": final_score,
        "company_type": company_type,
    }


def get_score(job_description: str, company_name: str = "", log_callback: Optional[Any] = None) -> Dict[str, Union[int, str]]:
    """
    Score a job against the candidate resume and company type.

    Returns:
        {"score": <int 0-100>, "company_type": "Product" | "Service" | "Unknown"}
    """
    if not job_description or not job_description.strip():
        logger.warning("Empty job description provided for company: %s", company_name)
        return DEFAULT_SCORE_RESULT.copy()

    try:
        resume = read_resume()
    except Exception as exc:
        logger.error("Failed to read resume: %s", exc)
        raise

    prompt = _build_prompt(resume, job_description, company_name)
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = get_client().chat.completions.create(
                model="minimax/minimax-m3:free",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500,
            )
            raw_content = (response.choices[0].message.content or "").strip()
            print(f"AI Response: {raw_content}")

            result = _parse_score_response(raw_content)
            print(
                f"Parsed score: {result['score']} | Company type: {result['company_type']}"
            )
            if log_callback:
                parsed_payload = _extract_json(raw_content)
                if parsed_payload:
                    log_callback(
                        f"LLM score: {result['score']} (Match: {parsed_payload.get('resume_match_score')}, "
                        f"Type: {result['company_type']}, Adj: {parsed_payload.get('company_adjustment')})",
                        status="success"
                    )
                else:
                    log_callback(
                        f"LLM returned invalid JSON. Raw response: {raw_content}",
                        status="warning"
                    )
            return result

        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            last_error = exc
            logger.warning(
                "Transient OpenRouter error (attempt %s/%s): %s",
                attempt,
                MAX_RETRIES,
                exc,
            )
            if log_callback:
                log_callback(
                    f"Transient LLM API Error (attempt {attempt}/{MAX_RETRIES}): {str(exc)}",
                    status="warning"
                )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS * attempt)
                continue
            break

        except Exception as exc:
            last_error = exc
            logger.error("Unexpected scoring error: %s", exc)
            if log_callback:
                log_callback(
                    f"LLM API Error: {str(exc)}",
                    status="error"
                )
            break

    logger.error("Scoring failed after retries: %s", last_error)
    return DEFAULT_SCORE_RESULT.copy()
