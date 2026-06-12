"""
LinkedIn Job Matcher for Sayantani Nath
Searches jobs across LinkedIn and Indeed
Scores and ranks by resume match
Filters: based on SEARCH_MODE below
"""

from jobspy import scrape_jobs
import pandas as pd
from datetime import datetime
import re

# ── Search Configuration ────────────────────────────────────────────────────
# "remote_only"   — only true-remote US roles. Tightest filter.
# "sf_relocated"  — SF onsite/hybrid + any US location + remote. Broadest.
#                   Use this if (a) you've relocated to SF, or (b) you're
#                   pre-relocation but want a bigger sample size to measure
#                   recruiter behavior (e.g. testing L2 visa response rates).
SEARCH_MODE = "sf_relocated"

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
    "cloud", "cloud-native", "distributed", "streaming", "aws", "azure", "gcp",
    # Soft/domain
    "banking", "healthcare", "finance", "fintech", "enterprise",
    "performance tuning", "query optimization", "partitioning", "indexing",
]

# Broad set of titles covering how consulting/tech firms post these roles
TARGET_JOB_TITLES = [
    # Core engineering titles
    "Senior Data Engineer",
    "Lead Data Engineer",
    "Principal Data Engineer",
    "Staff Data Engineer",
    # Architect titles
    "Data Architect",
    "Senior Data Architect",
    "Lead Data Architect",
    "Enterprise Data Architect",
    "Cloud Data Architect",
    "Solutions Architect Data",
    # Modeler titles
    "Data Modeler",
    "Senior Data Modeler",
    "Data Modeling Engineer",
    # Warehouse / Platform titles
    "Data Warehouse Engineer",
    "Data Warehouse Architect",
    "Data Platform Engineer",
    "Data Infrastructure Engineer",
    "Data Platform Architect",
    # Consulting / big firm titles
    "Data Engineering Manager",
    "Data Analytics Engineer",
    "Senior Analytics Engineer",
]

def score_job(title, description):
    """Score a job 0-100 based on resume keyword match."""
    text = f"{title} {description}".lower()
    matched = [kw for kw in RESUME_SKILLS if kw.lower() in text]
    score = min(100, int((len(matched) / len(RESUME_SKILLS)) * 100 * 2.5))
    return score, matched

def is_relevant_location(location, is_remote):
    """Keep jobs based on SEARCH_MODE.

    Tightened 2026-05-19 because LinkedIn/Indeed often tag jobs `is_remote=True`
    while the location field still names a specific US city (e.g. "Houston, TX").
    For someone in India, those city-located "remote" tags are unreliable
    proxies — often the role is hybrid at the HQ city. So in remote_only mode
    we require an EXPLICIT remote signal in the location string OR an empty
    location with the API's remote flag — not a US city + remote flag.
    """
    loc = (location or "").lower().strip()

    if SEARCH_MODE == "remote_only":
        # Gold standard: explicit "remote" / "anywhere" / "work from home" in
        # the location string. Trust this.
        explicit_remote = any(k in loc for k in ("remote", "anywhere", "work from home"))
        if explicit_remote:
            return True
        # Empty / generic location + API says remote: provisionally trust.
        if is_remote and (not loc or loc == "nan" or loc in ("united states", "usa", "us")):
            return True
        # API flagged remote but the location names a specific US city: drop.
        # These are usually "remote at HQ city" hybrids in disguise.
        return False

    # sf_relocated mode: original behavior, accept any major US location.
    if is_remote:
        return True
    if not loc:
        return False
    us_indicators = [
        "san francisco", "bay area", "remote", "hybrid", "california", ", ca",
        "new york", "seattle", "chicago", "austin", "boston", "denver",
        "atlanta", "dallas", "washington", "united states", "usa", "anywhere",
        ", ny", ", tx", ", wa", ", il", ", ma", ", co", ", ga",
    ]
    return any(k in loc for k in us_indicators)

def format_salary(min_sal, max_sal, description=""):
    """Format salary — use structured fields first, fall back to parsing description."""
    try:
        if pd.notna(min_sal) and pd.notna(max_sal) and min_sal > 0:
            return f"${int(min_sal):,} - ${int(max_sal):,}"
        elif pd.notna(min_sal) and min_sal > 0:
            return f"${int(min_sal):,}+"
    except Exception:
        pass

    # Extract salary from description text (e.g. "$150,000 - $200,000" or "$150K - $200K")
    patterns = [
        r'\$[\d,]+[Kk]?\s*[-–to]+\s*\$[\d,]+[Kk]?',   # $150K - $200K or $150,000 - $200,000
        r'\$[\d,]+[Kk]?\s*(?:per year|annually|/yr)?',   # $150K per year
        r'[\d,]+[Kk]?\s*[-–]\s*[\d,]+[Kk]?\s*(?:USD|per year|annually)',  # 150K - 200K USD
    ]
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    return "Not listed"

