from typing import List, Dict, Any, Tuple
from .config import MARKET_DATA_DB  # 假设您有一个配置文件来获取数据库路径
from .database import Database  # 导入已有的 Database 类

class MarketDatabase:
    def __init__(self, db_path: str = MARKET_DATA_DB):
        """初始化市场数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db = Database(db_path)

    def get_buy_sell_signals(self, etf_code: str, trend_indicator: str) -> Dict[str, List[Dict[str, Any]]]:
        """获取指定ETF的买卖点数据
        
        Args:
            etf_code: ETF代码
            indicator_type: 指标类型
            
        Returns:
            Dict[str, List[Dict[str, Any]]]: 买卖点数据
        """
        # 根据指标类型获取买卖点数据的逻辑
        result = self.db.fetch_one("""
            SELECT Buy_Signal, Sell_Signal
            FROM combined_signals
            WHERE etf_code = ? and trend_indicator = ?
        """, (etf_code, trend_indicator))

        if result:
            buy_signals = result[0].split(',') if result[0] else []
            sell_signals = result[1].split(',') if result[1] else []
            return {
                'buy': [{'date': date, 'price': self.get_price_by_date(etf_code, date)} for date in buy_signals],
                'sell': [{'date': date, 'price': self.get_price_by_date(etf_code, date)} for date in sell_signals]
            }
        return {'buy': [], 'sell': []}

    def get_price_by_date(self, etf_code: str, date: str) -> float:
        """根据日期获取指定ETF的价格
        
        Args:
            etf_code: ETF代码
            date: 日期
            
        Returns:
            float: 指定日期的收盘价
        """
        result = self.db.fetch_one("""
            SELECT close_price
            FROM etf_daily
            WHERE etf_code = ? AND date = ?
        """, (etf_code, date))
        return result[0] if result else 0.0

    def get_price_data(self, etf_code: str) -> Tuple[List[float], List[str]]:
        """获取指定ETF的价格数据
        
        Args:
            etf_code: ETF代码
            
        Returns:
            Tuple[List[float], List[str]]: 价格和日期列表
        """
        results = self.db.fetch_all("""
            SELECT close_price, date
            FROM etf_daily
            WHERE etf_code = ?
            ORDER BY date
        """, (etf_code,))
        
        prices = [row[0] for row in results]
        dates = [row[1] for row in results]
        
        return prices, dates 