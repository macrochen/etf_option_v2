import akshare as ak
import pandas as pd

def check_etf_info(symbol):
    print(f"Checking info for ETF: {symbol}")
    try:
        # 尝试获取 ETF 基本信息
        # 注意：AKShare 的接口经常变动，我们尝试几个可能的接口
        
        # 1. 基金概况
        # fund_etf_fund_info_em 接口返回：基金代码, 基金简称, 成立日期, ...
        # 但可能不包含跟踪指数代码
        df_info = ak.fund_etf_fund_info_em(fund_code=symbol)
        print("--- Fund Info ---")
        print(df_info)
        
        # 2. 尝试从其他途径获取跟踪指数
        # 很多时候只能通过名称匹配，或者硬编码映射，或者看是否有 specific 接口
        # fund_portfolio_hold_em (持仓) 也没有指数信息
        
        # 尝试：stock_a_code_to_symbol 可能有？
        
    except Exception as e:
        print(f"Error fetching info: {e}")

def check_index_valuation(index_code):
    print(f"\nChecking valuation for Index: {index_code}")
    try:
        # 尝试获取指数估值
        # stock_zh_index_value_csindex: 中证指数估值
        # 注意：指数代码通常需要带后缀或者特定的格式
        
        # 比如 000300 -> 000300.SH or just 000300
        df = ak.index_value_hist_funddb(symbol="000300") # 韭圈儿数据，通常比较全
        print("--- Valuation Data (FundDB) ---")
        if not df.empty:
            print(df.head())
            print(df.columns)
        else:
            print("Empty dataframe")
            
    except Exception as e:
        print(f"Error fetching valuation: {e}")

if __name__ == "__main__":
    # 510300 -> 沪深300 (000300)
    # 588000 -> 科创50 (000688)
    check_index_valuation("000300")
