from grid.etf818_client import Etf818Client
import json

def inspect_valuation_structure():
    client = Etf818Client()
    index_code = "000300.SH"
    
    print(f"Fetching PE history for {index_code}...")
    data = client.get_valuation_history(index_code, 'PE')
    
    print(f"Data Type: {type(data)}")
    if isinstance(data, list):
        print(f"Length: {len(data)}")
        if len(data) > 0:
            print("First item:", data[0])
    elif isinstance(data, dict):
        print("Keys:", data.keys())
        # Print a snippet
        print("Content snippet:", str(data)[:500])
    else:
        print("Data:", data)

if __name__ == "__main__":
    inspect_valuation_structure()
