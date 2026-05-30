#!/usr/bin/env python3
"""
L1 Blanket Visa Slot Agent
Monitors ais.usvisa-info.com for open L1/NIV interview appointment slots
and sends an email alert the moment one becomes available.

Setup:
  1. Copy .env.example to .env and fill in your credentials.
  2. pip install -r requirements.txt
  3. python l1_visa_slot_agent.py          # runs continuously
     python l1_visa_slot_agent.py --once   # single check and exit
"""

import os
import re
import time
import logging
import smtplib
import argparse
import requests
from datetime import datetime, date
from typing import List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ──────────────────────────────────────────────────────────────

COUNTRY_CODE   = os.getenv("COUNTRY_CODE", "in")          # 'in' for India
CONSUL_CITY    = os.getenv("CONSUL_CITY", "Chennai")
FACILITY_ID    = int(os.getenv("FACILITY_ID", "89"))      # see FACILITY_IDS dict below
SCHEDULE_ID    = os.getenv("SCHEDULE_ID", "")             # digits from your AIS dashboard URL
VISA_USERNAME  = os.getenv("VISA_USERNAME", "")
VISA_PASSWORD  = os.getenv("VISA_PASSWORD", "")
NOTIFY_EMAIL   = os.getenv("NOTIFY_EMAIL", "")
SMTP_SERVER    = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME  = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MINUTES", "15"))
DATE_FROM      = os.getenv("PREFERRED_DATE_FROM", "")     # YYYY-MM-DD  (leave blank = any date)
DATE_TO        = os.getenv("PREFERRED_DATE_TO", "")       # YYYY-MM-DD  (leave blank = any date)

# Known AIS facility IDs for India (verify on the site — they can change)
FACILITY_IDS = {
    "Chennai":   89,
    "Mumbai":    90,
    "Hyderabad": 91,
    "Delhi":     92,
    "Kolkata":   93,
}

AIS_BASE = "https://ais.usvisa-info.com"

# ── Logging ────────────────────────────────────────────────────────────────────

def _setup_logging() -> logging.Logger:
    log_file = f"visa_slot_agent_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )
    return logging.getLogger(__name__)

log = _setup_logging()

# ── AIS Portal Agent ───────────────────────────────────────────────────────────

