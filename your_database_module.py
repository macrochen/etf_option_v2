from db.market_db import MarketDatabase

# 假设您有一个配置文件来获取数据库路径
DB_PATH = 'path/to/your/market_data.db'
market_db = MarketDatabase(DB_PATH)

def get_buy_sell_signals(etf_code: str):
    """获取买卖点数据"""
    return market_db.get_buy_sell_signals(etf_code)

def get_price_data(etf_code: str):
    """获取价格数据"""
    return market_db.get_price_data(etf_code) 