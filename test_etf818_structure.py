from grid.etf818_client import Etf818Client
import json

def inspect_valuation_structure():
    client = Etf818Client()
    index_code = "000300.SH" # 沪深300
    
    print(f"Fetching PE history for {index_code}...")
    data = client.get_valuation_history(index_code, 'PE')
    
    if data and len(data) > 0:
        print(f"Got {len(data)} records.")
        first_item = data[0]
        print("First item structure:")
        print(json.dumps(first_item, indent=2, ensure_ascii=False))
        
        # 检查是否每个item都有相同的key
        keys = set(first_item.keys())
        print(f"Keys: {keys}")
    else:
        print("No data returned or error occurred.")

if __name__ == "__main__":
    inspect_valuation_structure()
