"""
LinkedIn Job Matcher for Sayantani Nath
Searches jobs across LinkedIn, Indeed, Glassdoor
Scores and ranks by resume match
Filters: San Francisco Bay Area + US Remote, Hybrid/Remote
"""

from jobspy import scrape_jobs
import pandas as pd
from datetime import datetime
import re

# ── Resume keywords extracted from Sayantani's resume ──────────────────────
RESUME_SKILLS = [
    # Core skills
    "data modeling", "data modelling", "dimensional modeling", "dimensional modelling",
    "data warehouse", "data warehousing", "data architect", "data architecture",
    "data engineer", "data engineering", "etl", "elt", "pipeline",
    # Technologies
    "snowflake", "oracle", "postgresql", "sql", "kafka", "redis", "graphql",
    "talend", "python", "erwin", "magicdraw",
    # Patterns & methodologies
    "data vault", "star schema", "snowflake schema", "kimball", "olap", "oltp",
    "scd", "slowly changing dimension", "data governance", "mdm",
    "data quality", "data lineage",
    # Cloud & architecture
    "cloud", "cloud-native", "distributed", "streaming",
    # Soft/domain
    "banking", "healthcare", "finance", "fintech", "enterprise",
    "performance tuning", "query optimization", "partitioning", "indexing",
]

TARGET_JOB_TITLES = [
    "Senior Data Engineer",
    "Lead Data Engineer",
    "Principal Data Engineer",
    "Data Architect",
    "Senior Data Architect",
    "Data Modeler",
    "Senior Data Modeler",
    "Data Warehouse Engineer",
    "Data Infrastructure Engineer",
    "Data Platform Engineer",
    "Staff Data Engineer",
]

LOCATIONS = [
    "San Francisco, CA",
    "United States",  # catches remote US jobs
]

def score_job(title, description):
    """Score a job 0-100 based on resume keyword match."""
    text = f"{title} {description}".lower()
    matched = [kw for kw in RESUME_SKILLS if kw.lower() in text]
    score = min(100, int((len(matched) / len(RESUME_SKILLS)) * 100 * 2.5))
    return score, matched

def is_relevant_location(location, is_remote):
    """Keep SF Bay Area, hybrid, remote, or US remote jobs."""
    if is_remote:
        return True
    if not location:
        return False
    loc = location.lower()
    keywords = ["san francisco", "sf", "bay area", "remote", "hybrid",
                 "california", "ca,", ", ca", "new york", "seattle",
                 "united states", "usa", "anywhere"]
    return any(k in loc for k in keywords)

def search_jobs():
    all_jobs = []

    for title in TARGET_JOB_TITLES:
        print(f"Searching: {title}...")
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=title,
                location="San Francisco Bay Area, CA",
                results_wanted=20,
                hours_old=72,  # jobs posted in last 3 days
                country_indeed="USA",
                linkedin_fetch_description=True,
                is_remote=False,
            )
            all_jobs.append(jobs)

            # Also search for remote
            remote_jobs = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=title,
                location="United States",
                results_wanted=10,
                hours_old=72,
                country_indeed="USA",
                linkedin_fetch_description=True,
                is_remote=True,
            )
            all_jobs.append(remote_jobs)

        except Exception as e:
            print(f"  Error searching {title}: {e}")
            continue

    if not all_jobs:
        print("No jobs found.")
        return pd.DataFrame()

    df = pd.concat(all_jobs, ignore_index=True)
    df = df.drop_duplicates(subset=["title", "company"], keep="first")
    return df

def process_jobs(df):
    if df.empty:
        return df

    results = []
    for _, row in df.iterrows():
        title = str(row.get("title", ""))
        description = str(row.get("description", ""))
        location = str(row.get("location", ""))
        is_remote = bool(row.get("is_remote", False))

        # Filter irrelevant locations
        if not is_relevant_location(location, is_remote):
            continue

        score, matched_keywords = score_job(title, description)

        # Only keep jobs with decent match
        if score < 20:
            continue

        results.append({
            "match_score": score,
            "title": title,
            "company": row.get("company", ""),
            "location": location,
            "is_remote": is_remote,
            "job_type": row.get("job_type", ""),
            "salary_min": row.get("min_amount", ""),
            "salary_max": row.get("max_amount", ""),
            "date_posted": row.get("date_posted", ""),
            "apply_url": row.get("job_url", ""),
            "source": row.get("site", ""),
            "matched_keywords": ", ".join(matched_keywords[:8]),
            "description_snippet": description[:300].replace("\n", " "),
        })

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values("match_score", ascending=False)
    return result_df

def main():
    print("=" * 60)
    print("Job Matcher for Sayantani Nath")
    print("Roles: Data Engineer / Architect / Modeler / Warehouse")
    print("Location: SF Bay Area + US Remote/Hybrid")
    print("=" * 60)

    print("\nSearching jobs... (this takes 1-2 minutes)")
    df = search_jobs()

    print("\nScoring and filtering jobs...")
    results = process_jobs(df)

    if results.empty:
        print("No matching jobs found. Try again later.")
        return

    # Save to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"/Users/sayantaninath/Downloads/job_matches_{timestamp}.csv"
    results.to_csv(filename, index=False)

    # Print top 10
    print(f"\nTop {min(10, len(results))} Job Matches:\n")
    print("-" * 60)
    for _, row in results.head(10).iterrows():
        print(f"Score:    {row['match_score']}%")
        print(f"Title:    {row['title']}")
        print(f"Company:  {row['company']}")
        print(f"Location: {row['location']} {'(Remote)' if row['is_remote'] else ''}")
        print(f"Salary:   {row['salary_min']} - {row['salary_max']}")
        print(f"Keywords: {row['matched_keywords']}")
        print(f"Apply:    {row['apply_url']}")
        print("-" * 60)

    print(f"\nTotal matches found: {len(results)}")
    print(f"Full results saved to: {filename}")

if __name__ == "__main__":
    main()
