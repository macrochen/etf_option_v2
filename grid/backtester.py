import pandas as pd
import numpy as np
from typing import List, Dict
from .models import GridLine, BacktestResult, TradeRecord

class VirtualAccount:
    def __init__(self, initial_cash: float, initial_positions: Dict[int, int] = None, locked_position: int = 0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        
        # T+1 库存管理
        # positions 存储的是 "总可用持仓" (Available) - 用于网格交易
        self.positions = initial_positions or {} 
        self.frozen_positions = {} 
        
        # 锁定底仓 (长期持有，不参与网格卖出)
        self.locked_position = locked_position
        
        self.total_cost = 0.0 
        self.realized_profit = 0.0 
        self.trade_records = []
        
    def settle(self):
        """盘前结算：将冻结持仓转为可用持仓"""
        for idx, vol in self.frozen_positions.items():
            current = self.positions.get(idx, 0)
            self.positions[idx] = current + vol
        self.frozen_positions.clear()

    def buy(self, date, price, volume, grid_index):
        cost = price * volume
        if self.cash < cost:
            return False 
            
        self.cash -= cost
        self.total_cost += cost
        
        # 增加冻结持仓 (T+1)
        current_frozen = self.frozen_positions.get(grid_index, 0)
        self.frozen_positions[grid_index] = current_frozen + volume
        
        # 记录快照 (持仓量 = 可用 + 冻结 + 锁定)
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
        # 检查可用持仓 (不包含冻结，也不包含锁定底仓)
        current_vol = self.positions.get(grid_index, 0)
        if current_vol < volume:
            return False 
            
        revenue = price * volume
        self.cash += revenue
        self.total_cost -= revenue 
        
        # 扣减可用持仓
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
        
    def get_total_volume(self):
        """获取总持仓 (可用 + 冻结 + 锁定)"""
        avail = sum(self.positions.values())
        frozen = sum(self.frozen_positions.values())
        return avail + frozen + self.locked_position
        
    def get_equity(self, current_price):
        market_value = self.get_total_volume() * current_price
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
        
        # 网格状态机: List of dicts [{'buy': bool, 'sell': bool}]
        # buy: 当前网格是否允许买入 (Empty)
        # sell: 当前网格是否允许触发卖出 (即下方网格 i-1 是否有持仓)
        self.grid_states = []
        self.missed_trades = 0
        
    def _init_account(self, start_price):
        """初始化账户，建立底仓"""
        
        # 1. 锁定底仓计算 (Passive Hold)
        # 如果用户指定了底仓比例，这部分资金用于买入"永久持有"的底仓
        locked_vol = 0
        locked_cost = 0
        grid_capital = self.initial_capital # 剩余用于网格交易的资金
        
        if self.base_pos_ratio is not None and self.base_pos_ratio > 0:
            locked_capital = self.initial_capital * self.base_pos_ratio
            locked_vol = int(locked_capital / start_price / 100) * 100
            locked_cost = locked_vol * start_price
            grid_capital -= locked_cost
            
        # 2. 网格初始持仓计算 (Active Grid Inventory)
        # 根据当前价格在网格中的位置，自动计算需要持有的"待卖出"筹码
        # 逻辑：价格越高，需要的初始持仓越少(已卖出)；价格越低，需要的持仓越多(已买入)
        # 假设：价格在 start_idx，则下方 0...start_idx-1 的格子应该是"已买入"状态
        # 因此我们需要持有这些格子对应的 sell_vols，以便价格上涨时卖出
        
        start_idx = int(np.searchsorted(self.prices, start_price))
        
        # 计算网格部分需要的初始持仓
        # 逻辑：填充 start_idx 及其上方的格子? 不，参考之前的逻辑
        # 我们需要持有 positions[i] 来响应 i+1 的卖出。
        # 如果价格在 P_k。
        # 价格涨到 P_k+1 -> 卖出 positions[k]。
        # 价格涨到 P_k+2 -> 卖出 positions[k+1]。
        # 所以我们需要持有 positions[k], positions[k+1]... 
        # 即从 start_idx 开始向上的格子。
        
        active_vol_needed = sum(self.sell_vols[i] for i in range(start_idx, len(self.grid_lines)))
        active_cost = active_vol_needed * start_price
        
        # 检查剩余资金是否足够支付网格初始持仓
        # 如果不够，按比例缩减 (优先保证网格完整性 vs 资金限制?)
        # 这里按比例缩减 active_vol
        positions = {}
        remaining_active_vol = active_vol_needed
        
        if active_cost > grid_capital:
            ratio = grid_capital / active_cost if active_cost > 0 else 0
            remaining_active_vol = int(remaining_active_vol * ratio)
            
        total_initial_cost = locked_cost + (remaining_active_vol * start_price)
        initial_cash = self.initial_capital - total_initial_cost
        
        # 初始化状态机
        self.grid_states = [{'buy': True, 'sell': False} for _ in range(len(self.grid_lines) + 1)] 
        
        # 分配网格持仓并更新状态
        for i in range(start_idx, len(self.grid_lines)):
            if remaining_active_vol <= 0:
                break
            vol_needed = self.sell_vols[i]
            
            # 分配逻辑
            alloc_vol = min(remaining_active_vol, vol_needed)
            
            if alloc_vol >= vol_needed:
                positions[i] = vol_needed
                self.grid_states[i]['buy'] = False # 已满
                self.grid_states[i+1]['sell'] = True # 挂卖
            else:
                # 资金不足只买了部分，也算持有
                positions[i] = alloc_vol
                self.grid_states[i]['buy'] = False
                self.grid_states[i+1]['sell'] = True
                
            remaining_active_vol -= alloc_vol
            
        # 创建账户
        # 修正 T+1 逻辑：初始网格持仓视为"当日买入"，应进入冻结状态，Day 1 不可卖出
        self.account = VirtualAccount(initial_cash, {}, locked_position=locked_vol) # positions(Available) 为空
        self.account.frozen_positions = positions # 将计算出的网格持仓放入冻结池
        self.account.total_cost = total_initial_cost
        
        # 记录初始交易 - 拆分为两笔以便用户区分
        
        # 1. 锁定底仓记录
        current_pos_acc = 0
        current_val_acc = 0
        
        if locked_vol > 0:
            current_pos_acc += locked_vol
            val = locked_vol * start_price
            current_val_acc += val
            
            self.account.trade_records.append(TradeRecord(
                date="初始建仓(底仓)", 
                type='BUY', 
                price=start_price, 
                volume=locked_vol, 
                amount=val,
                current_position=current_pos_acc, 
                position_value=current_val_acc, 
                cash=self.initial_capital - val, 
                total_value=self.initial_capital 
            ))
            
        # 2. 网格活跃持仓记录
        active_vol = sum(positions.values())
        if active_vol > 0:
            current_pos_acc += active_vol
            val = active_vol * start_price
            current_val_acc += val
            
            self.account.trade_records.append(TradeRecord(
                date="初始建仓(网格)", 
                type='BUY', 
                price=start_price, 
                volume=active_vol, 
                amount=val,
                current_position=current_pos_acc, 
                position_value=current_val_acc, 
                cash=initial_cash, 
                total_value=initial_cash + current_val_acc
            ))

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty:
            return None
            
        first_open = df.iloc[0]['open']
        self._init_account(first_open)
        
        # 更新初始建仓日期为回测开始日期
        if self.account.trade_records:
            start_date_str = str(df.iloc[0]['date'])
            for rec in self.account.trade_records:
                if "初始建仓" in rec.date:
                    suffix = rec.date.replace("初始建仓", "")
                    rec.date = f"{start_date_str}{suffix}"
        
        equity_curve = []
        is_first_day = True
        
        for idx, row in df.iterrows():
            date = row['date']
            high_p = row['high']
            low_p = row['low']
            close_p = row['close']
            open_p = row['open']
            
            # Step 1: 盘前结算 (T+1 解冻)
            # 第一天跳过结算，确保初始冻结持仓不会立刻解冻
            if not is_first_day:
                self.account.settle()
            is_first_day = False
            
            # Step 2: 卖出判定 (High Priority)
            sell_candidates = [i for i, state in enumerate(self.grid_states) 
                             if state['sell'] and i < len(self.prices) and high_p >= self.prices[i]]
            
            sell_candidates.sort()
            
            for i in sell_candidates:
                grid_p = self.prices[i]
                vol = self.sell_vols[i]
                
                if vol > 0:
                    if self.account.sell(date, grid_p, vol, i-1):
                        self.grid_states[i]['sell'] = False
                        self.grid_states[i-1]['buy'] = True
                        
                        buy_price = self.prices[i-1]
                        step_profit = grid_p - buy_price
                        self.account.realized_profit += step_profit * vol
                    else:
                        self.missed_trades += 1
            
            # Step 3: 买入判定 (Low Priority)
            buy_candidates = [i for i, state in enumerate(self.grid_states) 
                            if state['buy'] and i < len(self.prices) and low_p <= self.prices[i]]
            
            buy_candidates.sort(reverse=True)
            
            for i in buy_candidates:
                grid_p = self.prices[i]
                vol = self.buy_vols[i]
                
                if vol > 0:
                    if self.account.buy(date, grid_p, vol, i):
                        self.grid_states[i]['buy'] = False
                        self.grid_states[i+1]['sell'] = True
                    else:
                        self.missed_trades += 1
            
            # Step 4: 收盘状态更新
            equity = self.account.get_equity(close_p)
            equity_curve.append({
                'date': str(date),
                'equity': equity,
                'cash': self.account.cash, # 记录现金以便计算利用率
                'price': close_p,
                'open': open_p,
                'high': high_p,
                'low': low_p
            })
            
        # 统计结果
        final_equity = equity_curve[-1]['equity']
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100
        days = len(df)
        annualized_return = total_return / (days / 252) if days > 0 else 0
        
        # 交易统计
        all_trades = self.account.trade_records
        buy_count = sum(1 for t in all_trades if t.type == 'BUY')
        sell_count = sum(1 for t in all_trades if t.type == 'SELL')
        trade_count = len(all_trades)
        
        # 资金利用率 = 平均持仓市值 / 平均总资产
        # 持仓市值 = Equity - Cash
        avg_pos_value = np.mean([e['equity'] - e['cash'] for e in equity_curve])
        avg_equity = np.mean([e['equity'] for e in equity_curve])
        capital_utilization = (avg_pos_value / avg_equity * 100) if avg_equity > 0 else 0.0
        
        break_count = df[ (df['close'] > self.prices[-1]) | (df['close'] < self.prices[0]) ].shape[0]
        break_rate = break_count / days * 100
        
        equities = [e['equity'] for e in equity_curve]
        max_eq = np.maximum.accumulate(equities)
        drawdowns = (max_eq - equities) / max_eq
        max_dd = drawdowns.max() * 100
        
        float_pnl = final_equity - self.initial_capital - self.account.realized_profit

        equity_series = pd.Series(equities)
        daily_returns = equity_series.pct_change().dropna()
        sharpe_ratio = (daily_returns.mean() * 252) / (daily_returns.std() * np.sqrt(252)) if daily_returns.std() != 0 else 0.0

        first_price = df.iloc[0]['close']
        last_price = df.iloc[-1]['close']
        benchmark_total_return = (last_price - first_price) / first_price * 100
        benchmark_annualized_return = benchmark_total_return / (days / 252) if days > 0 else 0
        
        prices = df['close'].values
        max_prices = np.maximum.accumulate(prices)
        benchmark_drawdowns = (max_prices - prices) / max_prices
        benchmark_max_drawdown = benchmark_drawdowns.max() * 100
        
        price_series = df['close']
        benchmark_daily_returns = price_series.pct_change().dropna()
        benchmark_sharpe_ratio = (benchmark_daily_returns.mean() * 252) / (benchmark_daily_returns.std() * np.sqrt(252)) if benchmark_daily_returns.std() != 0 else 0.0
        
        initial_equity = self.initial_capital
        for i, item in enumerate(equity_curve):
            item['benchmark_equity'] = (item['price'] / first_price) * initial_equity

        return BacktestResult(
            total_return=round(total_return, 2),
            annualized_return=round(annualized_return, 2),
            grid_profit=round(self.account.realized_profit, 2),
            float_pnl=round(float_pnl, 2),
            trade_count=trade_count,
            buy_count=buy_count,
            sell_count=sell_count,
            daily_trade_count=round(trade_count / days, 2),
            capital_utilization=round(capital_utilization, 2),
            win_rate=0,
            max_drawdown=round(max_dd, 2),
            break_rate=round(break_rate, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
            missed_trades=self.missed_trades,
            trades=self.account.trade_records,
            daily_equity=equity_curve,
            benchmark_total_return=round(benchmark_total_return, 2),
            benchmark_annualized_return=round(benchmark_annualized_return, 2),
            benchmark_max_drawdown=round(benchmark_max_drawdown, 2),
            benchmark_sharpe_ratio=round(benchmark_sharpe_ratio, 2)
        )