
import logging
from datetime import datetime
from grid.backtest_engine import BacktestEngine
from grid.grid_generator import GridGenerator
from grid.trade_executor import TradeExecutor

# 配置日志
logging.basicConfig(level=logging.INFO)

def simulate_backtest():
    # 模拟数据
    # 2025-08-15 buy 0.640
    # 2025-08-20 sell 0.649
    # 2025-08-22 sell 0.665
    
    dates = ['2024-08-15', '2024-08-16', '2024-08-19', '2024-08-20', '2024-08-21', '2024-08-22']
    closes = [0.640, 0.638, 0.642, 0.649, 0.655, 0.665]
    
    hist_data = {
        'dates': dates,
        'close': closes,
        'open': closes, # placeholder
        'high': closes, # placeholder
        'low': closes   # placeholder
    }
    
    engine = BacktestEngine(initial_capital=100000)
    
    print("Starting simulation...")
    result = engine.run_manual_backtest(
        hist_data=hist_data,
        grid_percent=2.88,
        grid_count=20,
        benchmark_annual_return=0.0,
        initial_base_price=0.640, # 明确指定基准价格
        trade_size=2000,          # 假设每格 2000
        initial_position_mode='full'
    )
    
    print("\nTrades:")
    for t in result.trades:
        print(f"{t.timestamp.date()} {t.direction} {t.price:.3f} Amt:{t.amount}")

    print("\nGrids around base:")
    # 找到 0.640 附近的网格
    sorted_grids = sorted(result.grids, key=lambda g: g.price)
    for g in sorted_grids:
        if 0.6 < g.price < 0.7:
            print(f"Grid: {g.price:.4f} Pos:{g.position} HasPos:{g.has_position}")

if __name__ == "__main__":
    simulate_backtest()
