from scorer import get_score

job_description = """
Senior Java Developer

Required Skills:
Java
Spring Boot
Microservices
React
AWS
REST APIs
"""

score = get_score(job_description)

print("Final Score:", score)