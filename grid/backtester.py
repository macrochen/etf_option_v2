import pandas as pd
import numpy as np
from typing import List, Dict
from .models import GridLine, BacktestResult, TradeRecord

import logging

class VirtualAccount:
    def __init__(self, initial_cash: float, initial_positions: Dict[int, int] = None):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.positions = initial_positions or {} # {grid_index: volume}
        
        self.total_cost = 0.0 
        self.realized_profit = 0.0 
        self.trade_records = []
        
    def get_total_volume(self):
        return sum(self.positions.values())

    def buy(self, date, price, volume, grid_index):
        cost = price * volume
        if self.cash < cost:
            # logging.debug(f"Buy failed: No cash. Req: {cost}, Avail: {self.cash}")
            return False 
            
        self.cash -= cost
        self.total_cost += cost
        
        # 增加持仓
        current_vol = self.positions.get(grid_index, 0)
        self.positions[grid_index] = current_vol + volume
        
        # 记录快照
        total_vol = self.get_total_volume()
        pos_val = total_vol * price
        
        self.trade_records.append(TradeRecord(
            date=str(date),
            type='BUY',
            price=price,
            volume=volume,
            amount=cost,
            current_position=total_vol,
            position_value=pos_val,
            cash=self.cash,
            total_value=self.cash + pos_val
        ))
        return True

    def sell(self, date, price, volume, grid_index):
        # 检查该格子是否有持仓
        current_vol = self.positions.get(grid_index, 0)
        if current_vol < volume:
            # logging.debug(f"Sell failed: No pos at idx {grid_index}. Req: {volume}, Has: {current_vol}")
            return False 
            
        revenue = price * volume
        self.cash += revenue
        self.total_cost -= revenue 
        
        # 扣减持仓
        self.positions[grid_index] = current_vol - volume
        
        # 记录快照
        total_vol = self.get_total_volume()
        pos_val = total_vol * price
        
        self.trade_records.append(TradeRecord(
            date=str(date),
            type='SELL',
            price=price,
            volume=volume,
            amount=revenue,
            current_position=total_vol,
            position_value=pos_val,
            cash=self.cash,
            total_value=self.cash + pos_val
        ))
        return True
        
    def get_equity(self, current_price):
        market_value = sum(vol for vol in self.positions.values()) * current_price
        return self.cash + market_value

