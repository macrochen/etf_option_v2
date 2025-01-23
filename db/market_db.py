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

    def get_grid_trade_data(self, etf_code: str, months: int = 12) -> Dict[str, Any]:
        """获取网格交易所需的历史数据
        
        Args:
            etf_code: ETF代码
            months: 获取距今多少个月的数据，默认12个月
            
        Returns:
            Dict[str, Any]: 包含OHLCV、成交量等数据
        """
        results = self.db.fetch_all("""
            SELECT date, open_price, close_price, low_price, high_price,
                   volume, money, factor, high_limit, low_limit,
                   avg_price, pre_close, paused
            FROM grid_trade
            WHERE etf_code = ? 
            AND date >= date('now', ?) 
            ORDER BY date
        """, (etf_code, f'-{months} months'))
        
        if not results:
            return None
            
        return {
            'dates': [row[0] for row in results],
            'open': [row[1] for row in results],
            'close': [row[2] for row in results],
            'low': [row[3] for row in results],
            'high': [row[4] for row in results],
            'volume': [row[5] for row in results],
            'money': [row[6] for row in results],
            'factor': [row[7] for row in results],
            'high_limit': [row[8] for row in results],
            'low_limit': [row[9] for row in results],
            'avg_price': [row[10] for row in results],
            'pre_close': [row[11] for row in results],
            'paused': [row[12] for row in results]
        }