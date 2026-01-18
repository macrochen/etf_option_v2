from grid.backtester import PathSimulator
from grid.models import GridLine
import pandas as pd
import logging

logging.basicConfig(level=logging.DEBUG)

def test_sell_logic():
    grid_lines = [
        GridLine(price=2.0, buy_vol=100, sell_vol=100),
        GridLine(price=2.5, buy_vol=100, sell_vol=100),
        GridLine(price=3.0, buy_vol=100, sell_vol=100),
        GridLine(price=3.5, buy_vol=100, sell_vol=100),
        GridLine(price=4.0, buy_vol=100, sell_vol=100),
    ]
    
    # Start at 3.0. Should fill base positions for grids >= 3.0?
    # Logic: start_idx = searchsorted(3.0) -> index 2 (3.0).
    # Loops 2, 3, 4. Grids 3.0, 3.5, 4.0 get positions.
    
    data = [
        {'date': '2023-01-01', 'open': 3.0, 'high': 3.0, 'low': 3.0, 'close': 3.0}, 
        {'date': '2023-01-02', 'open': 3.0, 'high': 3.6, 'low': 3.0, 'close': 3.6}, # Rise to 3.6. Should sell 3.0, 3.5
    ]
    df = pd.DataFrame(data)
    
    # 50% base position
    simulator = PathSimulator(grid_lines, initial_capital=10000, base_position_ratio=0.5)
    result = simulator.run(df)
    
    print(f"Total Trades: {len(result.trades)}")
    for t in result.trades:
        print(f"{t.date} {t.type} @ {t.price} vol:{t.volume}")

if __name__ == "__main__":
    test_sell_logic()