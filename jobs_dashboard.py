"""
Job dashboard generator.

Reads the newest ~/Downloads/job_matches_*.csv, applies Sayantani's standing
filters (titles, remote-anywhere or SF-only-hybrid, posted within the last
7 days, not already in the application tracker), and writes a self-contained
HTML dashboard to ~/Downloads/jobs_dashboard.html.

Usage:
    python jobs_dashboard.py            # generate + print the file path
    open ~/Downloads/jobs_dashboard.html

The page has its own controls: freshness (24h / 3d / 7d), title search,
minimum score, and SF-only toggle. Data is embedded — no server needed.
"""

import glob
import html
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

DOWNLOADS = Path.home() / "Downloads"
TRACKER = DOWNLOADS / "application_tracker.csv"
OUT = DOWNLOADS / "jobs_dashboard.html"

TITLE_RE = re.compile(
    r"data\s*(?:architect|engineer|platform|model)|analytics\s*engineer", re.I
)
SF_RE = re.compile(r"san francisco|sf bay|bay area", re.I)


def newest_matches_csv():
    files = sorted(glob.glob(str(DOWNLOADS / "job_matches_*.csv")))
    if not files:
        raise SystemExit("No job_matches_*.csv found — run job_matcher.py first.")
    return files[-1]


def load_jobs():
    src = newest_matches_csv()
    df = pd.read_csv(src)

    seen = set()
    if TRACKER.exists():
        seen = set(pd.read_csv(TRACKER)["apply_url"].dropna())

    df = df[df["title"].astype(str).str.contains(TITLE_RE)]
    df = df[~df["apply_url"].isin(seen)]

    loc = df["location"].astype(str)
    is_remote = df["is_remote"].astype(str).str.lower().isin(["true", "1", "yes"]) | \
        loc.str.contains("remote", case=False)
    is_sf = loc.str.contains(SF_RE)
    df = df[is_remote | is_sf]

    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    df = df[df["date_posted"].notna() & (df["date_posted"].astype(str) >= cutoff)]

    df = df.sort_values("match_score", ascending=False)

    jobs = []
    for _, r in df.iterrows():
        jobs.append({
            "score": int(r.get("match_score", 0) or 0),
            "title": str(r.get("title", "")),
            "company": str(r.get("company", "")),
            "location": "" if pd.isna(r.get("location")) else str(r.get("location")),
            "salary": "" if pd.isna(r.get("salary")) or str(r.get("salary")) == "Not listed"
                      else str(r.get("salary")),
            "ead": str(r.get("ead_friendly", "")),
            "posted": str(r.get("date_posted", "")),
            "source": str(r.get("source", "")),
            "keywords": "" if pd.isna(r.get("matched_keywords")) else str(r.get("matched_keywords")),
            "snippet": "" if pd.isna(r.get("description_snippet"))
                       else str(r.get("description_snippet"))[:400],
            "url": str(r.get("apply_url", "")),
            "sf": bool(SF_RE.search(str(r.get("location", "")))),
        })
    return jobs, Path(src).name


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Job Dashboard — Sayantani</title>
<style>
  :root {{
    --bg: #03030a; --card: #0c0c14; --border: #1a1a2e;
    --text: #e8eaf6; --muted: #8a8fb0; --accent: #6366f1;
    --accent-light: #818cf8; --green: #10b981; --cyan: #06b6d4;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  ::selection {{ background: rgba(99,102,241,0.6); color: #fff; -webkit-text-fill-color: #fff; }}
  body {{ font-family: -apple-system, 'Inter', sans-serif; background: var(--bg);
         color: var(--text); line-height: 1.5; padding: 32px 20px; }}
  .wrap {{ max-width: 880px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  h1 span {{ background: linear-gradient(135deg, #6366f1, #06b6d4);
             -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }}
  .meta {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  .controls {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 22px; align-items: center; }}
  .controls button {{ background: var(--card); color: var(--text); border: 1px solid var(--border);
       padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; }}
  .controls button.active {{ border-color: var(--accent); color: var(--accent-light);
       background: rgba(99,102,241,0.12); }}
  .controls input {{ background: var(--card); color: var(--text); border: 1px solid var(--border);
       padding: 7px 12px; border-radius: 8px; font-size: 13px; min-width: 180px; }}
  .count {{ color: var(--muted); font-size: 13px; margin-bottom: 14px; }}
  .job {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px;
          padding: 18px 20px; margin-bottom: 14px; }}
  .job:hover {{ border-color: rgba(99,102,241,0.45); }}
  .job-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }}
  .job-title {{ font-size: 16px; font-weight: 700; }}
  .job-title a {{ color: var(--text); text-decoration: none; }}
  .job-title a:hover {{ color: var(--accent-light); }}
  .score {{ font-size: 12px; font-weight: 700; color: var(--green);
            border: 1px solid rgba(16,185,129,0.4); padding: 2px 9px; border-radius: 999px;
            white-space: nowrap; }}
  .job-sub {{ color: var(--muted); font-size: 13px; margin: 5px 0 8px; }}
  .job-sub b {{ color: var(--cyan); font-weight: 600; }}
  .snippet {{ font-size: 13px; color: #b9bdd6; margin-bottom: 10px; }}
  .tags {{ font-size: 11px; color: var(--muted); margin-bottom: 12px; }}
  .apply {{ display: inline-block; background: var(--accent); color: #fff; text-decoration: none;
            font-size: 13px; font-weight: 600; padding: 7px 16px; border-radius: 8px; }}
  .apply:hover {{ background: var(--accent-light); }}
  .empty {{ color: var(--muted); padding: 40px 0; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Jobs matching <span>your profile</span></h1>
  <div class="meta">Generated {generated} · source: {source} · already-applied roles excluded</div>
  <div class="controls">
    <button data-days="1">Last 24h</button>
    <button data-days="3">Last 3 days</button>
    <button data-days="7" class="active">Last week</button>
    <button id="sfToggle">SF / hybrid only</button>
    <input id="search" placeholder="Search title or company…">
  </div>
  <div class="count" id="count"></div>
  <div id="list"></div>
</div>
<script>
const JOBS = {jobs_json};
const GENERATED = new Date("{generated_iso}");
let days = 7, sfOnly = false, q = "";

function render() {{
  const cutoff = new Date(GENERATED - days * 864e5);
  const rows = JOBS.filter(j => {{
    if (new Date(j.posted) < cutoff) return false;
    if (sfOnly && !j.sf) return false;
    if (q && !(j.title + " " + j.company).toLowerCase().includes(q)) return false;
    return true;
  }});
  document.getElementById("count").textContent =
    rows.length + " job" + (rows.length === 1 ? "" : "s") + " shown";
  document.getElementById("list").innerHTML = rows.length ? rows.map(j => `
    <div class="job">
      <div class="job-head">
        <div class="job-title"><a href="${{j.url}}" target="_blank">${{j.title}} — ${{j.company}}</a></div>
        <div class="score">${{j.score}} match</div>
      </div>
      <div class="job-sub">${{j.location || "Location n/a"}} · <b>${{j.salary || "Salary not listed"}}</b>
        · EAD: ${{j.ead || "check"}} · posted ${{j.posted}} · ${{j.source}}</div>
      ${{j.snippet ? `<div class="snippet">${{j.snippet}}…</div>` : ""}}
      ${{j.keywords ? `<div class="tags">matched: ${{j.keywords}}</div>` : ""}}
      <a class="apply" href="${{j.url}}" target="_blank">Apply ↗</a>
    </div>`).join("") : '<div class="empty">No jobs in this window — widen the filter or refresh the matcher.</div>';
}}

document.querySelectorAll("[data-days]").forEach(b => b.onclick = () => {{
  days = +b.dataset.days;
  document.querySelectorAll("[data-days]").forEach(x => x.classList.toggle("active", x === b));
  render();
}});
document.getElementById("sfToggle").onclick = e => {{
  sfOnly = !sfOnly; e.target.classList.toggle("active", sfOnly); render();
}};
document.getElementById("search").oninput = e => {{ q = e.target.value.toLowerCase(); render(); }};
render();
</script>
</body>
</html>
"""


def main():
    jobs, source = load_jobs()
    now = datetime.now()
    OUT.write_text(PAGE.format(
        generated=now.strftime("%Y-%m-%d %H:%M"),
        generated_iso=now.isoformat(),
        source=html.escape(source),
        jobs_json=json.dumps(jobs),
    ))
    print(f"{len(jobs)} jobs → {OUT}")


if __name__ == "__main__":
    main()
