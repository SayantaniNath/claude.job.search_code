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


def draft_cover_letter(page_context, profile):
    """Full cover letter for forms with a cover-letter upload field. Returns the
    letter text, or None if there isn't enough job context to write one."""
    import anthropic

    client = anthropic.Anthropic()
    resume = load_resume_text()

    system = (
        "You write job-application cover letters for the candidate, first person. Hard rules:\n"
        "- Ground every claim in the resume below. NEVER invent experience, employers, "
        "metrics, or technologies.\n"
        "- 250-320 words, 3-4 paragraphs. Address 'Dear Hiring Manager'.\n"
        "- Lead with fit for THIS role using the job page; pick the 2-3 strongest "
        "matching experiences, not a resume recital.\n"
        "- Include: authorized to work in the US, no sponsorship required (L2 EAD).\n"
        "- If the page has no usable job description, reply with exactly: SKIP\n\n"
        f"CANDIDATE RESUME:\n{resume}"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{
            "role": "user",
            "content": f"JOB PAGE:\n{page_context[:MAX_PAGE_CONTEXT]}\n\nWrite the cover letter.",
        }],
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    return None if (text == "SKIP" or not text) else text


def save_cover_letter_docx(text, profile):
    """Save the letter as .docx via macOS textutil (HTML → docx). Returns the
    docx path, or the .html path if conversion fails (still uploadable on most ATSes)."""
    import subprocess
    from datetime import datetime

    out_dir = Path.home() / "Downloads/cover_letters"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    html_path = out_dir / f"Cover_Letter_{stamp}.html"

    paragraphs = "".join(f"<p>{p}</p>" for p in text.split("\n\n"))
    html_path.write_text(
        f"<html><body style='font-family: Georgia, serif; font-size: 11pt;'>"
        f"<p>{profile['full_name']}<br>{profile['email']}</p>{paragraphs}</body></html>"
    )
    docx_path = html_path.with_suffix(".docx")
    try:
        subprocess.run(
            ["textutil", "-convert", "docx", str(html_path), "-output", str(docx_path)],
            check=True, capture_output=True,
        )
        return str(docx_path)
    except Exception:
        return str(html_path)


def api_key_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
