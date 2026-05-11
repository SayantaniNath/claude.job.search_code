"""
Job Application Assistant for Sayantani Nath
- Loads ALL job CSVs (not just latest) to maximise job pool
- Skips already applied/skipped jobs automatically
- Shows exactly 10 new top jobs per session
- Generates tailored cover letter for each job
- Tracks everything in application_tracker.csv
"""

import pandas as pd
import webbrowser
import os
from datetime import datetime
from glob import glob

# ── Your details ────────────────────────────────────────────────────────────
CANDIDATE = {
    "name": "Sayantani Nath",
    "email": "sayantaninath91@gmail.com",
    "phone": "",
    "location": "San Francisco Bay Area, CA",
    "linkedin": "linkedin.com/in/sayantani-nath-a252502",
    "github": "github.com/sayantaninath",
    "work_auth": "Authorised to work in the US — no employer sponsorship required (L2 EAD)",
    "experience": "13+ years",
    "current_role": "AVP Data Engineer at Citibank",
}

TRACKER_FILE = "/Users/sayantaninath/Downloads/application_tracker.csv"
COVER_LETTER_DIR = "/Users/sayantaninath/Downloads/cover_letters"

def get_all_jobs():
    """Load ALL job match CSVs and combine them."""
    files = glob("/Users/sayantaninath/Downloads/job_matches_*.csv")
    if not files:
        print("No job matches found. Run job_matcher.py first.")
        return None

    print(f"Loading jobs from {len(files)} search result file(s)...")
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f))
        except Exception:
            continue

    df = pd.concat(dfs, ignore_index=True)

    # Deduplicate by apply_url
    df = df.drop_duplicates(subset=["apply_url"], keep="first")
    print(f"Total unique jobs in pool: {len(df)}")
    return df

def get_already_seen():
    """Load all jobs already applied to or skipped."""
    if os.path.exists(TRACKER_FILE):
        tracker = pd.read_csv(TRACKER_FILE)
        return set(tracker["apply_url"].dropna().tolist())
    return set()

def get_tracker_stats():
    """Show application stats."""
    if not os.path.exists(TRACKER_FILE):
        return
    tracker = pd.read_csv(TRACKER_FILE)
    total = len(tracker)
    applied = len(tracker[tracker["status"] == "Applied"])
    skipped = len(tracker[tracker["status"] == "Skipped"])
    print(f"\n📊 Your Application Stats:")
    print(f"   Total processed : {total}")
    print(f"   Applied         : {applied}")
    print(f"   Skipped         : {skipped}")
    print(f"   Remaining today : 10 new jobs\n")

def generate_cover_letter(job_title, company, description):
    """Generate a tailored cover letter."""
    skill_map = {
        "snowflake": "Snowflake",
        "data vault": "Data Vault 2.0",
        "kafka": "Kafka",
        "python": "Python",
        "etl": "ETL/ELT pipelines",
        "data modeling": "dimensional data modelling",
        "data modelling": "dimensional data modelling",
        "data warehouse": "data warehousing",
        "sql": "Advanced SQL",
        "oracle": "Oracle",
        "postgresql": "PostgreSQL",
        "redis": "Redis caching",
        "graphql": "GraphQL APIs",
        "airflow": "Apache Airflow",
        "spark": "Apache Spark",
        "aws": "AWS",
        "azure": "Azure",
        "dbt": "dbt",
        "talend": "Talend",
    }
    desc_lower = description.lower()
    matched_skills = [label for kw, label in skill_map.items() if kw in desc_lower]

    skills_sentence = ""
    if matched_skills:
        skills_sentence = (
            f"Your requirement for expertise in {', '.join(matched_skills[:4])} "
            f"aligns directly with my hands-on experience in these technologies."
        )

    return f"""{datetime.now().strftime("%B %d, %Y")}

Hiring Manager
{company}

Re: Application for {job_title}

Dear Hiring Manager,

I am writing to express my strong interest in the {job_title} position at {company}. With 13+ years of experience designing enterprise-scale data solutions across banking, healthcare, and manufacturing sectors, I am confident in my ability to deliver immediate and lasting impact to your organisation.

{skills_sentence}

In my current role as AVP Data Engineer at Citibank, I have led enterprise data architecture for DCRM/CEAM metrics — engineering conceptual and physical models across 4 domains adopted by 10+ teams. I architected a unified consumption layer leveraging Oracle sources, Kafka streaming, Redis caching, and GraphQL APIs, reducing source-to-mart latency by 40% and achieving 45% query performance improvement.

Previously as Lead Data Architect at Hexaware Technologies (IQVIA–Bayer), I designed a global healthcare analytics model standardising architecture across 15+ programmes using Data Vault 2.0, Star/Snowflake schemas, and SCD Type 2 strategies.

I am authorised to work in the United States and do not require employer sponsorship (L2 EAD). I am based in the San Francisco Bay Area and open to remote, hybrid, or on-site opportunities.

I would welcome the opportunity to discuss how my background aligns with your needs.

Warm regards,

{CANDIDATE["name"]}
{CANDIDATE["email"]} | {CANDIDATE["location"]}
LinkedIn: {CANDIDATE["linkedin"]}
GitHub:   {CANDIDATE["github"]}"""

