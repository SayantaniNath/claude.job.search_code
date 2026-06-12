"""
Daily Job Email — sends top 10 unseen jobs to Sayantani at 7 PM.
Marks sent jobs as "Emailed" in the tracker so they don't repeat.
"""

import pandas as pd
import subprocess
import os
import sys
from datetime import datetime
from glob import glob

TRACKER_FILE = "/Users/sayantaninath/Downloads/application_tracker.csv"
TO_EMAIL = "sayantaninath91@gmail.com"


def get_all_jobs():
    files = glob("/Users/sayantaninath/Downloads/job_matches_*.csv")
    if not files:
        return None
    dfs = []
    for f in files:
        try:
            dfs.append(pd.read_csv(f))
        except Exception:
            continue
    df = pd.concat(dfs, ignore_index=True)
    return df.drop_duplicates(subset=["apply_url"], keep="first")


def get_already_seen():
    if os.path.exists(TRACKER_FILE):
        tracker = pd.read_csv(TRACKER_FILE)
        return set(tracker["apply_url"].dropna().tolist())
    return set()


def mark_as_emailed(rows):
    entries = []
    for _, row in rows.iterrows():
        entries.append({
            "date_applied": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "title": row.get("title", ""),
            "company": row.get("company", ""),
            "location": row.get("location", ""),
            "salary": row.get("salary", ""),
            "match_score": row.get("match_score", ""),
            "ead_friendly": row.get("ead_friendly", ""),
            "apply_url": row.get("apply_url", ""),
            "status": "Emailed",
            "notes": "",
        })
    new_df = pd.DataFrame(entries)
    if os.path.exists(TRACKER_FILE):
        tracker = pd.read_csv(TRACKER_FILE)
        tracker = pd.concat([tracker, new_df], ignore_index=True)
    else:
        tracker = new_df
    tracker.to_csv(TRACKER_FILE, index=False)


def build_email_body(jobs, today):
    lines = [f"Your top {len(jobs)} job matches — {today}\n"]
    for i, (_, row) in enumerate(jobs.iterrows(), 1):
        salary = row.get("salary", "Not listed") or "Not listed"
        remote = "Remote" if str(row.get("is_remote", "")).lower() == "yes" else "On-site/Hybrid"
        visa = row.get("ead_friendly", "Check")
        lines.append(
            f"{i}. {row['title']} — {row['company']}\n"
            f"   {row.get('location', 'N/A')} | {remote} | {salary} | Visa: {visa}\n"
            f"   {row['apply_url']}\n"
        )
    lines.append("Good luck! Run the assistant to apply: python ~/claude_job_linkedin/apply_assistant.py")
    return "\n".join(lines)


def send_via_mail_app(subject, body, to):
    escaped_body = body.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "Mail"
    set newMsg to make new outgoing message with properties {{subject:"{subject}", content:"{escaped_body}", visible:false}}
    tell newMsg
        make new to recipient with properties {{address:"{to}"}}
    end tell
    send newMsg
end tell
'''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.returncode == 0, result.stderr


def main():
    today = datetime.now().strftime("%Y-%m-%d")

    df = get_all_jobs()
    if df is None:
        print("No job files found.")
        sys.exit(1)

    already_seen = get_already_seen()
    df = df[~df["apply_url"].isin(already_seen)]
    df = df.sort_values("match_score", ascending=False).head(10).reset_index(drop=True)

    if df.empty:
        print("No new jobs to email — all jobs have been seen.")
        sys.exit(0)

    body = build_email_body(df, today)
    subject = f"Your Top {len(df)} Job Matches — {today}"

    ok, err = send_via_mail_app(subject, body, TO_EMAIL)
    if ok:
        mark_as_emailed(df)
        print(f"[{datetime.now()}] Email sent with {len(df)} jobs. Marked as Emailed in tracker.")
    else:
        print(f"[{datetime.now()}] Failed to send email: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
