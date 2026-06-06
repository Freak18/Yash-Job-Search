import re

from openai import OpenAI

from config import OPENROUTER_API_KEY
from paths import read_resume

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
    return _client


def get_score(job_description):
    resume = read_resume()

    prompt = f"""
You are an extremely strict technical recruiter.

==================================================
CANDIDATE RESUME
==================================================

{resume}

==================================================
JOB DESCRIPTION
==================================================

{job_description}

==================================================
TASK
==================================================

Compare the candidate's resume against the job description.

IMPORTANT:
- Score ONLY based on the job description.
- Ignore the job title completely.
- Be extremely strict.

==================================================
STRONG POSITIVE MATCH
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
NEGATIVE MATCH
==================================================

Give strong negative weight if the job description is mainly:

- .NET
- C#
- ASP.NET
- Power BI
- QA
- Testing
- Data Engineer
- Data Analyst
- Python-only roles
- DevOps-only roles
- SAP
- Salesforce
- ServiceNow
- Support Engineer
- Network Engineer

==================================================
SCORING GUIDE
==================================================

95-100:
Excellent match.
Java + Spring Boot + Microservices + React + REST APIs

85-94:
Strong Java role.
Most important skills match.

70-84:
Good Java role.
Some important skills missing.

50-69:
Weak Java match.

30-49:
Poor match.

0-29:
Technology mismatch.

==================================================
IMPORTANT RULES
==================================================

If Java is NOT a primary skill:
Score MUST be below 50.

If Spring Boot is missing:
Score should rarely exceed 80.

If React, AWS, Kafka, Redis and Microservices are present:
Increase score.

If the role is primarily:
.NET, C#, QA, Testing, Power BI,
Data Engineering, Python, DevOps,
SAP, Salesforce or ServiceNow:

Score should be below 30.

==================================================
OUTPUT
==================================================

Return ONLY a single integer.

Examples:

95
87
42
15

Do not explain.
Do not write any text.
Return only the number.
"""

    response = get_client().chat.completions.create(
        model="deepseek/deepseek-chat-v3",
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    result = response.choices[0].message.content.strip()

    print("AI Response:", result)

    match = re.search(r"\d+", result)

    if match:
        return int(match.group())

    return 0
