import sys
import os
import logging

# 临时清除代理设置
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)

# 配置日志输出到控制台
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 添加项目根目录到 python path，以便导入 services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.price_service import PriceService

def test_price_fetch():
    print("-" * 50)
    print("开始验证 Akshare 价格获取功能...")
    print("-" * 50)

    # 构造测试数据
    test_assets = [
        # --- 场内 ETF ---
        {'symbol': '510300', 'asset_type': 'etf', 'name': '沪深300ETF'},
        {'symbol': '588000', 'asset_type': 'etf', 'name': '科创50ETF'},
        
        # --- 个股 ---
        {'symbol': '600519', 'asset_type': 'stock', 'name': '贵州茅台'},
        {'symbol': '00700', 'asset_type': 'stock', 'name': '腾讯控股(不支持港股)'}, # 测试不支持的情况
        
        # --- 场外基金 ---
        {'symbol': '110011', 'asset_type': 'fund', 'name': '易方达中小盘'},
        {'symbol': '000001', 'asset_type': 'fund', 'name': '华夏成长'}, # 注意：000001 既是平安银行又是华夏成长，靠 asset_type 区分
        
        # --- 现金 ---
        {'symbol': 'CNY', 'asset_type': 'cash', 'name': '人民币'},
    ]

    try:
        # 调用批量获取接口
        print(f"正在请求 {len(test_assets)} 个资产的最新价格，请稍候...")
        prices = PriceService.get_batch_prices(test_assets)
        
        print("-" * 50)
        print(f"{'代码':<10} | {'名称':<15} | {'类型':<8} | {'最新价/净值':<10}")
        print("-" * 50)
        
        for asset in test_assets:
            symbol = asset['symbol']
            price = prices.get(symbol)
            
            status = f"{price:.4f}" if price is not None else "获取失败"
            print(f"{symbol:<10} | {asset['name']:<15} | {asset['asset_type']:<8} | {status}")
            
    except Exception as e:
        print(f"测试过程发生严重错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_price_fetch()
