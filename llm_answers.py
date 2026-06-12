"""
Stage 3: LLM-drafted answers for free-text application questions.

Used by agent_apply.py. When the form has a textarea the keyword rules can't
fill ("Why do you want to work here?", "Describe a project..."), this module
drafts an answer with Claude, grounded in the resume — the agent fills it in
as a DRAFT and you review/edit before submitting. Never fabricates experience.

Requires ANTHROPIC_API_KEY in the environment. If it's missing, agent_apply.py
falls back to leaving these fields blank (the pre-Stage-3 behavior).
"""

import os
import re
from pathlib import Path

import yaml

MODEL = "claude-opus-4-8"
RESUME_HTML = Path.home() / "Downloads/resume_HTML_MISC/Sayantani_Nath_ATS_Resume_WorkAuth.html"
MAX_PAGE_CONTEXT = 6000  # chars of job-page text passed as JD context

# Signals that mark a textarea as a free-text question worth drafting.
# Deliberately conservative — anything not matched stays manual.
QUESTION_HINTS = (
    "why", "describe", "tell us", "tell me", "what interests", "what excites",
    "cover letter", "motivation", "anything else", "additional information",
    "share an example", "how would you", "what makes you",
)


def is_free_text_question(signal):
    return any(hint in signal for hint in QUESTION_HINTS)


def load_resume_text():
    """Plain-text resume from the master HTML — good enough grounding for drafts."""
    try:
        html = RESUME_HTML.read_text(errors="ignore")
    except OSError:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def draft_answer(question, page_context, profile):
    """One Claude call → one drafted answer string. Raises on API errors so the
    caller can decide to skip drafting for the rest of the form."""
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    resume = load_resume_text()

    system = (
        "You draft answers to job-application free-text questions on behalf of the "
        "candidate, in her first-person voice. Hard rules:\n"
        "- Ground every claim in the resume below. NEVER invent experience, employers, "
        "metrics, or technologies that aren't in it.\n"
        "- 100-160 words unless the question clearly wants less (then be shorter).\n"
        "- Plain confident prose. No bullet points, no headers, no openers like "
        "'I am writing to express'.\n"
        "- If the question asks about work authorization: authorized to work in the US, "
        "no sponsorship required (L2 EAD).\n"
        "- If the question can't be answered from the resume (e.g. salary, references, "
        "how did you hear about us), reply with exactly: SKIP\n\n"
        f"CANDIDATE RESUME:\n{resume}\n\n"
        f"STANDARD ANSWERS:\n{yaml.safe_dump({k: v for k, v in profile.items() if v and 'path' not in k})}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{
            "role": "user",
            "content": (
                f"JOB PAGE (for context about the role/company):\n{page_context[:MAX_PAGE_CONTEXT]}\n\n"
                f"APPLICATION QUESTION:\n{question}\n\n"
                "Draft the answer."
            ),
        }],
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    if text == "SKIP" or not text:
        return None
    return text


def api_key_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
