import re
import phonenumbers
from app.utils.file_reader import read_resume_from_upload
from app.services.skill_matcher import nlp, matcher

def extract_skills(text):
    text_lower = text.lower()
    skill_section = text_lower

    if "skills" in text_lower:
        skill_section = text_lower.split("skills", 1)[1][:1500]

    doc = nlp(skill_section)
    matches = matcher(doc)

    skills = set()
    for _, start, end in matches:
        skill = doc[start:end].text.lower().strip()
        skill = re.sub(r"[^a-zA-Z0-9+.# ]", "", skill)
        if len(skill) > 1:
            skills.add(skill)

    return sorted(skills)


def extract_experience_years(text):
    patterns = [
        r"(\d+)\+?\s*years",
        r"(\d+)\+?\s*yrs",
        r"experience\s*[:\-]?\s*(\d+)",
        r"over\s*(\d+)\s*years"
    ]

    years = []
    for pattern in patterns:
        matches = re.findall(pattern, text.lower())
        years.extend([int(m) for m in matches])

    return max(years) if years else None


def extract_education(text):
    degrees = ["bachelor","b.tech","be","b.sc","master","m.tech","mba","phd","diploma"]
    results = []

    for sent in nlp(text).sents:
        s = sent.text.lower()
        if any(deg in s for deg in degrees):
            results.append(sent.text.strip())

    return results


def extract_projects(text):
    projects = []
    if "project" in text.lower():
        section = text.lower().split("project", 1)[1][:2000]
        for sent in nlp(section).sents:
            if len(sent.text.strip()) > 20:
                projects.append(sent.text.strip())
    return projects[:5]


def extract_email(text):
    match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    return match.group(0) if match else None


def extract_phone(text):
    for match in phonenumbers.PhoneNumberMatcher(text, None):
        return phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164)
    return None

def extract_name(text):
    doc = nlp(text[:300])
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text
        return None


def parse_resume(text):
    return {
    "name": extract_name(text),
    "skills": extract_skills(text),
    "experience_years": extract_experience_years(text),
    "education": extract_education(text),
    "projects": extract_projects(text),
    "email": extract_email(text),
    "phone": extract_phone(text)
    }


def clean_text(text):
    text = re.sub(r"[^\x20-\x7E]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def parse_resume_file(file):
    raw = read_resume_from_upload(file)
    return clean_text(raw)