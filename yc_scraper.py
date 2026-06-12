"""
Y Combinator job scraper for Sayantani Nath.

Scrapes Work at a Startup (workatastartup.com) using Playwright since the site
is a React SPA. Filters for data-related roles, applies the same
visa-restriction + location filters as job_matcher.py, and writes results in
the same CSV schema so email_jobs.py picks them up via its glob.

Usage: python ~/claude_job_linkedin/yc_scraper.py
Output: ~/Downloads/job_matches_yc_<timestamp>.csv
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

# Reuse the matcher's scoring + filtering. Same SEARCH_MODE applies.
sys.path.insert(0, str(Path(__file__).parent))
from job_matcher import (
    SEARCH_MODE,
    is_relevant_location,
    is_visa_restricted,
    score_job,
)

YC_BASE_URL = "https://www.workatastartup.com/companies"

# Data-relevant title keywords. YC doesn't have a "data" job category, so we
# filter by title after scraping.
DATA_TITLE_KEYWORDS = [
    "data engineer", "data architect", "data modeler", "data warehouse",
    "data platform", "data infrastructure", "etl", "analytics engineer",
    "data eng", "data engineering", "machine learning engineer", "mle ",
    "ml engineer", "ai engineer", "ml platform", "data scientist",
]


def is_data_role(title):
    t = title.lower()
    return any(k in t for k in DATA_TITLE_KEYWORDS)


def scrape_yc_jobs(max_jobs=200, headless=True):
    """Scrape workatastartup.com job listings."""
    jobs = []

    # Build search URL. workatastartup uses query params; using `remote_only`
    # when our SEARCH_MODE is remote_only.
    remote_param = "only_remote" if SEARCH_MODE == "remote_only" else "any"
    url = (
        f"https://www.workatastartup.com/jobs"
        f"?demographic=any&hasEquity=any&hasSalary=any&jobType=fulltime"
        f"&layout=list-compact&remoteness={remote_param}&role=eng"
    )

    print(f"Loading: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"  Initial load timeout: {e}")

        page.wait_for_timeout(2500)

        # Scroll a few times to trigger lazy loading
        for _ in range(8):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)

        # Extract job links + visible card text.
        # Cards on workatastartup.com link to /jobs/<id>-<slug>.
        job_data = page.evaluate(
            """
            () => {
                const seen = new Set();
                const out = [];
                const links = document.querySelectorAll('a[href*="/jobs/"]');
                for (const a of links) {
                    const href = a.getAttribute('href');
                    if (!href || seen.has(href)) continue;
                    seen.add(href);
                    // Walk up to find the visible card container
                    let card = a.closest('div, li, article') || a;
                    const text = (card.innerText || a.innerText || '').trim();
                    if (!text || text.length < 5) continue;
                    out.push({
                        url: href.startsWith('http') ? href
                              : 'https://www.workatastartup.com' + href,
                        text: text,
                    });
                }
                return out;
            }
            """
        )

        print(f"  Found {len(job_data)} raw job card links")

        for item in job_data[:max_jobs]:
            text = item["text"]
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) < 2:
                continue

            # Card layout typically:
            #   Line 1: company name
            #   Line 2: role title
            #   Lines 3-N: salary, equity, location, posted date
            company = lines[0]
            title = lines[1]

            location = ""
            salary = "Not listed"
            description_bits = []
            for line in lines[2:]:
                low = line.lower()
                if re.search(r"\bremote\b|\bhybrid\b|\bin[- ]?person\b", low):
                    location = line
                elif re.search(r"\$[\d,]+|equity", low):
                    salary = line
                else:
                    description_bits.append(line)
            description = " ".join(description_bits)

            if not is_data_role(title):
                continue

            is_remote = "remote" in location.lower()
            if is_visa_restricted(description, title):
                continue
            if not is_relevant_location(location, is_remote):
                continue

            score, matched = score_job(title, description)
            if score < 20:
                continue

            jobs.append({
                "match_score": score,
                "title": title,
                "company": company,
                "location": location or "Not specified",
                "is_remote": "Yes" if is_remote else "No",
                "job_type": "fulltime",
                "salary": salary,
                "ead_friendly": "Check",  # YC doesn't usually state this
                "date_posted": "",
                "apply_url": item["url"],
                "source": "ycombinator",
                "matched_keywords": ", ".join(matched[:10]),
                "description_snippet": description[:400],
            })

        browser.close()

    return jobs


def main():
    print("=" * 60)
    print("Y Combinator (Work at a Startup) Scraper")
    print(f"Mode: {SEARCH_MODE}")
    print("=" * 60)

    jobs = scrape_yc_jobs(max_jobs=200)
    if not jobs:
        print("\nNo matching YC jobs found. Check the URL filters or DOM structure.")
        return

    df = pd.DataFrame(jobs).drop_duplicates(subset=["apply_url"])
    df = df.sort_values("match_score", ascending=False)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"/Users/sayantaninath/Downloads/job_matches_yc_{timestamp}.csv"
    df.to_csv(filename, index=False)

    print(f"\nFound {len(df)} matching YC jobs.")
    print("\nTop 8:")
    for _, r in df.head(8).iterrows():
        print(f"  [{r['match_score']}%] {r['title']} @ {r['company']}")
        print(f"        {r['location']}  |  {r['salary']}")
        print(f"        {r['apply_url']}")
    print(f"\nSaved to: {filename}")
    print(f"email_jobs.py will pick this up automatically (it globs job_matches_*.csv).")


if __name__ == "__main__":
    main()
