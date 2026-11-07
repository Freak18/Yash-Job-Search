import json
import logging
import re
import time
from typing import Any, Dict, Optional, Union

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from config import LLM_API_KEY, LLM_BASE_URL, OPENROUTER_MODEL
from paths import read_resume

logger = logging.getLogger(__name__)

VALID_COMPANY_TYPES = frozenset({"Target", "Unknown"})
DEFAULT_SCORE_RESULT = {"score": 0, "company_type": "Target", "reason": ""}

_client: Optional[OpenAI] = None
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not LLM_API_KEY:
            raise ValueError("Neither GEMINI_API_KEY nor OPENROUTER_API_KEY environment variable is set.")
        _client = OpenAI(
            base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY,
        )
    return _client


def _build_prompt(resume: str, job_description: str, company_name: str) -> str:
    company_display = company_name.strip() or "Target Company"
    return f"""
CRITICAL REQUIREMENT: RESPOND WITH ONLY THE RAW JSON OBJECT. DO NOT OUTPUT ANY PREAMBLE, REASONING, OR THINKING TEXT.

You are an extremely strict technical recruiter evaluating job fit for a target employer.

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

Evaluate the candidate's resume match against the job description only.
- Score ONLY based on the job description.
- Ignore the job title completely.
- Be extremely strict.

==================================================
RESUME MATCH — EXPERIENCE AND SKILLS REQUIREMENTS
==================================================

Evaluate the required years of experience and skills:
- The candidate's resume shows 7+ years of professional full-stack development experience (Java, Spring Boot, React, Microservices, and GenAI).
- The ideal required experience for the job is between 3 and 8 years.
- If the job description requires more than 8 years of experience (e.g. 9+, 10+, 12+ years, or Principal/Staff/Architect roles demanding >8 years), the match is poor and you MUST reduce the score drastically (it should not exceed 50).
- If the job description requires 8 years of experience or less (e.g. 4-7 years, 5-8 years, 3-5 years, or unspecified mid-to-senior level), it aligns well with the candidate's background.
- Core stack priority: Java, Spring Boot, Microservices, and optionally React / GenAI.

==================================================
RESUME MATCH — STRONG POSITIVE SIGNALS
==================================================

Give strong positive weight if the job description contains:

- Java (Core & Advanced)
- Spring Boot / Spring Reactive
- Microservices Architecture
- React.js / Modern Frontend
- RESTful APIs
- Kafka / Event-driven architecture
- Redis / Caching
- AWS / Cloud Services
- Docker / Containerization
- GenAI / Agentic AI / LangGraph / RAG / LLM Integration
- Full Stack Development (Java + React)
- Backend Engineering using Java
- Senior Software Engineer / Lead Java Developer

==================================================
RESUME MATCH — NEGATIVE SIGNALS
==================================================

Give strong negative weight if the job description is primarily:

- .NET, C#, ASP.NET
- Power BI, Tableau
- QA, Manual Testing, Test Automation only
- Data Analyst, BI Developer
- DevOps-only / Sysadmin / SRE only (with no application development)
- SAP, Salesforce, or ServiceNow administration / configuration
- Support Engineer, Helpdesk, Network Engineer

==================================================
RESUME MATCH SCORING GUIDE (score)
==================================================

95-100: Exceptional match — Java + Spring Boot + Microservices + React / AWS / GenAI
85-94:  Strong match — core Java + Spring Boot + Microservices match with required experience
70-84:  Good match — solid Java backend role, minor complementary skills missing
50-69:  Weak match — peripheral Java or secondary role fit
30-49:  Poor match — wrong seniority or major tech stack gaps
0-29:   Technology mismatch (.NET, QA, SAP, Salesforce, Support)

Rules:
- If Java is NOT a primary skill, score MUST be below 50.
- If Spring Boot is missing for a Java backend role, score should rarely exceed 80.
- If React, AWS, Kafka, Redis, Docker, and Microservices are present, increase score.
- If GenAI / Agentic AI / LLM workflows are requested alongside Java/Full Stack, boost score.
- If the role is primarily .NET, C#, QA, SAP, Salesforce or ServiceNow administration, score should be below 30.
- Crucial Experience Penalty: If the job description requires more than 8 years of experience (e.g. 9+ years, 10+ years, etc.), the score MUST be reduced drastically and MUST NOT exceed 50.

==================================================
OUTPUT FORMAT
==================================================

Return ONLY a raw JSON object with NO preamble, explanation, or markdown formatting outside the JSON:

{{
  "score": <integer 0-100>,
  "reason": "<short 1-sentence summary of fit>"
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

    json_objects = re.findall(r"\{[^{}]*\"score\"[^{}]*\}", text, re.DOTALL)
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


def _parse_score_response(raw_content: str) -> Dict[str, Union[int, str]]:
    payload = _extract_json(raw_content)
    if not payload:
        logger.warning("Failed to parse AI response as JSON: %s", raw_content)
        return DEFAULT_SCORE_RESULT.copy()

    try:
        raw_score = payload.get("score", payload.get("resume_match_score", 0))
        final_score = _clamp(int(raw_score), 0, 100)
    except (TypeError, ValueError):
        final_score = 0

    reason = str(payload.get("reason", "")).strip()

    return {
        "score": final_score,
        "company_type": "Target",
        "reason": reason,
    }


def get_score(job_description: str, company_name: str = "", log_callback: Optional[Any] = None) -> Dict[str, Union[int, str]]:
    """
    Score a job against the candidate resume.

    Returns:
        {"score": <int 0-100>, "company_type": "Target", "reason": "<str>"}
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
                model=OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500,
            )
            raw_content = (response.choices[0].message.content or "").strip()
            print(f"AI Response: {raw_content}")

            result = _parse_score_response(raw_content)
            print(
                f"Parsed score: {result['score']} | Reason: {result.get('reason', '')}"
            )
            if log_callback:
                parsed_payload = _extract_json(raw_content)
                if parsed_payload:
                    reason_str = f" - {result['reason']}" if result.get('reason') else ""
                    log_callback(
                        f"LLM score: {result['score']}/100{reason_str}",
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
