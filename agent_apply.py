"""
Stage 2+3 job-application agent.

Usage:
    python agent_apply.py <apply_url> [resume_path]

Opens the URL in a visible Chrome window, scans the page for text inputs,
fills the ones it can match against profile.yaml, uploads the resume
(per-job tailored one if passed as the 2nd arg), drafts free-text answers
and a cover letter with Claude (Stage 3 — requires ANTHROPIC_API_KEY),
then stops. You review everything and click submit yourself.
The script never submits on your behalf.
"""

import re
import sys
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

import llm_answers

PROFILE_PATH = Path(__file__).parent / "profile.yaml"


# ── Part A: load your answers ──────────────────────────────────────────────
def load_profile():
    with open(PROFILE_PATH) as f:
        return yaml.safe_load(f)


# ── Part B: figure out what a form field is asking for ─────────────────────
def field_signal(el):
    """
    Combine every clue we can find about a form field into one lowercase string.
    We match keywords against this 'signal' to decide what to fill it with.
    """
    label = el.get_attribute("aria-label") or ""
    placeholder = el.get_attribute("placeholder") or ""
    name = el.get_attribute("name") or ""
    el_id = el.get_attribute("id") or ""
    # The <label for="..."> tag (or wrapping label) attached to this input.
    nearby = el.evaluate("e => e.labels && e.labels[0] ? e.labels[0].innerText : ''")
    # Walk up ancestors looking for a <label> or labelled heading. Greenhouse
    # frequently puts the question text in a <label> that isn't associated via
    # `for=` or in a sibling div, so e.labels misses it.
    ancestor_label = el.evaluate(
        """e => {
            let cur = e.parentElement;
            for (let i = 0; i < 5 && cur; i++) {
                const lbl = cur.querySelector('label, legend, [role="heading"]');
                if (lbl && !lbl.contains(e)) {
                    const text = (lbl.innerText || lbl.textContent || '').trim();
                    if (text && text.length > 1 && text.length < 200) return text;
                }
                cur = cur.parentElement;
            }
            return '';
        }"""
    )
    return f"{label} {placeholder} {name} {el_id} {nearby} {ancestor_label}".lower()


# ── Part C: the matching rules ─────────────────────────────────────────────
def build_rules(profile):
    """
    Each rule is (list of keywords, value to fill).
    Order matters — first match wins. So put the most specific rules first
    (e.g. 'first name' before generic 'name').
    """
    # Order matters — first match wins. Put highly specific phrases first so
    # short, generic keywords (e.g. "state") can't match inside a longer
    # question further down (e.g. "United States").
    return [
        # ── Work authorization Y/N (must come BEFORE state rule — legal-auth
        #    questions usually contain "United States" → "state").
        (["legally authorized", "authorized to work", "work authorization", "authorization to work"],
                                                                profile["work_authorized_us"]),
        (["require sponsorship", "need sponsorship", "visa sponsorship", "future require"],
                                                                profile["requires_sponsorship"]),
        # ── Heartflow-style Y/N questions (specific phrases first, before
        #    generic rules so they don't get hijacked).
        (["debarred", "debarment", "fda debarment"],            profile["fda_debarment"]),
        (["immediate family", "family member", "family employed"],
                                                                profile["family_at_employer"]),
        (["healthcare professional", "medical professional"],   profile["family_healthcare_professional"]),
        (["do you have 10+ years", "10+ years of relevant"],    profile["has_10_plus_years_experience"]),
        (["based in the san francisco", "based in san francisco bay", "currently based in"],
                                                                profile["based_in_sf_bay_area"]),
        (["attend office", "office attendance", "willing to attend", "in office", "onsite", "on-site"],
                                                                profile["willing_to_attend_office"]),
        (["willing to relocate", "open to relocation", "if not local"],
                                                                profile["willing_to_relocate"]),
        # ── Identity
        (["first name", "given name", "fname"],                 profile["first_name"]),
        (["last name", "family name", "surname", "lname"],      profile["last_name"]),
        (["full name", "your name", "candidate name"],          profile["full_name"]),
        (["email"],                                             profile["email"]),
        (["phone", "mobile", "telephone"],                      profile["phone"]),
        # ── Profiles
        (["linkedin"],                                          profile["linkedin"]),
        (["github"],                                            profile["github"]),
        (["portfolio", "personal website", "website"],          profile["portfolio"]),
        # ── Address — word boundaries mean "United States" doesn't match "state".
        (["zip", "postal"],                                     profile["zip_code"]),
        (["city"],                                              profile["city"]),
        (["state", "province"],                                 profile["state"]),
        (["country"],                                           profile["country"]),
        (["address", "street"],                                 profile["location"]),
        # ── Education
        (["school", "university", "institution"],               profile["school"]),
        (["degree"],                                            profile["degree"]),
        (["discipline", "field of study", "major"],             profile["discipline"]),
        (["start year", "start date year", "from year"],        profile["education_start_year"]),
        (["end year", "end date year", "to year", "graduation year"],
                                                                profile["education_end_year"]),
        # ── Work history
        (["current company", "employer"],                       profile["current_company"]),
        (["current title", "current role", "job title"],        profile["current_title"]),
        (["years of experience", "yoe"],                        profile["years_of_experience"]),
        (["salary", "compensation", "expected pay"],            profile["salary_expectation"]),
        (["notice period"],                                     profile["notice_period_days"]),
    ]


