import json
import os
import requests

# NVIDIA CIK
cik="0001045810"

url=f"https://data.sec.gov/submissions/CIK{cik}.json" 

headers={
    "User-Agent": "AdaHo (tiny.excellencer@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}

# Folder/file to remember last seen filing
state_file = "state/last_seen.json"

# High-signal forms only
high_signal_forms = {"8-K", "10-Q", "10-K"}

# Get data from SEC 
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

# load previous filing if it exits
previous_filing = None
if os.path.exists(state_file):
    with open(state_file, "r") as f:
        previous_filing = json.load(f)  

# Compare with previous 
if previous_filing == latest_filing:
    print("No new filing detected")
else:
    print("New filings detected!")
    print("Previous:", previous_filing)
    print("Current:", latest_filing)

    # Save the new filing
    with open(state_file, "w") as f:
        json.dump(latest_filing, f, indent=2)

for i in range(5):
    print(f"{forms[i]} - {dates[i]}")
