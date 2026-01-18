from grid.backtester import PathSimulator
from grid.strategy import SmartGridStrategy
from grid.models import GridContext
from grid.data_loader import GridDataLoader
import pandas as pd
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)

def test_full_flow_510300():
    symbol = '510300'
    loader = GridDataLoader()
    
    print(f"1. Loading data for {symbol}...")
    df = loader.load_daily_data(symbol)
    if df.empty:
        print("Error: No data.")
        return
        
    current_price = loader.get_latest_price(symbol)
    print(f"Latest price (DB): {current_price}")
    
    # 2. Generate Strategy
    print("\n2. Generating Strategy...")
    context = GridContext(
        symbol=symbol,
        current_price=current_price,
        total_capital=100000,
        base_position_ratio=0.0, # Try 0 base position first
        pe_percentile=50,
        pb_percentile=50
    )
    
    strategy = SmartGridStrategy(context)
    strat_result = strategy.generate(df)
    
    print(f"Strategy Mode: {strat_result.mode}")
    print(f"Range: {strat_result.price_min} - {strat_result.price_max}")
    print(f"Step: {strat_result.step_price}")
    print(f"Grids: {len(strat_result.grid_lines)}")
    # print([g.price for g in strat_result.grid_lines])
    
    # 3. Run Backtest (Last 365 days)
    print("\n3. Running Backtest (Last 365 days)...")
    backtest_days = 365
    start_date = (datetime.now() - timedelta(days=backtest_days)).strftime('%Y-%m-%d')
    backtest_df = df[df['date'] >= start_date].copy()
    
    print(f"Backtest Date Range: {backtest_df.iloc[0]['date']} to {backtest_df.iloc[-1]['date']}")
    print(f"Start Price: {backtest_df.iloc[0]['open']}")
    
    simulator = PathSimulator(
        grid_lines=strat_result.grid_lines,
        initial_capital=100000,
        base_position_ratio=0.0
    )
    
    bt_result = simulator.run(backtest_df)
    
    # 4. Analyze
    buys = [t for t in bt_result.trades if t.type == 'BUY']
    sells = [t for t in bt_result.trades if t.type == 'SELL']
    
    print(f"\n--- Results ---")
    print(f"Total Trades: {len(bt_result.trades)}")
    print(f"Buys: {len(buys)}")
    print(f"Sells: {len(sells)}")
    
    if len(sells) == 0 and len(buys) > 0:
        print("\n!!! REPRODUCED: All Buys, No Sells !!!")
        print("Checking first 5 buys:")
        for t in buys[:5]:
            print(f"{t.date} BUY {t.volume} @ {t.price}")
            
        print("\nChecking price path around first buy:")
        first_buy_date = buys[0].date
        # Find data around this date
        idx = backtest_df[backtest_df['date'] == first_buy_date].index[0]
        print(df.loc[idx:idx+5][['date', 'open', 'high', 'low', 'close']])

if __name__ == "__main__":
    test_full_flow_510300()