import json
import os
from pathlib import Path
import time 
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import smtplib
import yaml
import feedparser 
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart 

# ===========================
# Configuration
# ===========================

WATCHLIST_FILE = "watchlist.yaml"
FEEDS_FILE = "feeds.yaml"
STATE_FILE = "state/last_seen.json"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")
USER_AGENT = os.getenv("USER_AGENT") or "DeepTechAgent/1.0 (tiny.excellencer@gmail.com)"
RUN_MODE = os.getenv("RUN_MODE", "alert").lower()  

high_signal_forms = {"8-K", "10-Q", "10-K"}


# ===========================
# HELPERS
# ===========================
def load_watchlist():
    with open(WATCHLIST_FILE, "r") as f:
        data = yaml.safe_load(f)
    return data["tickers"]

def load_feeds():
    with open(FEEDS_FILE, "r") as f: 
        data = yaml.safe_load(f)
    return data["themes"]


def fetch_rss_items():
    themes = load_feeds()
    results = {}

    for theme, urls in themes.items():
        results[theme] = []

        for url in urls: 
            parsed = feedparser.parse(url)

            for entry in parsed.entries[:5]:
                item = {
                    "title": entry.get("title", "No title"),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", "No published date"),
                }
                results[theme].append(item)

    return results


def load_state():
    state_path = Path(STATE_FILE)
    if not state_path.exists():
        return {}
    with open(state_path, "r") as f:
        return json.load(f)
    
def save_state(state):
     state_path = Path(STATE_FILE)
     state_path.parent.mkdir(parents=True, exist_ok=True)
     with open(state_path, "w") as f:
         json.dump(state, f, indent=2)

# ===========================
# Email Function
# ===========================
def send_email(subject, body):
    print("DEBUG SMTP_USER =", repr(SMTP_USER))
    print("DEBUG SMTP_PASS loaded =", SMTP_PASS is not None)
    print("DEBUG TO_EMAIL =", repr(TO_EMAIL))

    if not SMTP_USER or not SMTP_PASS or not TO_EMAIL:
        raise ValueError(
            "Missing email environment variable(s)"
            "Click SMTP_USER, SMTP_PASS, and T)_EMAIL."
        )
    
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def fetch_latest_high_signal_filing(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
        "Host": "data.sec.gov",
    }
    
    for _ in range(2):  # Retry up to 3 times
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            break
        time.sleep(1)
    
    
    if response.status_code != 200:
        print(f"SEC request failed for CIK {cik}: {response.status_code}")
        print("Response review:", response.text[:200])
        return None  
    
    data=response.json()
    recent=data["filings"]["recent"]

    forms=recent["form"]
    dates=recent["filingDate"]
    accessions = recent["accessionNumber"]
    primary_docs = recent["primaryDocument"]

    for form, date, accession, primary_doc in zip(forms, dates, accessions, primary_docs):
        if form in high_signal_forms:
            accession_nodash = accession.replace("-", "")
            cik_ink = str(int(cik))  # Remove leading zeros for URL 
            filing_link = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_ink}/{accession_nodash}/{primary_doc}"
            )

            return {
                "form": form, 
                "date": date,
                "accession": accession,
                "primary_doc": primary_doc,
                "link": filing_link
            }
        
    return None 

# ===========================
# Alert mode
# ===========================
def run_alert_mode():
    watchlist = load_watchlist()
    state = load_state() 

    print("Checking watchlist ...\n ")

    new_alerts = []

    # Loop through watchlist and check for new filings
    for company in watchlist:
        ticker = company["ticker"]
        name = company["name"]
        cik = company["cik"]

        print(f"Checking {ticker} ({name}) ...")

        latest_filing = fetch_latest_high_signal_filing(cik)

        if latest_filing is None:
            print(f"No high-signal filings found for {ticker}.\n")
            time.sleep(1)
            continue

        previous_filing = state.get(ticker) 

        print(f"Latest filing: {latest_filing}")

        if previous_filing == latest_filing:
            print(f"No new filing detected for {ticker}.")
        else:
            print(f"New filing detected for {ticker}!")
            print(f"Previous: {previous_filing}")
            print(f"Current: {latest_filing}")

            # Only collect alerts here
            new_alerts.append({
                "ticker": ticker,
                "name": name,
                "previous": previous_filing,  
                "current": latest_filing
            })

            state[ticker] = latest_filing    # Update state for this stock

        print()
        time.sleep(1)

    save_state(state)   # Save updated state ONCE after the loop

    # Send one comnbined email if anything new
    if new_alerts:
        subject = f"[SEC Alerts]{len(new_alerts)} stock(s) with new filing(s)"
        
        lines = []
        lines.append("New high-signal SEC filings detected:\n")

        for alert in new_alerts:
            lines.append(f"==={alert['ticker']} ({alert['name']})===")
            lines.append(
                f"  Current: {alert['current']['form']} on {alert['current']['date']}"
            )
            lines.append(f"  Link: {alert['current']['link']}")
            lines.append(f"  Previous: {alert['previous']}")
            lines.append("")

        body = "\n".join(lines)

        send_email(subject, body)
        print("Email sent successfully")
    else:
        print("No new filings across the watchlist.")

# ===========================
# Digest mode
# ===========================
def run_digest_mode():
    watchlist = load_watchlist()
    state = load_state()
    rss_items = fetch_rss_items()

    digest_date = datetime.now(ZoneInfo("America/Toronto")).date().isoformat()
    subject = f"[Daily Digest {digest_date}] SEC Filing Summary & Industry News"

    print("Building daily digest ...\n")

    lines = []
    lines.append(f"Daily SEC filing summary for {digest_date}\n")

    for company in watchlist:
        ticker = company["ticker"]
        name = company["name"]
        cik = company["cik"]

        print(f"Digesting {ticker} ({name}) ...")

        latest_filing = fetch_latest_high_signal_filing(cik)
        previous = state.get(ticker)
        if previous != latest_filing:
            status = "NEW Today✅"
        else: 
            status = "unchanged"

        if latest_filing is None:
            lines.append(f"==={ticker} ({name})===")
            lines.append("Latest:  No high-signal filings found/ request failed")
            lines.append("")
            time.sleep(1)
            continue

        lines.append(f"==={ticker} ({name})===")
        lines.append(
            f"  Latest: {latest_filing['form']} on {latest_filing['date']}"
        )
        lines.append(f"  Status: {status}")
        lines.append(f"  Link: {latest_filing['link']}")
        lines.append("")

        time.sleep(1)

    if len(lines) <=1: 
        print("Digest empty - skipping email")
        return

    lines.append("=== Industry RSS Summary ===")
    lines.append("")

    for theme, items in rss_items.items():
        lines.append(f"[{theme.upper()}]")

        if not items: 
            lines.append("No items found.")
            lines.append("")
            continue

        for item in items[:10]:
            lines.append(f"-{item['title']}")
            lines.append(f" Link{item['link']}")
            lines.append(f"")
        
        lines.append("")

    body = "\n".join(lines)

    send_email(subject, body)
    print("Daily digest email sent successfully!")


# ===========================
# Main
# ===========================
def main():
    if RUN_MODE == "digest":
        run_digest_mode()
    else:
        run_alert_mode()


if __name__ == "__main__":
    main()