def save_to_tracker(row, status):
    """Log a job to the tracker CSV."""
    entry = {
        "date_applied": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "title": row.get("title", ""),
        "company": row.get("company", ""),
        "location": row.get("location", ""),
        "salary": row.get("salary", ""),
        "match_score": row.get("match_score", ""),
        "ead_friendly": row.get("ead_friendly", ""),
        "apply_url": row.get("apply_url", ""),
        "status": status,
        "notes": "",
    }
    if os.path.exists(TRACKER_FILE):
        tracker = pd.read_csv(TRACKER_FILE)
        tracker = pd.concat([tracker, pd.DataFrame([entry])], ignore_index=True)
    else:
        tracker = pd.DataFrame([entry])
    tracker.to_csv(TRACKER_FILE, index=False)

def main():
    print("=" * 60)
    print("  Daily Job Application Assistant — Sayantani Nath")
    print("  10 fresh top jobs every session")
    print("=" * 60)

    # Show stats from previous sessions
    get_tracker_stats()

    # Load all jobs
    df = get_all_jobs()
    if df is None:
        return

    # Remove already seen jobs
    already_seen = get_already_seen()
    df = df[~df["apply_url"].isin(already_seen)]

    # Sort by score, pick top 10
    df = df.sort_values("match_score", ascending=False).head(10)

    if df.empty:
        print("\n✅ You've gone through all available jobs!")
        print("The job matcher runs every 12 hours — check back tomorrow for fresh listings.")
        return

    remaining = len(df[~df["apply_url"].isin(already_seen)])
    print(f"New jobs available: {remaining} — showing top 10\n")

    os.makedirs(COVER_LETTER_DIR, exist_ok=True)

    applied_count = 0
    for i, (_, row) in enumerate(df.iterrows(), 1):
        print(f"\n{'─'*60}")
        print(f"  Job {i} of 10")
        print(f"  Score    : {row['match_score']}%")
        print(f"  Title    : {row['title']}")
        print(f"  Company  : {row['company']}")
        print(f"  Location : {row['location']} | Remote: {row.get('is_remote','')}")
        print(f"  Salary   : {row.get('salary', 'Not listed')}")
        print(f"  Visa OK  : {row.get('ead_friendly', 'Check')}")
        print(f"  Apply    : {row['apply_url']}")
        print(f"{'─'*60}")

        # Generate + save cover letter
        cover = generate_cover_letter(
            str(row["title"]),
            str(row["company"]),
            str(row.get("description_snippet", ""))
        )
        safe_name = str(row["company"]).replace(" ", "_").replace("/", "_")[:30]
        cl_path = f"{COVER_LETTER_DIR}/CoverLetter_{safe_name}_{i}.txt"
        with open(cl_path, "w") as f:
            f.write(cover)
        print(f"\n  📄 Cover letter saved: {cl_path}")

        print("\n  y = Apply (opens browser + logs it)")
        print("  s = Skip")
        print("  q = Quit session")
        choice = input("\n  Your choice (y/s/q): ").strip().lower()

        if choice == "y":
            webbrowser.open(row["apply_url"])
            save_to_tracker(row, "Applied")
            applied_count += 1
            print(f"  ✅ Opened + logged as Applied")
        elif choice == "q":
            save_to_tracker(row, "Skipped")
            print("\n  Session ended. See you tomorrow!")
            break
        else:
            save_to_tracker(row, "Skipped")
            print("  Skipped.")

    print(f"\n{'='*60}")
    print(f"  Applied this session : {applied_count}")
    print(f"  Tracker saved to     : {TRACKER_FILE}")
    print(f"  Cover letters saved  : {COVER_LETTER_DIR}/")
    print(f"{'='*60}")
    print("\n  Run again tomorrow for 10 more fresh jobs! 💪")

if __name__ == "__main__":
    main()
