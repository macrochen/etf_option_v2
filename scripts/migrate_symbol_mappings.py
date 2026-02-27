import sys
import os

# 将项目根目录添加到 python 路径
sys.path.append(os.getcwd())

from db.market_db import MarketDatabase

# 提取自 tiger_routes.py
HK_STOCK_NAMES = {
    '00388': '香港交易所', '09992': '泡泡玛特', '03750': '宁德时代', '00300': '美的集团',
    '00700': '腾讯控股', '01448': '福寿园', '02318': '中国平安', '02800': '盈富基金',
    '03032': '恒生科技ETF', '03069': '华夏恒生生科', '03690': '美团-W', '03968': '招商银行',
    '02020': '安踏体育', '02382': '舜宇光学', '09961': '携程集团', '01211': '比亚迪股份',
    '09999': '网易', '09618': '京东集团-SW', '09988': '阿里巴巴-W', '01810': '小米集团',
    '00016': '新鸿基地产',
}

# 提取自 futu_routes.py
STOCK_NAME_MAPPING = {
    '中国平安': '平安', '腾讯控股': '腾讯', '安踏体育': '安踏', '携程集团': '携程',
    '比亚迪股份': '比亚迪', '美团-W': '美团', '京东集团-SW': '京东', '阿里巴巴-W': '阿里',
    '小米集团': '小米', '香港交易所': '港交所', '新鸿基地产': '新鸿基',
}

def migrate():
    db = MarketDatabase()
    print("开始迁移港股名称映射...")
    count = 0
    for symbol, display_name in HK_STOCK_NAMES.items():
        short_name = STOCK_NAME_MAPPING.get(display_name)
        db.update_symbol_mapping(symbol, 'HK', display_name, short_name)
        print(f"已迁移: {symbol} -> {display_name} ({short_name or ''})")
        count += 1
    print(f"迁移完成，共处理 {count} 条记录。")

if __name__ == "__main__":
    migrate()
