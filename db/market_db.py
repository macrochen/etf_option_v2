import logging
import traceback
from typing import List, Dict, Any, Tuple
from .config import MARKET_DATA_DB  # 假设您有一个配置文件来获取数据库路径
from .database import Database  # 导入已有的 Database 类
from utils.fund_info_manager import FundInfoManager

class MarketDatabase:
    def __init__(self, db_path: str = MARKET_DATA_DB):
        """初始化市场数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db = Database(db_path)
        self.fund_info_manager = FundInfoManager(db_path)
        
    def save_grid_trade_data(self, etf_code: str, data: Dict[str, List[Any]]) -> None:
        """保存ETF数据到网格交易表
        
        Args:
            etf_code: ETF代码
            data: 包含OHLCV等数据的字典
        """
        # 获取基金名称
        fund_info = self.fund_info_manager.get_fund_info(etf_code)
        etf_name = fund_info["fund_name"] if fund_info else etf_code
        
        # 先删除已有数据
        self.db.execute("DELETE FROM grid_trade WHERE etf_code = ?", (etf_code,))
        
        # 逐条插入数据
        insert_sql = """
            INSERT INTO grid_trade (
                etf_code, etf_name, date, open_price, close_price, 
                low_price, high_price, volume
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        for i in range(len(data['date'])):
            # 跳过任何包含None的数据
            if None in [data['open'][i], data['close'][i], data['high'][i], data['low'][i]]:
                continue
                
            self.db.execute(insert_sql, (
                etf_code,
                etf_name,
                data['date'][i],
                data['open'][i],
                data['close'][i],
                data['low'][i],
                data['high'][i],
                data['volume'][i]
            ))
        
        self.db.commit()

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

    def get_grid_trade_data(self, etf_code: str, months: str | int) -> Dict[str, List] | None:
        """获取ETF的历史数据
        
        Args:
            etf_code: ETF代码
            months: 获取几个月的数据, 或者 'ytd' 表示今年以来
            
        Returns:
            Dict[str, List]: 历史数据字典
        """
        try:
            from datetime import datetime

            if str(months) == 'ytd':
                current_year = datetime.now().year
                start_date = f'{current_year}-01-01'
                sql = """
                    SELECT date, open_price, high_price, low_price, close_price, volume
                    FROM grid_trade
                    WHERE etf_code = ? 
                    AND date >= ?
                    ORDER BY date
                """
                params = (etf_code, start_date)
            else:
                # 确保 months 是整数
                months = int(months)
                sql = """
                    SELECT date, open_price, high_price, low_price, close_price, volume
                    FROM grid_trade
                    WHERE etf_code = ? 
                    AND date >= date('now', ?) 
                    ORDER BY date
                """
                params = (etf_code, f'-{months} months')

            results = self.db.fetch_all(sql, params)
            
            if not results:
                return None
                
            return {
                'dates': [r[0] for r in results],
                'open': [float(r[1]) for r in results],
                'high': [float(r[2]) for r in results],
                'low': [float(r[3]) for r in results],
                'close': [float(r[4]) for r in results],
                'volume': [float(r[5]) for r in results]
            }
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logging.error(f"获取ETF数据失败: \nETF代码: {etf_code}\n月数: {months}\n"
                         f"错误信息: {str(e)}\n堆栈信息:\n{stack_trace}")
            return None

    def get_grid_trade_data_by_date(self, etf_code: str, start_date: str, end_date: str = None) -> Dict[str, List] | None:
        """根据日期范围获取ETF数据
        
        Args:
            etf_code: ETF代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)，默认为今天
            
        Returns:
            Dict[str, List]: 历史数据字典
        """
        try:
            from datetime import datetime
            
            if not end_date:
                end_date = datetime.now().strftime('%Y-%m-%d')
                
            sql = """
                SELECT date, open_price, high_price, low_price, close_price, volume
                FROM grid_trade
                WHERE etf_code = ? 
                AND date >= ? AND date <= ?
                ORDER BY date
            """
            params = (etf_code, start_date, end_date)
            
            results = self.db.fetch_all(sql, params)
            
            if not results:
                return None
                
            return {
                'dates': [r[0] for r in results],
                'open': [float(r[1]) for r in results],
                'high': [float(r[2]) for r in results],
                'low': [float(r[3]) for r in results],
                'close': [float(r[4]) for r in results],
                'volume': [float(r[5]) for r in results]
            }
            
        except Exception as e:
            stack_trace = traceback.format_exc()
            logging.error(f"获取ETF数据失败(按日期): \nETF代码: {etf_code}\n日期范围: {start_date} - {end_date}\n"
                         f"错误信息: {str(e)}\n堆栈信息:\n{stack_trace}")
            return None

    def get_grid_trade_etf_list(self) -> List[Dict[str, Any]]:
        """获取网格交易ETF列表
        
        Returns:
            List[Dict[str, Any]]: ETF列表，包含代码、名称和起止时间
        """
        results = self.db.fetch_all("""
            SELECT DISTINCT 
                etf_code, 
                etf_name,
                MIN(date) as start_date,
                MAX(date) as end_date
            FROM grid_trade
            GROUP BY etf_code, etf_name
            ORDER BY etf_code
        """)
        
        return [
            {
                'code': row[0],
                'name': row[1] or row[0],  # 如果名称为空则显示代码
                'start_date': row[2],
                'end_date': row[3]
            }
            for row in results
        ]

    def get_etf_list(self) -> List[Dict[str, Any]]:
        """获取ETF列表及其数据的起止时间
        
        Returns:
            List[Dict[str, Any]]: ETF列表，包含代码和起止时间
        """
        results = self.db.fetch_all("""
            SELECT 
                etf_code,
                MIN(date) as start_date,
                MAX(date) as end_date
            FROM etf_daily
            GROUP BY etf_code
            ORDER BY etf_code
        """)
        
        if not results:
            return []
            
        return [
            {
                'etf_code': row[0],
                'start_date': row[1],
                'end_date': row[2]
            }
            for row in results
        ]