class AISPortalAgent:
    """Handles authenticated access to ais.usvisa-info.com."""

    def __init__(self, country_code: str, username: str, password: str,
                 schedule_id: str, facility_id: int):
        self.country_code = country_code
        self.username     = username
        self.password     = password
        self.schedule_id  = schedule_id
        self.facility_id  = facility_id
        self._logged_in   = False

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })

    # ── internal helpers ───────────────────────────────────────────────────────

    @property
    def _niv(self) -> str:
        return f"{AIS_BASE}/en-{self.country_code}/niv"

    def _appt_base(self) -> str:
        return f"{self._niv}/schedule/{self.schedule_id}/appointment"

    def _json_headers(self) -> dict:
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self._appt_base(),
        }

    # ── login ──────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        sign_in = f"{self._niv}/users/sign_in"
        try:
            resp = self.session.get(sign_in, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("Could not reach AIS login page: %s", exc)
            return False

        csrf = re.search(r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"', resp.text)
        if not csrf:
            log.error("CSRF token not found — page structure may have changed")
            return False

        payload = {
            "utf8": "✓",
            "authenticity_token": csrf.group(1),
            "user[email]": self.username,
            "user[password]": self.password,
            "policy_confirmed": "1",
            "commit": "Sign In",
        }

        try:
            resp = self.session.post(
                sign_in, data=payload,
                headers={"Referer": sign_in},
                timeout=30, allow_redirects=True,
            )
        except requests.RequestException as exc:
            log.error("Login POST failed: %s", exc)
            return False

        if "sign_in" in resp.url:
            log.error("Login rejected — check VISA_USERNAME / VISA_PASSWORD in .env")
            return False

        # Try to auto-discover schedule_id from the post-login dashboard
        if not self.schedule_id:
            m = re.search(r"/schedule/(\d+)/", resp.text)
            if m:
                self.schedule_id = m.group(1)
                log.info("Auto-discovered schedule ID: %s", self.schedule_id)

        self._logged_in = True
        log.info("Logged in as %s", self.username)
        return True

    def _ensure_session(self) -> bool:
        if not self._logged_in:
            return self.login()
        return True

    # ── slot queries ───────────────────────────────────────────────────────────

    def get_available_dates(self) -> List[str]:
        """Return list of date strings (YYYY-MM-DD) that have open slots."""
        if not self._ensure_session():
            return []
        if not self.schedule_id:
            log.error(
                "SCHEDULE_ID is empty. "
                "Find it in your AIS dashboard URL: /schedule/<ID>/appointment"
            )
            return []

        url = f"{self._appt_base()}/days/{self.facility_id}.json"
        try:
            resp = self.session.get(
                url,
                params={"appointments[expedite]": "false"},
                headers=self._json_headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            log.error("Network error fetching dates: %s", exc)
            return []

        if resp.status_code == 401:
            log.warning("Session expired — re-authenticating")
            self._logged_in = False
            if self.login():
                return self.get_available_dates()
            return []

        if not resp.ok:
            log.error("Dates endpoint returned HTTP %d", resp.status_code)
            return []

        try:
            return [entry["date"] for entry in resp.json() if entry.get("date")]
        except ValueError:
            log.error("Unexpected response format for dates")
            return []

    def get_available_times(self, date_str: str) -> List[str]:
        """Return list of time strings available on a given date."""
        url = f"{self._appt_base()}/times/{self.facility_id}.json"
        try:
            resp = self.session.get(
                url,
                params={"date": date_str, "appointments[expedite]": "false"},
                headers=self._json_headers(),
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("available_times", [])
        except (requests.RequestException, ValueError) as exc:
            log.error("Error fetching times for %s: %s", date_str, exc)
            return []


# ── Date filtering ─────────────────────────────────────────────────────────────

def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def filter_dates(dates: List[str], from_str: str, to_str: str) -> List[str]:
    """Keep only dates within [from_str, to_str].  Empty strings = no bound."""
    d_from = _parse_date(from_str)
    d_to   = _parse_date(to_str)
    result = []
    for ds in dates:
        d = _parse_date(ds)
        if d is None:
            continue
        if d_from and d < d_from:
            continue
        if d_to and d > d_to:
            continue
        result.append(ds)
    return result


# ── Notifications ──────────────────────────────────────────────────────────────

def send_email_alert(slots: List[dict], consul_city: str,
                     to_addr: str, smtp_user: str, smtp_pass: str,
                     smtp_server: str, smtp_port: int):
    if not to_addr or not smtp_user or not smtp_pass:
        log.warning("Email not configured — skipping notification (set NOTIFY_EMAIL, SMTP_USERNAME, SMTP_PASSWORD)")
        return

    subject = f"🟢 L1 Visa slot available in {consul_city}!"

    lines = [f"Available appointment slots at the US Consulate in {consul_city}:\n"]
    for s in slots:
        times = ", ".join(s["times"]) if s["times"] else "times not fetched"
        lines.append(f"  • {s['date']}  —  {times}")
    lines.append(f"\nBook now: {AIS_BASE}")
    body = "\n".join(lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_user
    msg["To"]      = to_addr
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_addr], msg.as_string())
        log.info("Email alert sent to %s", to_addr)
    except smtplib.SMTPException as exc:
        log.error("Failed to send email: %s", exc)


def console_alert(slots: List[dict], consul_city: str):
    banner = "=" * 60
    print(f"\n{banner}")
    print(f"  ✅  VISA SLOT AVAILABLE — {consul_city.upper()}")
    print(banner)
    for s in slots:
        times = ", ".join(s["times"]) if s["times"] else "(times unknown)"
        print(f"  📅  {s['date']}   🕐  {times}")
    print(f"\n  Book at: {AIS_BASE}")
    print(f"{banner}\n")


# ── Core check ─────────────────────────────────────────────────────────────────

def check_slots(agent: AISPortalAgent, date_from: str, date_to: str,
                consul_city: str, fetch_times: bool = True) -> List[dict]:
    """
    Run one slot check. Returns list of dicts {date, times} for open slots
    within the preferred date range.
    """
    all_dates = agent.get_available_dates()

    if not all_dates:
        log.info("No open dates found at %s", consul_city)
        return []

    filtered = filter_dates(all_dates, date_from, date_to)
    if not filtered:
        log.info(
            "Found %d open date(s) at %s but none within preferred range [%s – %s]",
            len(all_dates), consul_city,
            date_from or "any", date_to or "any",
        )
        log.info("Open dates (outside range): %s", ", ".join(all_dates[:10]))
        return []

    log.info("🟢 Found %d slot(s) in range at %s: %s", len(filtered), consul_city, ", ".join(filtered))

    slots = []
    for d in filtered:
        times = agent.get_available_times(d) if fetch_times else []
        slots.append({"date": d, "times": times})

    return slots


# ── Main loop ──────────────────────────────────────────────────────────────────

def run_loop(agent: AISPortalAgent, args: argparse.Namespace):
    check_count = 0
    notified_dates: set = set()

    while True:
        check_count += 1
        log.info(
            "Check #%d — %s consulate (facility %d)",
            check_count, CONSUL_CITY, FACILITY_ID,
        )

        slots = check_slots(agent, DATE_FROM, DATE_TO, CONSUL_CITY)

        if slots:
            new_slots = [s for s in slots if s["date"] not in notified_dates]
            if new_slots:
                console_alert(new_slots, CONSUL_CITY)
                send_email_alert(
                    new_slots, CONSUL_CITY,
                    NOTIFY_EMAIL, SMTP_USERNAME, SMTP_PASSWORD,
                    SMTP_SERVER, SMTP_PORT,
                )
                for s in new_slots:
                    notified_dates.add(s["date"])

        if args.once:
            break

        log.info("Next check in %d minute(s)…", CHECK_INTERVAL)
        time.sleep(CHECK_INTERVAL * 60)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="L1 Blanket visa slot monitor")
    p.add_argument("--once", action="store_true",
                   help="Run a single check then exit (useful for cron)")
    p.add_argument("--list-facilities", action="store_true",
                   help="Print known India facility IDs and exit")
    p.add_argument("--country", default=COUNTRY_CODE,
                   help="AIS country code, e.g. 'in' (default: %(default)s)")
    p.add_argument("--city", default=CONSUL_CITY,
                   help="Consulate city name (default: %(default)s)")
    p.add_argument("--facility-id", type=int, default=FACILITY_ID,
                   help="AIS facility ID (default: %(default)s)")
    return p.parse_args()


def main():
    args = parse_args()

    if args.list_facilities:
        print("Known AIS facility IDs for India:")
        for city, fid in FACILITY_IDS.items():
            print(f"  {city:12s} → {fid}")
        return

    # Validate required config
    missing = [k for k, v in {
        "VISA_USERNAME": VISA_USERNAME,
        "VISA_PASSWORD": VISA_PASSWORD,
    }.items() if not v]
    if missing:
        log.error("Missing required config: %s — copy .env.example to .env and fill it in", ", ".join(missing))
        return

    if not SCHEDULE_ID:
        log.warning(
            "SCHEDULE_ID not set — will try to auto-discover after login. "
            "If that fails, find it in your AIS dashboard URL: "
            "https://ais.usvisa-info.com/en-in/niv/schedule/<SCHEDULE_ID>/appointment"
        )

    effective_facility = args.facility_id
    if args.city != CONSUL_CITY and args.city in FACILITY_IDS:
        effective_facility = FACILITY_IDS[args.city]

    agent = AISPortalAgent(
        country_code=args.country,
        username=VISA_USERNAME,
        password=VISA_PASSWORD,
        schedule_id=SCHEDULE_ID,
        facility_id=effective_facility,
    )

    log.info(
        "Starting L1 visa slot agent | Consulate: %s (facility %d) | Interval: %d min",
        args.city, effective_facility, CHECK_INTERVAL,
    )
    if DATE_FROM or DATE_TO:
        log.info("Preferred date range: %s → %s", DATE_FROM or "any", DATE_TO or "any")

    run_loop(agent, args)


if __name__ == "__main__":
    main()
