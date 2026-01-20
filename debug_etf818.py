import requests
import time

def debug_request():
    ts = int(time.time() * 1000)
    url = "https://etf818.com/fundex-quote/security/component/trackingIndex"
    params = {
        "securityCode": "510300.SH",
        "ts": ts
    }
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    
    print(f"Requesting: {url} with params {params}")
    try:
        resp = requests.get(url, params=params, headers=headers)
        print("Status:", resp.status_code)
        print("Text:", resp.text[:500]) # First 500 chars
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    debug_request()
