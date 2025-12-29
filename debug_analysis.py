
import logging
from datetime import datetime
from grid.backtest_engine import BacktestEngine
from grid.parameter_analyzer import ParameterAnalyzer

logging.basicConfig(level=logging.INFO)

def simulate_analysis():
    # 模拟数据
    dates = ['2024-01-01', '2024-01-02', '2024-01-03', '2024-01-04']
    closes = [1.0, 1.05, 0.95, 1.0]
    opens = [1.0, 1.0, 1.0, 0.95]
    highs = [1.05, 1.1, 1.0, 1.02]
    lows = [0.95, 1.0, 0.9, 0.95]
    
    hist_data = {
        'dates': dates,
        'close': closes,
        'open': opens,
        'high': highs,
        'low': lows
    }
    
    analyzer = ParameterAnalyzer(initial_capital=100000)
    print("Starting analysis simulation...")
    
    try:
        results = analyzer.analyze(
            hist_data=hist_data,
            atr=0.02,
            benchmark_annual_return=0.1,
            top_n=5
        )
        print(f"Analysis complete. Found {len(results)} results.")
        for res in results:
            print(f"Score: {res.evaluation['total_score']:.2f}, Params: {res.params}")
            
    except Exception as e:
        import traceback
        print(f"Error during analysis: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    simulate_analysis()
