import datetime
import pandas as pd
import numpy as np
# import talib
from typing import Dict, Any
from .grid_backtester import GridBacktester

class GridCalculator:
    def __init__(self):
        """初始化网格计算器"""
        self.volatility_range = (10, 30)   # 适合网格交易的波动率范围
        self.adx_threshold = 25             # ADX阈值
        self.adx_range = (15, 25)          # 添加ADX的理想范围
        self.band_ratio_threshold = 0.9     # 布林带内震荡比例阈值
        self.oscillation_range = (0.4, 0.8) # 震荡比例范围：最小0.6，最理想0.9
        self.initial_position_ratio = 0.5   # 添加初始建仓比例，默认50%

    def evaluate_grid_suitability(self, history_data: Dict[str, Any]) -> Dict[str, Any]:
        """评估ETF是否适合网格交易
        
        Args:
            history_data: 包含OHLCV数据的字典
            
        Returns:
            Dict[str, Any]: 评估结果
        """
        # 转换为DataFrame
        df = self._convert_to_dataframe(history_data)

        # 检查数据长度
        if len(df) < 45: # ADX等指标需要足够数据，45天是一个安全阈值
            return {
                'suitable': False,
                'reason': '数据周期太短（少于45天），无法进行有效分析。请选择更长的时间范围。',
                'scores': {'volatility_score': 0, 'trend_score': 0, 'oscillation_score': 0, 'safety_score': 0},
                'atr': 0
            }
        
        # 计算技术指标
        df = self._calculate_indicators(df)
        
        # 计算各维度得分
        scores = self._calculate_scores(df)

        # 判断是否适合网格交易
        suitable, reason = self._check_suitability(scores)
        
        # 获取最新的ATR值用于安全评分
        latest_atr = float(df['ATR'].iloc[-1])

        # 获取期初的ATR值用于构建网格，这更符合无未来函数的原则
        first_valid_atr_index = df['ATR'].first_valid_index()
        if first_valid_atr_index is not None:
            atr_for_grid = float(df['ATR'].loc[first_valid_atr_index])
        else:
            atr_for_grid = 0 # 如果无法计算ATR，则回退

        return {
            'suitable': suitable,
            'reason': reason,
            'scores': scores,
            'atr': round(atr_for_grid, 4)  # 返回用于构建网格的期初ATR
        }

    def _convert_to_dataframe(self, history_data: Dict[str, Any]) -> pd.DataFrame:
        """将历史数据转换为DataFrame格式"""
        df = pd.DataFrame({
            'date': pd.to_datetime(history_data['dates']),
            'open': history_data['open'],
            'high': history_data['high'],
            'low': history_data['low'],
            'close': history_data['close'],
            'volume': history_data['volume']
        }).set_index('date')
        return df

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        # 计算基于真实波动幅度的波动率
        df['true_range'] = pd.DataFrame({
            'hl': df['high'] - df['low'],
            'hc': abs(df['high'] - df['close'].shift(1)),
            'lc': abs(df['low'] - df['close'].shift(1))
        }).max(axis=1)
        
        # 计算日收益率
        df['daily_returns'] = df['close'].pct_change()
        
        # 根据数据长度动态调整波动率计算窗口
        data_length = len(df)
        if data_length <= 252:  # 1年数据
            volatility_window = 20
        elif data_length <= 504:  # 2年数据
            volatility_window = 40
        elif data_length <= 756:  # 3年数据
            volatility_window = 60
        else:  # 5年数据
            volatility_window = 100
            
        # 计算波动率，使用动态窗口
        df['volatility'] = df['daily_returns'].rolling(
            window=volatility_window
        ).std() * np.sqrt(252) * 100  # 年化并转换为百分比
        
        # # 计算ADX
        # df['ADX'] = talib.ADX(df['high'].values, df['low'].values,
        #                      df['close'].values, timeperiod=14)
        
        # # 计算ATR
        # df['ATR'] = talib.ATR(df['high'].values, df['low'].values,
        #                      df['close'].values, timeperiod=14)
        
        # # 计算布林带
        # df['upper_band'], df['middle_band'], df['lower_band'] = talib.BBANDS(
        #     df['close'].values, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        
        # 计算ADX
        def calculate_adx(high, low, close, period=14):
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
            atr = tr.rolling(window=period).mean()
            
            up_move = high - high.shift(1)
            down_move = low.shift(1) - low
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
            
            # 创建Series时指定正确的索引
            plus_di = 100 * pd.Series(plus_dm, index=high.index).rolling(window=period).mean() / atr
            minus_di = 100 * pd.Series(minus_dm, index=high.index).rolling(window=period).mean() / atr
            
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(window=period).mean()
            return adx
        
        # 计算ATR
        def calculate_atr(high, low, close, period=14):
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
            return tr.rolling(window=period).mean()
        
        # 计算布林带
        def calculate_bollinger_bands(close, period=20, num_std=1.8):
            middle_band = close.rolling(window=period).mean()
            std = close.rolling(window=period).std()
            upper_band = middle_band + (std * num_std)
            lower_band = middle_band - (std * num_std)
            return upper_band, middle_band, lower_band
        
        # ADX (Average Directional Index, 平均趋向指标)
        # - 用于判断市场趋势的强弱
        # - 取值范围0-100，一般认为：
        #   * ADX > 25：表示趋势较强，不适合网格交易
        #   * ADX < 25：表示趋势较弱，适合网格交易
        df['ADX'] = calculate_adx(df['high'], df['low'], df['close'])

        # ATR (Average True Range, 平均真实波幅)
        # - 衡量市场波动程度的指标
        # - 计算方法：取以下三个值中的最大值，再求N日平均：
        #   1. 当日最高价 - 当日最低价
        #   2. |当日最高价 - 昨日收盘价|
        #   3. |当日最低价 - 昨日收盘价|
        df['ATR'] = calculate_atr(df['high'], df['low'], df['close'])

        # 布林带 (Bollinger Bands)
        # - 由中轨（20日移动平均线）和上下轨（中轨±2倍标准差）组成
        # - 用途：
        #   * 价格在上下轨之间波动，适合网格交易
        #   * 价格突破上下轨，表示趋势较强，不适合网格交易
        # - 计算：
        #   * 中轨 = 20日移动平均线
        #   * 上轨 = 中轨 + 2倍标准差
        #   * 下轨 = 中轨 - 2倍标准差
        df['upper_band'], df['middle_band'], df['lower_band'] = calculate_bollinger_bands(df['close'])
        
        return df

    def _calculate_scores(self, df: pd.DataFrame) -> Dict[str, float]:
        """计算各维度得分"""
        # 获取最近数据
        recent_data = df.iloc[-252:]  # 使用最近一年数据
        
        # 波动性得分 - 使用整个周期的波动率均值，而不是仅取最后20天
        volatility = recent_data['volatility'].mean()  # 使用整个周期的平均波动率
        volatility_score = self._normalize_score(volatility, 
                                               self.volatility_range[0], 
                                               self.volatility_range[1]) * 100
        
        # 趋势强度得分 (ADX低分表示更适合)
        adx = recent_data['ADX'].tail(20).mean()  # 使用20日平均ADX
        # 使用分段函数计算趋势得分
        if adx <= self.adx_range[0]:  # ADX过低，说明缺乏波动
            trend_score = 60 * (adx / self.adx_range[0])  # 最高60分
        elif adx <= self.adx_range[1]:  # 理想区间
            trend_score = 60 + 40 * (adx - self.adx_range[0]) / (self.adx_range[1] - self.adx_range[0])
        else:  # ADX过高，趋势过强
            trend_score = max(0, 100 - 20 * (adx - self.adx_range[1]) / self.adx_range[1])
        
        # 震荡得分计算改进
        in_band = ((recent_data['close'] <= recent_data['upper_band']) & 
                  (recent_data['close'] >= recent_data['lower_band']))
        oscillation_ratio = in_band.mean()
        
        # 使用更严格的评分标准
        oscillation_score = 100 * self._normalize_score(
            oscillation_ratio,
            0.4,    # 低于50%得0分
            0.8     # 达到90%得满分
        )

        # 安全边际得分
        atr_ratio = recent_data['ATR'].iloc[-1] / recent_data['close'].iloc[-1]
        safety_score = 100 - self._normalize_score(atr_ratio, 0, 0.1) * 100
        
        # 处理 NaN 值
        scores = {
            'volatility_score': round(float(volatility_score), 2) if not np.isnan(volatility_score) else 0,
            'trend_score': round(float(trend_score), 2) if not np.isnan(trend_score) else 0,
            'oscillation_score': round(float(oscillation_score), 2) if not np.isnan(oscillation_score) else 0,
            'safety_score': round(float(safety_score), 2) if not np.isnan(safety_score) else 0
        }
        
        return scores

    def _normalize_score(self, value: float, min_val: float, max_val: float) -> float:
        """将数值标准化到0-1区间"""
        if value < min_val:
            return 0
        if value > max_val:
            return 1
        return (value - min_val) / (max_val - min_val)

    def _check_suitability(self, scores: Dict[str, float]) -> tuple:
        """根据得分判断是否适合网格交易"""
        # 计算综合得分
        weights = {
            'volatility_score': 0.3,
            'trend_score': 0.3,
            'oscillation_score': 0.25,
            'safety_score': 0.15
        }
        
        composite_score = sum(scores[k] * weights[k] for k in weights)
        composite_score = round(composite_score, 2)  # 保留两位小数
        
        # 生成详细评价
        analysis = []
        
        # 波动性评价
        if scores['volatility_score'] >= 80:
            analysis.append("波动率处于理想区间，非常适合网格交易")
        elif scores['volatility_score'] >= 60:
            analysis.append("波动率适中，适合网格交易")
        elif scores['volatility_score'] >= 40:
            analysis.append("波动率偏离理想区间，建议谨慎使用网格策略")
        else:
            analysis.append("波动率不适合网格交易，可能会影响策略收益")
            
        # 趋势评价
        if scores['trend_score'] >= 80:
            analysis.append("趋势强度适中，适合网格交易")
        elif scores['trend_score'] >= 60:
            analysis.append("趋势性较弱，可以考虑网格交易")
        elif scores['trend_score'] >= 40:
            analysis.append("趋势较强，建议适当调整网格区间")
        else:
            analysis.append("趋势过强，不建议使用网格策略")
            
        # 震荡评价
        if scores['oscillation_score'] >= 80:
            analysis.append("价格在布林带内震荡充分，非常适合网格交易")
        elif scores['oscillation_score'] >= 60:
            analysis.append("价格震荡特性良好，适合网格交易")
        elif scores['oscillation_score'] >= 40:
            analysis.append("价格震荡不充分，建议谨慎使用网格策略")
        else:
            analysis.append("价格震荡特性差，不适合网格交易")
            
        # 安全性评价
        if scores['safety_score'] >= 80:
            analysis.append("交易风险较低，可以考虑加大仓位")
        elif scores['safety_score'] >= 60:
            analysis.append("交易风险适中，建议使用正常仓位")
        elif scores['safety_score'] >= 40:
            analysis.append("交易风险较高，建议降低单次交易量")
        else:
            analysis.append("交易风险很高，建议谨慎参与")
        
        # 生成综合评价
        if composite_score >= 70:
            conclusion = "该ETF整体适合网格交易"
        elif composite_score >= 50:
            conclusion = "该ETF风险较高，建议调整参数后使用网格交易"
        else:
            conclusion = "该ETF不适合网格交易，建议使用其他策略"
            
        detailed_reason = f"{conclusion}（综合得分：{composite_score}分）。\n" + "\n".join(analysis)
        
        return composite_score >= 70, detailed_reason

    

    def run_backtest(self, history_data: Dict[str, Any], grid_count: int, initial_capital: float) -> Dict[str, Any]:
        """执行网格交易回测
        
        Args:
            history_data: 历史数据
            grid_count: 网格数量
            initial_capital: 初始资金
            
        Returns:
            Dict[str, Any]: 回测结果
        """
        
        # 创建回测器并执行回测
        backtester = GridBacktester(grid_count, initial_capital)
        result = backtester.run_backtest(history_data)
        
        # 转换回测结果为字典格式
        return {
            'total_return': round(result.total_return * 100, 2),
            'annual_return': round(result.annual_return * 100, 2),
            'max_drawdown': round(result.max_drawdown * 100, 2),
            'sharpe_ratio': round(result.sharpe_ratio, 2),
            'grid_return': round(result.grid_return * 100, 2),
            'hold_return': round(result.hold_return * 100, 2),
            'excess_return': round(result.excess_return * 100, 2),
            'trades': [
                {
                    'date': trade.date.strftime('%Y-%m-%d'),
                    'type': trade.type,
                    'price': round(trade.price, 2),
                    'quantity': round(trade.quantity, 2),
                    'amount': round(trade.amount, 2),
                    'profit': round(trade.profit, 2)
                }
                for trade in result.trades
            ],
            'daily_returns': [round(r * 100, 2) for r in result.daily_returns],
            'dates': [date.strftime('%Y-%m-%d') for date in result.dates],
            'prices': result.prices,  # 直接使用 BacktestResult 中的价格数据
            'grid_prices': result.grid_prices  # 直接使用 BacktestResult 中的网格价格数据
        }