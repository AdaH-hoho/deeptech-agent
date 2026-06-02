import requests

# NVIDIA CIK
cik="0001045810"

url=f"https://data.sec.gov/submissions/CIK{cik}.json"

headers={
    "User-Agent": "AdaHo (tiny.excellencer@gmail.com)",
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov"
}

response = requests.get(url, headers=headers, timeout=30)

print("Status Code: ",response.status_code)   
print("Content-Type: ",response.headers.get("Content-Type"))
print("First 300 characters of the response content:")
print(response.text[:300])

# Stop here first if the reposnse isn't OK
response.raise_for_status()  

data = response.json()

recent=data["filings"]["recent"]    

print("\nLatest filings for NVIDIA:\n")

forms=recent["form"]
dates=recent["filingDate"]

for i in range(5):
    print(f"{forms[i]} - {dates[i]}")
