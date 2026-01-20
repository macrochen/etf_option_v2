import sys
import os
import time
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from grid.min_data_loader import MinDataLoader

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def batch_download():
    loader = MinDataLoader()
    
    # 热门 ETF 列表
    etf_list = [
        '510050', # 上证50
        '510500', # 中证500
        '588000', # 科创50
        '588080', # 科创板
        '159915', # 创业板
        '159949', # 创业板50
        '512880', # 证券ETF
        '512000', # 券商ETF
        '512660', # 军工ETF
        '512480', # 半导体
        '515030', # 新能源车
        '512690', # 酒ETF
        '513050', # 中概互联
        '518880', # 黄金ETF
        '159919', # 沪深300ETF(深)
        '159922', # 中证500ETF(深)
    ]
    
    print(f"Starting batch download for {len(etf_list)} ETFs...")
    
    for symbol in etf_list:
        try:
            print(f"Downloading {symbol}...")
            success = loader.update_data(symbol)
            if success:
                print(f"✅ {symbol} Downloaded.")
            else:
                print(f"❌ {symbol} Failed.")
            
            # 礼貌性延时，防封 IP
            time.sleep(2)
            
        except Exception as e:
            print(f"Error processing {symbol}: {e}")

if __name__ == "__main__":
    batch_download()
