from grid.etf818_client import Etf818Client
import logging

logging.basicConfig(level=logging.INFO)

def test_client():
    client = Etf818Client()
    
    # 1. Test Tracking Index
    print("Fetching tracking index for 510300...")
    idx = client.get_tracking_index("510300.SH")
    print("Index Info:", idx)
    
    if idx:
        idx_code = idx['index_code']
        # 2. Test Valuation
        print(f"\nFetching PE history for {idx_code}...")
        pe_hist = client.get_valuation_history(idx_code, 'PE')
        if pe_hist:
            print(f"Got {len(pe_hist)} records")
            print("First:", pe_hist[0])
            print("Last:", pe_hist[-1])
        else:
            print("No PE data")

if __name__ == "__main__":
    test_client()
