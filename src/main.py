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

def clean_summary(text, max_length=600, max_sentences=5):
    import re
    from html import unescape

    if not text:
        return "No highlights available."
    
    #Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    #Convert HTML entities
    text = unescape(text)

    #Add spaces after punctuation if missing
    text = re.sub(r"([.,;:!?])([A-Za-z])", r"\1 \2", text)

    #Add spaces between lowercase-uppercase transitions (helps glued words occasionally)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)

    #Normalize whitespace
    text = re.sub(r"\s+", " ", text). strip()

    #If claeaning removed everythibng 
    if not text: 
        return "No hightlights available. "
    
    #Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)

    #Default to 3 sentences, allow up to 5 if content is long
    if len(sentences)<=3:
        summary = " ".join(sentences)
    else:
        summary = " ".join(sentences[:5])

    #Still cap excessive length
    if len(summary) > max_length:
        summary = summary[:max_length].rstrip() + "..."

    return summary


def fetch_rss_items():
    themes = load_feeds()
    results = {}

    for theme, urls in themes.items():
        results[theme] = []

        for url in urls: 
            parsed = feedparser.parse(url)

            for entry in parsed.entries[:5]:
                raw_summary = (
                    entry.get("summary")
                    or entry.get("description")
                    or entry.get("subtitle")
                    or ""
                )

                item = {
                    "title": entry.get("title", "No title"),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", "No published date"),
                    "summary": clean_summary(raw_summary)if raw_summary else "No highlights available."
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
def send_email(subject, body, is_html=False):
    if not SMTP_USER or not SMTP_PASS or not TO_EMAIL:
        raise ValueError(
            "Missing email environment variable(s)"
            "Click SMTP_USER, SMTP_PASS, and T)_EMAIL."
        )
    
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    if is_html:
        msg.attach(MIMEText(body, "html"))
    else:
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
            lines.append(f"=== {alert['ticker']} ({alert['name']}) ===")
            lines.append(f"Current: {alert['current']['form']} on {alert['current']['date']}")
            lines.append(f"Link   : {alert['current']['link']}")
            
            previous = alert.get("previous")

            if previous: 
                lines.append(f"Previous: {previous.get('form', 'N/A')} on {previous.get('date', 'N/A')}")
            else: 
                lines.append("Previous: None")
            
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

    html_parts = []
    html_parts.append(f"<h2 style='font-family: Arial, sans-serif; margin-bottom: 20px; text-align: left;'>Daily Digest - {digest_date}</h2>")

    for company in watchlist:
        ticker = company["ticker"]
        name = company["name"]
        cik = company["cik"]

        print(f"Digesting {ticker} ({name}) ...")

        latest_filing = fetch_latest_high_signal_filing(cik)
        previous = state.get(ticker)

        if latest_filing is None: 
            html_parts.append(f"<h3 style='font-family: Arial; sans-serif; margin-top: 24px; margin-bottom: 10px; text-align: left;'>{ticker}({name})</h3>")
            html_parts.append("<p style='font-family: Arial; sans-serif; font-size: 15px; line-height: 1.7; margin: 0 0 14px 0; text-align: left;'>No high-signal filing found / request failed.</p>")

            time.sleep(1)
            continue

        if previous != latest_filing:
            status = "NEW since last alert ✅"
        else: 
            status = "unchanged"

        html_parts.append(f"<h3 style='font-family: Arial; sans-serif; margin-top: 24px; margin-bottom: 10px; text-align: left;'>{ticker}({name})</h3>")
        html_parts.append(
            f"<p style='font-family: Arial; sans-serif; font-size: 15px; line-height: 1.7; margin: 0 0 14px 0; text-align: left;'>"
            f"<b>Latest:</b>{latest_filing['form']} on {latest_filing['date']}<br>"
            f"<b>Status:</b>{status}<br>"
            f"<b>Link:</b><a href='{latest_filing['link']}'>{latest_filing['link']}</a>"
            f"</p>"
        )

        time.sleep(1)

    # RSS section
    html_parts.append("<h2>Industry RSS Summary</h2>")

    for theme, items in rss_items.items():
        html_parts.append(f"<h3>{theme.upper()}</h3>")

        if not items: 
            html_parts.append(f"<p>No items found.</p>")
            continue

        for item in items[:10]:
            html_parts.append(
                f"<p><a href='{item.get('link', '')}'><b>{item.get('title', 'No title')}</b></a><br>"
                f" {item.get('summary', 'No highlights available.')}</p>"
            )


    body = "".join(html_parts)
    send_email(subject, body, is_html=True)
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
