"""
Job Application Assistant for Sayantani Nath
- Opens top job matches in browser automatically
- Generates tailored cover letter for each job
- Tracks applications in a CSV log
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
    "phone": "",  # add your phone number here
    "location": "San Francisco Bay Area, CA",
    "linkedin": "linkedin.com/in/sayantani-nath-a252502",
    "github": "github.com/sayantaninath",
    "work_auth": "Authorised to work in the US — no employer sponsorship required (L2 EAD)",
    "experience": "13+ years",
    "current_role": "AVP Data Engineer at Citibank",
}

RESUME_SUMMARY = """
13+ years designing enterprise data solutions for banking, healthcare, and manufacturing.
Expert in dimensional modelling, cloud-native architectures, ETL/ELT pipeline development,
data governance, and team mentorship. Proven track record: 40% latency reduction,
45% storage optimisation, 50% query performance gains.

Key Skills: Advanced SQL, Snowflake, Oracle, PostgreSQL, Data Vault 2.0, Kafka, Redis,
GraphQL, Python, Talend, ERwin, Star/Snowflake Schemas, Kimball, OLAP/OLTP, SCD Strategies,
Data Governance, MDM, Data Quality, Lineage Management.
"""

TRACKER_FILE = "/Users/sayantaninath/Downloads/application_tracker.csv"

def get_latest_jobs():
    """Load the most recent job matches CSV."""
    files = glob("/Users/sayantaninath/Downloads/job_matches_*.csv")
    if not files:
        print("No job matches found. Run job_matcher.py first.")
        return None
    latest = max(files, key=os.path.getctime)
    print(f"Loading jobs from: {latest}")
    return pd.read_csv(latest)

def get_already_applied():
    """Load list of jobs already applied to."""
    if os.path.exists(TRACKER_FILE):
        tracker = pd.read_csv(TRACKER_FILE)
        return set(tracker["apply_url"].tolist())
    return set()

def generate_cover_letter(job_title, company, description):
    """Generate a tailored cover letter for a specific job."""

    # Extract key skills mentioned in job description
    key_skills = []
    skill_map = {
        "snowflake": "Snowflake",
        "data vault": "Data Vault 2.0",
        "kafka": "Kafka",
        "python": "Python",
        "etl": "ETL/ELT pipelines",
        "data modeling": "dimensional data modelling",
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
    }
    desc_lower = description.lower()
    for keyword, label in skill_map.items():
        if keyword in desc_lower:
            key_skills.append(label)

    skills_sentence = ""
    if key_skills:
        skills_sentence = f"Your requirement for expertise in {', '.join(key_skills[:4])} aligns directly with my hands-on experience in these technologies."

    cover_letter = f"""
{datetime.now().strftime("%B %d, %Y")}

Hiring Manager
{company}

Re: Application for {job_title}

Dear Hiring Manager,

I am writing to express my strong interest in the {job_title} position at {company}. With 13+ years of experience designing enterprise-scale data solutions across banking, healthcare, and manufacturing sectors, I am confident in my ability to deliver immediate and lasting impact to your data engineering organisation.

{skills_sentence}

In my current role as AVP Data Engineer at Citibank, I have led enterprise data architecture for DCRM/CEAM metrics — engineering conceptual and physical models across 4 domains adopted by 10+ teams. I architected a unified consumption layer leveraging Oracle sources, Kafka streaming, Redis caching, and GraphQL APIs, reducing source-to-mart latency by 40% and achieving 45% query performance improvement.

Previously as Lead Data Architect at Hexaware Technologies (IQVIA–Bayer), I designed a global healthcare analytics model with dimensional design patterns standardising architecture across 15+ programmes. I have deep expertise in Data Vault 2.0, Kimball methodology, Star/Snowflake schemas, SCD strategies, and data governance frameworks.

I am authorised to work in the United States and do not require employer sponsorship (L2 EAD). I am based in the San Francisco Bay Area and open to remote, hybrid, or on-site opportunities.

I would welcome the opportunity to discuss how my background aligns with your needs. Thank you for your time and consideration.

Warm regards,

{CANDIDATE["name"]}
{CANDIDATE["email"]}
{CANDIDATE["location"]}
LinkedIn: {CANDIDATE["linkedin"]}
GitHub: {CANDIDATE["github"]}
"""
    return cover_letter.strip()

def save_tracker(job_row, status="Applied"):
    """Log an application to the tracker CSV."""
    entry = {
        "date_applied": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "title": job_row.get("title", ""),
        "company": job_row.get("company", ""),
        "location": job_row.get("location", ""),
        "salary": job_row.get("salary", ""),
        "match_score": job_row.get("match_score", ""),
        "ead_friendly": job_row.get("ead_friendly", ""),
        "apply_url": job_row.get("apply_url", ""),
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
    print("Job Application Assistant — Sayantani Nath")
    print("=" * 60)

    # Load jobs
    df = get_latest_jobs()
    if df is None:
        return

    # Filter top matches not yet applied to
    already_applied = get_already_applied()
    df = df[~df["apply_url"].isin(already_applied)]
    df = df[df["match_score"] >= 70].head(10)

    if df.empty:
        print("No new top matches found. All top jobs already applied to!")
        return

    print(f"\nFound {len(df)} new top matches to review.\n")

    # Generate cover letters folder
    cover_letter_dir = "/Users/sayantaninath/Downloads/cover_letters"
    os.makedirs(cover_letter_dir, exist_ok=True)

    for i, (_, row) in enumerate(df.iterrows(), 1):
        print(f"\n{'='*60}")
        print(f"Job {i} of {len(df)}")
        print(f"Score:    {row['match_score']}%")
        print(f"Title:    {row['title']}")
        print(f"Company:  {row['company']}")
        print(f"Location: {row['location']} | Remote: {row['is_remote']}")
        print(f"Salary:   {row['salary']}")
        print(f"Visa OK:  {row.get('ead_friendly', 'Check')}")
        print(f"Apply:    {row['apply_url']}")
        print(f"{'='*60}")

        # Generate cover letter
        cover = generate_cover_letter(
            row["title"],
            row["company"],
            str(row.get("description_snippet", ""))
        )

        # Save cover letter
        safe_company = str(row["company"]).replace(" ", "_").replace("/", "_")
        cl_filename = f"{cover_letter_dir}/CoverLetter_{safe_company}_{i}.txt"
        with open(cl_filename, "w") as f:
            f.write(cover)

        print(f"\nCover letter saved: {cl_filename}")
        print("\n--- COVER LETTER PREVIEW ---")
        print(cover[:500] + "...")

        # Ask user
        print("\nOptions:")
        print("  y = open in browser + mark as applied")
        print("  s = skip this job")
        print("  q = quit")
        choice = input("\nYour choice (y/s/q): ").strip().lower()

        if choice == "y":
            webbrowser.open(row["apply_url"])
            save_tracker(row, status="Applied")
            print(f"✅ Opened in browser + logged as Applied")
        elif choice == "q":
            print("Exiting. Good luck with your applications!")
            break
        else:
            save_tracker(row, status="Skipped")
            print("Skipped.")

    print(f"\n{'='*60}")
    print(f"Application tracker saved to: {TRACKER_FILE}")
    print(f"Cover letters saved to: {cover_letter_dir}/")
    print("="*60)

if __name__ == "__main__":
    main()