def matches_keyword(signal, keyword):
    """Word-boundary match — 'city' must NOT match inside 'ethnicity'."""
    return re.search(r"\b" + re.escape(keyword) + r"\b", signal) is not None


def is_combobox(el):
    """Detect a typeahead/combobox input. Greenhouse, Lever, and Ashby all
    render their Y/N + country + degree + school fields this way: they look
    like plain text inputs but actually hold React state that rejects typed
    values which don't match a real dropdown option."""
    role = (el.get_attribute("role") or "").lower()
    aria_auto = (el.get_attribute("aria-autocomplete") or "").lower()
    return role == "combobox" or aria_auto in ("list", "both", "inline")


def fill_combobox(page, el, value):
    """Click → type → click matching option. Returns True if an option was
    actually selected (i.e. the value will persist), False if no matching
    option appeared (in which case we leave the field blank rather than show
    misleading text that React will silently reset)."""
    value_str = str(value)
    try:
        el.click()
        page.wait_for_timeout(150)
        el.fill(value_str)
        page.wait_for_timeout(350)  # let the filtered dropdown render
    except Exception:
        return False

    # ARIA-compliant ATSes (Greenhouse, Lever, Ashby) use role="option".
    # filter(has_text=...) does substring matching, which is what we want for
    # typeaheads ("California" should match an option that reads "California").
    try:
        page.locator("[role='option']").filter(has_text=value_str).first.click(timeout=1500)
        return True
    except Exception:
        pass

    # Fallback: list-item options that aren't ARIA-tagged
    try:
        page.locator("li[role='presentation'], li.option").filter(has_text=value_str).first.click(timeout=1000)
        return True
    except Exception:
        pass

    # No matching option — clear the input so we don't leave misleading text
    # that React will reset on its next render anyway.
    try:
        el.fill("")
    except Exception:
        pass
    return False


def fill_field(page, el, rules):
    """Try each rule against this field. Fill on first match with a value.
    Routes comboboxes through the click-and-select path; plain inputs use
    direct fill()."""
    signal = field_signal(el)
    for keywords, value in rules:
        if not value:
            continue
        if any(matches_keyword(signal, k) for k in keywords):
            try:
                if is_combobox(el):
                    if fill_combobox(page, el, value):
                        return signal.strip(), value
                    return None, None  # combobox couldn't be selected — leave blank
                el.fill(str(value))
                return signal.strip(), value
            except Exception:
                return None, None
    return None, None


