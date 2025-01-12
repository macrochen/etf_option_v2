import os

# 数据库文件路径配置
DB_DIR = os.path.dirname(os.path.abspath(__file__))
MARKET_DATA_DB = os.path.join(DB_DIR, 'market_data.db')
BACKTEST_SCHEMES_DB = os.path.join(DB_DIR, 'backtest_schemes.db')

# 数据库连接配置
DB_CONFIG = {
    'market_data': {
        'path': MARKET_DATA_DB
    },
    'backtest_schemes': {
        'path': BACKTEST_SCHEMES_DB
    }
} 