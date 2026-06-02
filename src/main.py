import json
import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart 

# ===========================
# Configuration
# ===========================

# NVIDIA CIK
cik="0001045810"

# SEC request settings
url=f"https://data.sec.gov/submissions/CIK{cik}.json" 
headers={
    "User-Agent": "AdaHo (tiny.excellencer@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}

# Email settings (temporory local test version)
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = "tiny.excellencer@gmail.com"
smtp_pass = "77804Ada"  # Replace with your actual password or use an app-specific password
to_email = "tiny.excellencer@gmail.com"

# Folder/file to remember last seen filing
state_file = "state/last_seen.json"

# High-signal forms only
high_signal_forms = {"8-K", "10-Q", "10-K"}


# ===========================
# Email Function
# ===========================
def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


# ===========================
# Get Data from SEC
# ===========================
response = requests.get(url, headers=headers, timeout=30)
response.raise_for_status()  

data = response.json()
recent=data["filings"]["recent"]    

forms=recent["form"]
dates=recent["filingDate"]

latest_filing = None

# Find the first high-signal filing
for form, date in zip(forms, dates):
    if form in high_signal_forms:
        latest_filing = {"form":form, "date":date} 
        break   

if latest_filing is None:
    print("No high-signal filings found.")
    exit()

print("Latest high-signal filing from SEC:")
print(latest_filing)

# ===========================
# Load previous state
# ===========================
previous_filing = None
if os.path.exists(state_file):
    with open(state_file, "r") as f:
        previous_filing = json.load(f)  

# ===========================
# Compare + Alert
# ===========================
if previous_filing == latest_filing:
    print("No new filing detected")
else:
    print("New filings detected!")
    print("Previous:", previous_filing)
    print("Current:", latest_filing)

    subject = f"[SEC Alert] NVIDIA new filing: {latest_filing['form']}"
    body = (
        f"New high-signal SEC filing detected for NVIDIA.:\n\n"
        f"Form: {latest_filing['form']}\n"
        f"Date: {latest_filing['date']}\n\n"
        f"Previous filing:\n{previous_filing}\n"
        f"Current filing:\n{latest_filing}\n"
    )

    send_email(subject, body)
    print("Email sent successfully!")

    # Save the new filing
    with open(state_file, "w") as f:
        json.dump(latest_filing, f, indent=2)

for i in range(5):
    print(f"{forms[i]} - {dates[i]}")
