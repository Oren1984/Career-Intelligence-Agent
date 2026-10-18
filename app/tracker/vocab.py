"""Controlled vocabularies for the application tracker.

Internal values are language-neutral codes. Hebrew labels are copied verbatim
from the workbook's "רשימות בחירה" sheet (including its original spelling,
e.g. "Meta Al") so that importing and exporting the workbook is lossless.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# code: (hebrew label from the workbook, english label) — order = workbook order
STATUSES: dict[str, tuple[str, str]] = {
    "submitted": ("הוגש", "Submitted"),
    "screening": ("בבדיקה", "Under review"),
    "initial_call": ("שיחה ראשונית", "Initial call"),
    "interview": ("ראיון מקצועי", "Professional interview"),
    "home_assignment": ("מטלת בית", "Home assignment"),
    "offer": ("הצעה / מתקדם", "Offer / advanced"),
    "rejected": ("נדחה", "Rejected"),
    "closed_no_response": ("נסגר ללא מענה", "Closed – no response"),
}
TRACKS: dict[str, tuple[str, str]] = {
    "ai_rag": ("AI Systems & RAG", "AI Systems & RAG"),
    "devops_cloud": ("DevOps & ענן", "DevOps & Cloud"),
    "qa_automation": ("QA & אוטומציה", "QA & Automation"),
    "tech_pm": ("ניהול פרויקטים טכנולוגיים", "Technology project management"),
    "software_other": ("תוכנה / אחר", "Software / other"),
}
SOURCES: dict[str, tuple[str, str]] = {
    "linkedin": ("לינקדאין (LinkedIn)", "LinkedIn"),
    "drushim": ("דרושים (Drushim)", "Drushim"),
    "alljobs": ("AllJobs", "AllJobs"),
    "jobmaster": ("ג'ובמאסטר (JobMaster)", "JobMaster"),
    "jobnet": ("ג'ובנט (Jobnet)", "Jobnet"),
    "jobkarov": ("ג'וב קרוב (JobKarov)", "JobKarov"),
    "jobify360": ("ג'וביפיי (Jobify360)", "Jobify360"),
    "gotfriends": ("גוטפרנדס (Gotfriends)", "Gotfriends"),
    "xplace": ("אקספלייס (Xplace)", "Xplace"),
    "facebook": ("facebook", "Facebook"),
    "meta_ai": ("Meta Al", "Meta AI"),
    "company_site": ("אתר החברה / פנייה יזומה", "Company website / direct approach"),
    "referral": ("חבר מביא חבר (Referral)", "Referral"),
    "other": ("אחר", "Other"),
}
VOCABS = {"status": STATUSES, "track": TRACKS, "source": SOURCES}

# Workbook KPI definitions (sheet "דשבורד וניתוח", cells C5, E5, G5).
ACTIVE_STATUSES = ("submitted", "screening", "initial_call", "interview", "home_assignment")
INTERVIEW_STATUSES = ("initial_call", "interview")
ASSIGNMENT_OFFER_STATUSES = ("home_assignment", "offer")
# Pipeline funnel order; rejected / closed / unset count only as "submitted".
FUNNEL = ("submitted", "screening", "initial_call", "interview", "home_assignment", "offer")

STALE_DAYS = 14


def label(field: str, code: Optional[str], lang: str) -> str:
    """Display label for a code ('' for None, the code itself if unknown)."""
    if not code:
        return ""
    pair = VOCABS[field].get(code)
    if pair is None:
        return code
    return pair[0] if lang == "he" else pair[1]


def labels(field: str, lang: str) -> list[str]:
    return [label(field, code, lang) for code in VOCABS[field]]


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    text = re.sub(r"[‘’׳`´]", "'", text)          # apostrophes / geresh
    text = re.sub(r"[‐-―−]", "-", text)            # dashes
    return re.sub(r"\s+", " ", text).strip()


_LOOKUP: dict[str, dict[str, str]] = {}
for _field, _vocab in VOCABS.items():
    table: dict[str, str] = {}
    for _code, (_he, _en) in _vocab.items():
        for variant in (_code, _he, _en):
            table[_norm(variant)] = _code
    _LOOKUP[_field] = table
_LOOKUP["source"][_norm("Meta AI")] = "meta_ai"


def to_code(field: str, value) -> Optional[str]:
    """Map a Hebrew label, English label or code to its code; None if unknown/blank."""
    if value is None or str(value).strip() == "":
        return None
    return _LOOKUP[field].get(_norm(value))