# ── Part D: file uploads ───────────────────────────────────────────────────
def upload_files(page, profile):
    """Find file inputs and upload from profile paths.

    Uses query_selector_all (ElementHandles) instead of locator(...).all()
    because some ATSes (notably Greenhouse) inject hidden/stale file inputs
    that cause Locator operations to hang for the 30s default timeout.
    ElementHandles point at specific DOM nodes without implicit retries.
    """
    try:
        file_inputs = page.query_selector_all("input[type=file]")
    except Exception:
        return []

    resume_path = profile.get("resume_path", "")
    cover_path = profile.get("cover_letter_path", "")
    uploads = []

    for el in file_inputs:
        # Get the signal — wrap every read so a detached/hidden element
        # doesn't crash the whole upload step.
        try:
            name = (el.get_attribute("name") or "").lower()
            el_id = (el.get_attribute("id") or "").lower()
            aria = (el.get_attribute("aria-label") or "").lower()
            try:
                label_text = (el.evaluate(
                    "e => e.labels && e.labels[0] ? e.labels[0].innerText : ''"
                ) or "").lower()
            except Exception:
                label_text = ""
            signal = f"{aria} {name} {el_id} {label_text}"
        except Exception:
            continue

        try:
            if resume_path and any(matches_keyword(signal, k) for k in ("resume", "cv")):
                el.set_input_files(resume_path)
                uploads.append(("resume", resume_path, signal.strip()))
            elif cover_path and matches_keyword(signal, "cover"):
                el.set_input_files(cover_path)
                uploads.append(("cover letter", cover_path, signal.strip()))
        except Exception as e:
            uploads.append(("?", f"FAILED: {str(e)[:80]}", signal.strip() or "<unknown>"))

    return uploads


