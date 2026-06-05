import json
import os
from pathlib import Path

import requests
import smtplib
import yaml
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart 

# ===========================
# Configuration
# ===========================

# Watchlist CIK 
WATCHLIST_FILE = "watchlist.yaml"
STATE_FILE = "state/last_seen.json"
USER_AGENT = "DeepTechAgent/1.0 (contact@example.com)"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
TO_EMAIL = os.getenv("TO_EMAIL")
USER_AGENT = os.getenv("USER_AGENT")

# High-signal forms only
high_signal_forms = {"8-K", "10-Q", "10-K"}

# ===========================
# HELPERS
# ===========================
def load_watchlist():
    with open(WATCHLIST_FILE, "r") as f:
        data = yaml.safe_load(f)
    return data["tickers"]

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
        "Host": "data.sec.gov",
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()  
    
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
            filing_link = f"https://www.sec.gov/Archives/edgar/data/{cik_ink}/{accession_nodash}/{primary_doc}"

            return {
                "form": form, 
                "date": date,
                "accession": accession,
                "primary_doc": primary_doc,
                "link": filing_link
            }
        
    return None 

# ===========================
# Main
# ===========================
def main():
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

        # Update state for this stock
        state[ticker] = latest_filing

        print()

    # Save updated state ONCE after the loop
    save_state(state)
    # Send one comnbined email if anything new
    if new_alerts:
        subject = f"[SEC Alerts]{len(new_alerts)} stock(s) with new filing(s)"
        
        lines = []
        lines.append("New high-signal SEC filings detected:\n")

        for alert in new_alerts:
            lines.append(f"{alert['ticker']} - ({alert['name']})")
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

if __name__ == "__main__":
    main()