import requests
import logging

logging.basicConfig(level=logging.INFO)

print("Testing Tencent HTTP Interface (Direct)...")

def get_tencent_price(symbols):
    """
    symbols: list of full codes (e.g. ['sh600519', 'sz000001'])
    """
    url = f"http://qt.gtimg.cn/q={','.join(symbols)}"
    try:
        resp = requests.get(url, timeout=5)
        print(f"Status Code: {resp.status_code}")
        # print(f"Raw: {resp.text}")
        
        results = {}
        if resp.status_code == 200:
            lines = resp.text.split(';')
            for line in lines:
                if '="' in line:
                    parts = line.split('="')
                    code = parts[0].split('_')[-1] # v_sh600519 -> sh600519
                    data = parts[1].strip('"').split('~')
                    if len(data) > 3:
                        name = data[1]
                        price = float(data[3])
                        print(f"Success {code} ({name}): {price}")
                        results[code] = price
        return results
    except Exception as e:
        print(f"Request Failed: {e}")
        return {}

test_codes = ['sh600519', 'sh510300', 'sh588000', 'sz000001']
get_tencent_price(test_codes)