# ── Part E: drive the page ─────────────────────────────────────────────────
def run(url, resume_override=None):
    profile = load_profile()
    if resume_override:
        profile["resume_path"] = resume_override
        print(f"→ Using per-job resume: {resume_override}")
    rules = build_rules(profile)

    with sync_playwright() as p:
        # headless=False means a real Chrome window opens — you can watch it work.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        print(f"\n→ Opening {url}")
        page.goto(url)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            # Some pages keep network activity going forever (chat widgets, etc.).
            pass

        # Modern ATS pages (Greenhouse, Lever) are React SPAs — the form renders
        # client-side and may appear *after* networkidle. Explicitly wait for any
        # input to exist before scanning.
        try:
            page.wait_for_selector("input, textarea", timeout=20000)
        except Exception:
            print("⚠️  No inputs appeared on page after 20s — the form may not have loaded.")

        # Nudge lazy-rendered sections by scrolling through the page once.
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(800)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(400)

        print(f"→ Landed on: {page.url}")
        raw_inputs = page.locator("input").count()
        raw_textareas = page.locator("textarea").count()
        raw_selects = page.locator("select").count()
        print(f"→ DOM contains: {raw_inputs} <input>, {raw_textareas} <textarea>, {raw_selects} <select> (selects/radios handled in later stage)")

        # Drop the :visible CSS pseudo (React often hides things via inline style
        # in ways the pseudo misses). Check per-element with is_visible() instead.
        selectors = "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]):not([type=file]), textarea"
        all_elements = page.locator(selectors).all()

        def skip_field(el):
            name = (el.get_attribute("name") or "").lower()
            el_id = (el.get_attribute("id") or "").lower()
            return any(x in name or x in el_id for x in ("recaptcha", "captcha", "honeypot"))

        elements = [el for el in all_elements if el.is_visible() and not skip_field(el)]

        print(f"→ Visible fillable fields after filter: {len(elements)} of {len(all_elements)}\n")

        if len(elements) == 0:
            print("❌ Nothing to fill — the form did not render. Likely causes:")
            print("   1. Form is inside an iframe — Greenhouse rarely does this, but check the page")
            print("   2. Apply button needs to be clicked first to reveal the form")
            print("   3. Page is gated by login or a region check")
            input("\nPress Enter to close the browser... ")
            browser.close()
            return

        filled = []
        skipped = []   # (element, signal) — kept so Stage 3 can try the textareas
        for el in elements:
            matched_signal, value = fill_field(page, el, rules)
            if matched_signal:
                filled.append((matched_signal, value))
            else:
                sig = field_signal(el).strip()
                skipped.append((el, sig if sig else "<unlabeled field>"))

        # Stage 3: if the form has a cover-letter upload and no letter is
        # configured, draft one with Claude and save it as .docx first, so the
        # upload pass below picks it up. Page text doubles as the JD context.
        try:
            page_context = page.title() + "\n" + page.evaluate("document.body.innerText")
        except Exception:
            page_context = ""
        cover_drafted = None
        if not profile.get("cover_letter_path") and llm_answers.api_key_available():
            has_cover_input = any(
                matches_keyword(
                    f"{(el.get_attribute('name') or '')} {(el.get_attribute('id') or '')} "
                    f"{(el.get_attribute('aria-label') or '')}".lower(), "cover")
                for el in page.query_selector_all("input[type=file]")
            )
            if has_cover_input and page_context:
                try:
                    letter = llm_answers.draft_cover_letter(page_context, profile)
                    if letter:
                        profile["cover_letter_path"] = llm_answers.save_cover_letter_docx(letter, profile)
                        cover_drafted = profile["cover_letter_path"]
                except Exception as e:
                    print(f"⚠️  Cover letter drafting failed: {str(e)[:120]}")

        # File uploads (resume, cover letter). Wrap defensively — a flaky
        # upload pass should never prevent the summary from printing.
        try:
            uploads = upload_files(page, profile)
        except Exception as e:
            print(f"⚠️  Upload step failed: {str(e)[:120]}")
            uploads = []

        # Stage 3: draft free-text answers with Claude. Drafts only — you
        # review and edit in the browser before submitting.
        drafted = []
        still_skipped = []
        free_text = [
            (el, sig) for el, sig in skipped
            if llm_answers.is_free_text_question(sig)
            and el.evaluate("e => e.tagName.toLowerCase()") == "textarea"
        ]
        if free_text and not llm_answers.api_key_available():
            print("⚠️  ANTHROPIC_API_KEY not set — free-text questions left blank.")
            free_text = []
        if free_text:
            for el, sig in free_text:
                try:
                    answer = llm_answers.draft_answer(sig, page_context, profile)
                except Exception as e:
                    print(f"⚠️  Claude drafting failed: {str(e)[:120]} — remaining questions left blank.")
                    break
                if answer:
                    try:
                        el.fill(answer)
                        drafted.append((sig, answer))
                    except Exception:
                        pass
        drafted_signals = {sig for sig, _ in drafted}
        still_skipped = [sig for _, sig in skipped if sig not in drafted_signals]

        # Summary
        print("─" * 60)
        print(f"FILLED ({len(filled)})")
        for sig, value in filled:
            display = (sig[:50] + "…") if len(sig) > 50 else sig
            print(f"  ✓ {display!r:55} ← {value!r}")
        print()
        print(f"UPLOADED ({len(uploads)})")
        for kind, path, sig in uploads:
            display = (sig[:40] + "…") if len(sig) > 40 else sig
            print(f"  ✓ {kind:14} → {path}")
            print(f"    (matched field: {display})")
        print()
        if cover_drafted:
            print(f"COVER LETTER drafted by Claude → {cover_drafted}")
            print("  (uploaded to the form — open the file and review before submitting)")
            print()
        print(f"DRAFTED BY CLAUDE ({len(drafted)}) — REVIEW AND EDIT BEFORE SUBMIT:")
        for sig, answer in drafted:
            display = (sig[:50] + "…") if len(sig) > 50 else sig
            print(f"  ✎ {display!r}")
            print(f"    → {answer[:100]}…" if len(answer) > 100 else f"    → {answer}")
        print()
        print(f"NOT FILLED ({len(still_skipped)}) — your turn:")
        for sig in still_skipped:
            display = (sig[:60] + "…") if len(sig) > 60 else sig
            print(f"  · {display}")
        print("─" * 60)
        print("\nReview the form, handle the remaining fields, then click submit yourself.")
        input("Press Enter when you're done to close the browser... ")

        browser.close()


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("Usage: python agent_apply.py <apply_url> [resume_path]")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
