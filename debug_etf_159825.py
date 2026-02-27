
import pandas as pd
from grid.valuation_manager import ValuationManager
from grid.min_data_loader import MinDataLoader
from datetime import datetime

def analyze_etf_readiness(etf_code: str):
    """
    Analyzes if an ETF has enough data for similarity search.
    """
    print(f"--- Analyzing ETF: {etf_code} ---")
    
    vm = ValuationManager()
    dl = MinDataLoader()
    
    # --- Step 1: Check Price Data History ---
    print("\n[1/2] Checking ETF price data history...")
    price_data = dl.load_daily_data(etf_code)
    price_days = len(price_data)
    
    is_price_ready = price_days >= 60
    
    if price_days > 0:
        start_date = price_data['date'].min().strftime('%Y-%m-%d')
        end_date = price_data['date'].max().strftime('%Y-%m-%d')
        print(f"Found {price_days} days of price data.")
        print(f"Date Range: {start_date} -> {end_date}")
    else:
        print("Found 0 days of price data.")
        
    if is_price_ready:
        print("✅ OK: Price data history is sufficient (>= 60 days).")
    else:
        print(f"❌ FAIL: Price data history is NOT sufficient. Need >= 60 days, but found {price_days}.")

    # --- Step 2: Check Valuation Data History ---
    print("\n[2/2] Checking underlying index valuation history...")
    index_info = vm.get_index_for_etf(etf_code)
    
    if not index_info:
        print("❌ FAIL: Could not find the underlying index for this ETF.")
        print("--- Analysis Complete ---")
        return

    index_code = index_info['index_code']
    index_name = index_info['index_name']
    print(f"Underlying Index: {index_name} ({index_code})")
    
    # Force update and recalculate ranks to get the latest status
    print("Updating valuation data from API...")
    vm._update_valuation_from_api(index_code)
    print("Ensuring valuation ranks are calculated...")
    vm.ensure_valuation_ranks(index_code)
    
    # Load history after update
    val_data = vm.get_valuation_history(index_code)
    
    # The rank calculation requires min_periods=250. 
    # So we check how many data points have a valid rank.
    val_days_with_rank = val_data['pe_rank'].notna().sum()
    
    # Also check total valuation days available
    total_val_days = len(val_data)

    is_valuation_ready = val_days_with_rank > 0

    if total_val_days > 0:
        start_date = val_data.index.min().strftime('%Y-%m-%d')
        end_date = val_data.index.max().strftime('%Y-%m-%d')
        print(f"Found {total_val_days} days of total valuation data.")
        print(f"Date Range: {start_date} -> {end_date}")
        print(f"Number of days with a calculated percentile rank: {val_days_with_rank}")
    else:
        print("Found 0 days of valuation data.")

    # The condition `min_periods=250` in `ensure_valuation_ranks` means we need at least 250 days of data
    # for the *first* rank to be calculated.
    if total_val_days >= 250:
         print("✅ OK: Valuation data history is sufficient (>= 250 days).")
    else:
        print(f"❌ FAIL: Valuation data history is NOT sufficient. Need >= 250 days for calculation, but found {total_val_days}.")


    print("\n--- Analysis Complete ---")

if __name__ == "__main__":
    etf_to_check = "159825"
    analyze_etf_readiness(etf_to_check)