def search_jobs():
    all_jobs = []

    for title in TARGET_JOB_TITLES:
        print(f"  Searching: {title}...")

        # Skip the SF Bay onsite/hybrid search in remote_only mode. Halves the
        # API calls and keeps the pool clean of roles she can't take from India.
        if SEARCH_MODE != "remote_only":
            try:
                sf_jobs = scrape_jobs(
                    site_name=["linkedin", "indeed"],
                    search_term=title,
                    location="San Francisco Bay Area, CA",
                    results_wanted=30,
                    hours_old=168,  # last 7 days
                    country_indeed="USA",
                    linkedin_fetch_description=True,
                    is_remote=False,
                )
                all_jobs.append(sf_jobs)
            except Exception as e:
                print(f"    SF search error for {title}: {e}")

        try:
            # US Remote jobs
            remote_jobs = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=title,
                location="United States",
                results_wanted=30,
                hours_old=168,  # last 7 days
                country_indeed="USA",
                linkedin_fetch_description=True,
                is_remote=True,
            )
            all_jobs.append(remote_jobs)
        except Exception as e:
            print(f"    Remote search error for {title}: {e}")

    if not all_jobs:
        print("No jobs found.")
        return pd.DataFrame()

    df = pd.concat(all_jobs, ignore_index=True)
    df = df.drop_duplicates(subset=["title", "company"], keep="first")
    print(f"\n  Total raw jobs scraped: {len(df)}")
    return df

# ── Visa restriction keywords — filter these jobs OUT ──────────────────────
VISA_RESTRICTED_KEYWORDS = [
    "must be a us citizen",
    "must be us citizen",
    "us citizens only",
    "usc only",
    "green card only",
    "security clearance required",
    "secret clearance",
    "top secret",
    "ts/sci",
    "dod clearance",
    "federal clearance",
    "must have green card",
    "permanent resident only",
    "gc only",
    "no visa candidates",
    "no opt candidates",
    "no cpt candidates",
    "citizens and green card",
    # Added 2026-05-18 after SailPoint slipped through with FedRAMP language.
    "fedramp",
    "us citizenship",
    "u.s. citizenship",
    "citizenship is required",
    "citizenship required",
    "requires us citizenship",
    "requires u.s. citizenship",
    "requires citizenship",
    "citizenship requirement",
]

def is_visa_restricted(description, title):
    """Return True if job is restricted to citizens/GC only."""
    text = f"{title} {description}".lower()
    return any(keyword in text for keyword in VISA_RESTRICTED_KEYWORDS)

def process_jobs(df):
    if df.empty:
        return df

    results = []
    visa_filtered = 0

    for _, row in df.iterrows():
        title = str(row.get("title", ""))
        description = str(row.get("description", ""))
        location = str(row.get("location", ""))
        is_remote = bool(row.get("is_remote", False))

        if not is_relevant_location(location, is_remote):
            continue

        # Filter out visa-restricted jobs
        if is_visa_restricted(description, title):
            visa_filtered += 1
            continue

        score, matched_keywords = score_job(title, description)

        if score < 20:
            continue

        # Check if job explicitly welcomes EAD/work authorisation
        ead_friendly = any(phrase in description.lower() for phrase in [
            "ead", "work authorization", "work authorisation",
            "authorized to work", "no sponsorship required",
            "all visa", "any visa", "l2", "l-2"
        ])

        results.append({
            "match_score": score,
            "title": title,
            "company": row.get("company", ""),
            "location": location,
            "is_remote": "Yes" if is_remote else "No",
            "job_type": row.get("job_type", ""),
            "salary": format_salary(row.get("min_amount"), row.get("max_amount"), description),
            "ead_friendly": "✅ Yes" if ead_friendly else "Check",
            "date_posted": row.get("date_posted", ""),
            "apply_url": row.get("job_url", ""),
            "source": row.get("site", ""),
            "matched_keywords": ", ".join(matched_keywords[:10]),
            "description_snippet": description[:400].replace("\n", " "),
        })

    print(f"  Visa-restricted jobs filtered out: {visa_filtered}")

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.sort_values("match_score", ascending=False)
    return result_df

def main():
    print("=" * 60)
    print("Job Matcher — Sayantani Nath")
    print("Roles: Data Engineer / Architect / Modeler / Warehouse")
    print(f"Mode: {SEARCH_MODE}")
    print("=" * 60)

    print("\nSearching jobs (this takes 3-5 minutes)...\n")
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

    # Print top 15
    print(f"\nTop {min(15, len(results))} Job Matches:\n")
    print("-" * 60)
    for _, row in results.head(15).iterrows():
        print(f"Score:    {row['match_score']}%")
        print(f"Title:    {row['title']}")
        print(f"Company:  {row['company']}")
        print(f"Location: {row['location']} | Remote: {row['is_remote']}")
        print(f"Salary:   {row['salary']}")
        print(f"Visa OK:  {row['ead_friendly']}")
        print(f"Posted:   {row['date_posted']}")
        print(f"Keywords: {row['matched_keywords']}")
        print(f"Apply:    {row['apply_url']}")
        print("-" * 60)

    # Summary stats
    with_salary = results[results["salary"] != "Not listed"]
    ead_friendly = results[results["ead_friendly"] == "✅ Yes"]
    print(f"\nTotal matches found:          {len(results)}")
    print(f"Jobs with salary listed:      {len(with_salary)}")
    print(f"EAD/visa-friendly confirmed:  {len(ead_friendly)}")
    print(f"Note: 'Check' jobs are likely fine for L2 EAD — just not explicitly stated")
    print(f"Full results saved to:        {filename}")

if __name__ == "__main__":
    main()