class PathSimulator:
    def __init__(self, grid_lines: List[GridLine], initial_capital: float, base_position_ratio: float = None):
        self.grid_lines = sorted(grid_lines, key=lambda x: x.price) # 升序
        self.account = None
        self.initial_capital = initial_capital
        self.base_pos_ratio = base_position_ratio
        
        # 预计算网格查找表
        self.prices = np.array([g.price for g in self.grid_lines])
        self.buy_vols = [g.buy_vol for g in self.grid_lines]
        self.sell_vols = [g.sell_vol for g in self.grid_lines]
        
        # 网格状态追踪: {grid_index: bool} True=持有, False=空仓
        # 用于防止在同一价格反复买入 (Over-Accumulation)
        self.grid_states = {}
        
    def _init_account(self, start_price):
        """初始化账户，建立底仓"""
        # 找到当前价格在网格中的位置
        start_idx = int(np.searchsorted(self.prices, start_price))
        
        # 自动计算底仓逻辑：
        # 如果是回测，为了模拟"中途入场"的真实状态，底仓比例应该与当前价格位置挂钩。
        # 例如：价格在网格中位，应持有 50% 仓位。
        # 逻辑：应持有数量 = 低于当前价格的网格数量 * 单格数量
        # (这响应了用户的需求："应该买入当前价格到网格下限的网格数量")
        
        # 优先使用传入的比例，如果为 None 则自动计算
        if self.base_pos_ratio is None:
            # 自动模式：假设下方每个格子都已买入
            # 注意：sell_vols 对应的是 grid[i]。我们假设持有 i 的 stock 是为了在 i+1 卖出?
            # 简单起见，假设下方每个格子都贡献一份标准 sell_vol
            # standard_vol = np.median(self.sell_vols) if self.sell_vols else 0
            # base_vol = start_idx * standard_vol
            
            # 更精确：累加下方所有格子的买入量？
            # 或者是：为了能在 start_idx...N 卖出，我们需要填充这些格子
            # 实际上，"中性网格"要求：价格在 K，持有 0..K 的对应的筹码?
            # 不，是持有 K..N 的筹码 (waiting to sell)。
            # 数量 = (N - start_idx) * vol ? 
            # 这是一个对冲：
            # 价格低 -> 持仓多。 价格高 -> 持仓少。
            # start_idx 小 (价格低) -> range(start_idx, N) 长 -> 持仓多。
            # start_idx 大 (价格高) -> range(start_idx, N) 短 -> 持仓少。
            # 这正是 range(start_idx, len) 的逻辑！
            
            # 所以，关键是 base_vol 的总额。
            # 如果我们想填满 start_idx 到 Top 的所有格子：
            base_vol = sum(self.sell_vols[i] for i in range(start_idx, len(self.grid_lines)))
            
            # 检查资金是否足够
            req_cash = base_vol * start_price
            if req_cash > self.initial_capital:
                # 资金不足，按比例缩减
                ratio = self.initial_capital / req_cash
                base_vol = int(base_vol * ratio)
        else:
            # 固定比例模式
            base_cash = self.initial_capital * self.base_pos_ratio
            base_vol = int(base_cash / start_price / 100) * 100
        
        positions = {}
        remaining_vol = base_vol
        
        # 向上分配底仓 (使用 index 作为 key)
        # 逻辑：将底仓分配给当前价格之上的网格，以便随价格上涨逐笔卖出
        for i in range(start_idx, len(self.grid_lines)):
            if remaining_vol <= 0:
                break
            vol_needed = self.sell_vols[i]
            if remaining_vol >= vol_needed:
                positions[i] = vol_needed
                self.grid_states[i] = True # 标记为持有
                remaining_vol -= vol_needed
            else:
                positions[i] = remaining_vol
                self.grid_states[i] = True # 标记为持有
                remaining_vol = 0
                
        # 剩余资金
        actual_cost = (base_vol - remaining_vol) * start_price
        initial_cash = self.initial_capital - actual_cost
        
        self.account = VirtualAccount(initial_cash, positions)
        self.account.total_cost = actual_cost
        
        # 记录初始建仓交易
        if actual_cost > 0:
            total_vol = base_vol - remaining_vol
            pos_val = total_vol * start_price
            
            self.account.trade_records.append(TradeRecord(
                date="初始建仓", # 或者使用具体日期
                type='BUY',
                price=start_price,
                volume=total_vol,
                amount=actual_cost,
                current_position=total_vol,
                position_value=pos_val,
                cash=initial_cash,
                total_value=initial_cash + pos_val
            ))

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty:
            return None
            
        # 1. 初始化
        first_open = df.iloc[0]['open']
        self._init_account(first_open)
        
        # 更新初始建仓日期为回测开始日期
        if self.account.trade_records:
            self.account.trade_records[0].date = str(df.iloc[0]['date'])
        
        equity_curve = []
        
        # 2. 遍历 K 线
        for idx, row in df.iterrows():
            date = row['date']
            open_p = row['open']
            high_p = row['high']
            low_p = row['low']
            close_p = row['close']
            
            # 构造路径
            path = []
            if close_p > open_p: # 阳线
                path = [(open_p, low_p), (low_p, high_p), (high_p, close_p)]
            else: # 阴线
                path = [(open_p, high_p), (high_p, low_p), (low_p, close_p)]
                
            # 模拟路径
            for p_start, p_end in path:
                if p_start == p_end:
                    continue
                    
                direction = 1 if p_end > p_start else -1
                
                # 找出涉及的网格索引范围
                p_min, p_max = min(p_start, p_end), max(p_start, p_end)
                idx_start = int(np.searchsorted(self.prices, p_min, side='left'))
                idx_end = int(np.searchsorted(self.prices, p_max, side='right'))
                
                # 根据方向遍历索引
                if direction == 1: # 向上 (可能触发卖出)
                    # 从下往上遍历
                    for i in range(idx_start, idx_end):
                        # 如果 i=0 (最底一格)，下方没有格子，无法卖出前序持仓
                        if i == 0:
                            continue
                            
                        grid_p = self.prices[i]
                        # 宽松判断: 只要 High >= grid_p 就算成交
                        if p_end >= grid_p:
                            # 核心逻辑：检查上一格(i-1)是否有持仓
                            if self.grid_states.get(i-1, False):
                                vol = self.sell_vols[i]
                                if vol > 0:
                                    # 执行卖出
                                    if self.account.sell(date, grid_p, vol, i-1):
                                        # 标记上一格为空仓
                                        self.grid_states[i-1] = False
                                        
                                        buy_price = self.prices[i-1]
                                        step_profit = grid_p - buy_price
                                        self.account.realized_profit += step_profit * vol
                                    
                else: # 向下 (可能触发买入)
                    # 从上往下遍历
                    for i in range(idx_end - 1, idx_start - 1, -1):
                        grid_p = self.prices[i]
                        # 只要穿过就买入
                        if grid_p < p_start and grid_p >= p_end:
                             # 核心逻辑：检查当前格(i)是否已持有
                             if not self.grid_states.get(i, False):
                                 vol = self.buy_vols[i]
                                 if vol > 0:
                                     if self.account.buy(date, grid_p, vol, i):
                                         # 标记当前格为持有
                                         self.grid_states[i] = True
                                 
            # 每日结算
            equity = self.account.get_equity(close_p)
            equity_curve.append({
                'date': str(date),
                'equity': equity,
                'price': close_p,
                'open': open_p,
                'high': high_p,
                'low': low_p
            })
            
        # 3. 统计结果
        final_equity = equity_curve[-1]['equity']
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100
        
        # 计算年化
        days = len(df)
        annualized_return = total_return / (days / 252) if days > 0 else 0
        
        # 破网率 (收盘价超出范围的天数)
        break_count = df[ (df['close'] > self.prices[-1]) | (df['close'] < self.prices[0]) ].shape[0]
        break_rate = break_count / days * 100
        
        # 最大回撤
        equities = [e['equity'] for e in equity_curve]
        max_eq = np.maximum.accumulate(equities)
        drawdowns = (max_eq - equities) / max_eq
        max_dd = drawdowns.max() * 100
        
        # 浮动盈亏 = 总权益 - 初始本金 - 已实现利润
        # (这种定义有点怪，通常 Float PnL = Market Value - Cost Basis)
        # 这里按 PRD: 底仓及未卖出网格的市值波动
        # 简单算: Final Equity - Initial Capital - Grid Profit
        float_pnl = final_equity - self.initial_capital - self.account.realized_profit

        # --- 计算夏普比率 ---
        # 策略日收益率序列
        equity_series = pd.Series(equities)
        daily_returns = equity_series.pct_change().dropna()
        if daily_returns.std() != 0:
            sharpe_ratio = (daily_returns.mean() * 252) / (daily_returns.std() * np.sqrt(252))
        else:
            sharpe_ratio = 0.0

        # --- 计算基准 (Buy & Hold) 指标 ---
        # 假设初始资金全部买入标的
        first_price = df.iloc[0]['close']
        last_price = df.iloc[-1]['close']
        
        benchmark_total_return = (last_price - first_price) / first_price * 100
        benchmark_annualized_return = benchmark_total_return / (days / 252) if days > 0 else 0
        
        # 基准最大回撤
        prices = df['close'].values
        max_prices = np.maximum.accumulate(prices)
        benchmark_drawdowns = (max_prices - prices) / max_prices
        benchmark_max_drawdown = benchmark_drawdowns.max() * 100
        
        # 基准夏普比率
        price_series = df['close']
        benchmark_daily_returns = price_series.pct_change().dropna()
        if benchmark_daily_returns.std() != 0:
            benchmark_sharpe_ratio = (benchmark_daily_returns.mean() * 252) / (benchmark_daily_returns.std() * np.sqrt(252))
        else:
            benchmark_sharpe_ratio = 0.0
        
        # 将基准净值加入 daily_equity (用于绘图)
        # 归一化基准曲线：使其起始值等于策略初始权益
        initial_equity = self.initial_capital
        for i, item in enumerate(equity_curve):
            item['benchmark_equity'] = (item['price'] / first_price) * initial_equity

        return BacktestResult(
            total_return=round(total_return, 2),
            annualized_return=round(annualized_return, 2),
            grid_profit=round(self.account.realized_profit, 2),
            float_pnl=round(float_pnl, 2),
            trade_count=len(self.account.trade_records),
            daily_trade_count=round(len(self.account.trade_records) / days, 2),
            win_rate=0, # 不计算
            max_drawdown=round(max_dd, 2),
            break_rate=round(break_rate, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
            trades=self.account.trade_records,
            daily_equity=equity_curve,
            benchmark_total_return=round(benchmark_total_return, 2),
            benchmark_annualized_return=round(benchmark_annualized_return, 2),
            benchmark_max_drawdown=round(benchmark_max_drawdown, 2),
            benchmark_sharpe_ratio=round(benchmark_sharpe_ratio, 2)
        )
