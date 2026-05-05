# LinkedIn Job Matcher — Sayantani Nath

An AI-powered Python script that automatically searches LinkedIn and Indeed for matching data jobs, scores them against your resume, and exports the top matches to a CSV file.

---

## What This Does

1. **Searches** LinkedIn and Indeed for jobs matching your target roles
2. **Filters** for San Francisco Bay Area + US Remote/Hybrid positions
3. **Scores** each job against your resume keywords (0–100%)
4. **Ranks** jobs by match score
5. **Exports** top matches to a CSV file in your Downloads folder

---

## Target Job Roles

- Senior / Lead / Principal / Staff Data Engineer
- Data Architect / Senior Data Architect
- Data Modeler / Senior Data Modeler
- Data Warehouse Engineer
- Data Infrastructure Engineer
- Data Platform Engineer

---

## Resume Keywords Used for Matching

The script scores jobs based on how many of these skills appear in the job description:

| Category | Keywords |
|----------|---------|
| Core | data modeling, data warehouse, ETL, ELT, pipeline |
| Technologies | Snowflake, Oracle, PostgreSQL, SQL, Kafka, Redis, Python, Talend |
| Architecture | Data Vault 2.0, Star Schema, Kimball, OLAP, OLTP, SCD |
| Specialties | data governance, MDM, data quality, data lineage, performance tuning |
| Domains | banking, healthcare, finance, enterprise, cloud-native |

---

## Setup

### 1. Prerequisites
- Python 3.10+
- `uv` or `pip`

### 2. Install Dependencies

Using `uv` (recommended):
```bash
uv pip install python-jobspy pandas
```

Or using `pip`:
```bash
pip install python-jobspy pandas
```

### 3. Run the Script
```bash
python job_matcher.py
```

---

## Output

The script prints the **top 10 matches** to the terminal:

```
Score:    85%
Title:    Senior Data Engineer
Company:  Stripe
Location: San Francisco, CA
Salary:   $180,000 - $220,000
Keywords: snowflake, data modeling, etl, kafka, sql, python
Apply:    https://linkedin.com/jobs/view/...
```

And saves **all matches** to a CSV file:
```
~/Downloads/job_matches_YYYYMMDD_HHMM.csv
```

### CSV Columns
| Column | Description |
|--------|-------------|
| match_score | % match with resume (0–100) |
| title | Job title |
| company | Company name |
| location | Job location |
| is_remote | True if remote |
| salary_min / salary_max | Salary range (if listed) |
| date_posted | When job was posted |
| apply_url | Direct link to apply |
| source | linkedin or indeed |
| matched_keywords | Which resume keywords matched |
| description_snippet | First 300 chars of job description |

---

## How the Scoring Works

```
score = (matched_keywords / total_resume_keywords) × 100 × 2.5
```

- Jobs scoring **below 20%** are filtered out
- Jobs are **sorted highest to lowest** score
- Score is **capped at 100%**

---

## Customisation

### Change job titles to search
Edit the `TARGET_JOB_TITLES` list in `job_matcher.py`:
```python
TARGET_JOB_TITLES = [
    "Senior Data Engineer",
    "Data Architect",
    # add more here
]
```

### Change location
Edit the `LOCATIONS` list or the `location` parameter in `scrape_jobs()`:
```python
location="New York, NY"   # change city
is_remote=True            # remote only
```

### Change how recent jobs must be
```python
hours_old=72   # last 3 days (default)
hours_old=168  # last 7 days
```

### Add your own resume keywords
Edit the `RESUME_SKILLS` list:
```python
RESUME_SKILLS = [
    "your skill here",
    ...
]
```

---

## Limitations

- **LinkedIn / Indeed rate-limit** scraping — run once a day max
- **Glassdoor / ZipRecruiter** currently block automated access
- **Salary** is not always listed by employers
- Job descriptions vary in quality — some may score lower than expected

---

## Recommended Daily Workflow

```
Morning routine:
1. Run: python job_matcher.py
2. Open CSV in Excel/Google Sheets
3. Review top 10–15 matches
4. Apply to top matches via the apply_url links
```

---

## Tech Stack

| Tool | Purpose |
|------|---------|
| `python-jobspy` | Scrapes LinkedIn and Indeed |
| `pandas` | Data processing and CSV export |
| `Python 3.14` | Runtime |

---

## Author

**Sayantani Nath** — Senior Data Engineer (Architect-Modeler)  
San Francisco Bay Area | sayantaninath91@gmail.com  
[LinkedIn](https://linkedin.com/in/sayantani-nath-a252502) | [GitHub](https://github.com/sayantaninath)
