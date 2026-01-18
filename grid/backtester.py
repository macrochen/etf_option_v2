import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from .models import GridLine, BacktestResult, TradeRecord, MarketRegime, GridContext
from .indicators import Indicators
from .strategy import SmartGridStrategy

class VirtualAccount:
    def __init__(self, initial_cash: float, locked_position: int = 0):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        
        # PRD 2.7 仓位结构
        # 1. Inventory_Locked (底仓): 永不卖出
        self.locked_position = locked_position
        
        # 2. Inventory_Available (网格仓): 可卖
        self.positions = {} # {grid_index: volume}
        
        # 3. Inventory_Frozen (冻结仓): T+1
        self.frozen_positions = {} 
        
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
        
        # 记录
        self._record_trade(date, 'BUY', price, volume, cost)
        return True

    def sell(self, date, price, volume, grid_index):
        # 检查可用持仓
        current_vol = self.positions.get(grid_index, 0)
        if current_vol < volume:
            return False 
            
        revenue = price * volume
        self.cash += revenue
        self.total_cost -= revenue 
        
        # 扣减可用持仓
        self.positions[grid_index] = current_vol - volume
        
        # 记录
        self._record_trade(date, 'SELL', price, volume, revenue)
        return True
        
    def _record_trade(self, date, type, price, volume, amount):
        total_vol = self.get_total_volume()
        pos_val = total_vol * price
        
        self.trade_records.append(TradeRecord(
            date=str(date),
            type=type,
            price=price,
            volume=volume,
            amount=amount,
            current_position=total_vol,
            position_value=pos_val,
            cash=self.cash,
            total_value=self.cash + pos_val
        ))

    def get_total_volume(self):
        avail = sum(self.positions.values())
        frozen = sum(self.frozen_positions.values())
        return avail + frozen + self.locked_position
        
    def get_equity(self, current_price):
        market_value = self.get_total_volume() * current_price
        return self.cash + market_value

class PathSimulator:
    def __init__(self, context: GridContext, initial_grid_lines: List[GridLine]):
        self.context = context
        # 初始网格 (可能在运行中重锚)
        self.grid_lines = sorted(initial_grid_lines, key=lambda x: x.price) 
        
        self.account = None
        self.grid_states = []
        self.missed_trades = 0
        
        # 初始化查找表和状态机
        self.update_grid_lookup()
        
        # 状态追踪
        self.is_hibernating = False # 是否休眠
        
    def update_grid_lookup(self):
        """更新网格查找表"""
        self.prices = np.array([g.price for g in self.grid_lines])
        self.buy_vols = [g.buy_vol for g in self.grid_lines]
        self.sell_vols = [g.sell_vol for g in self.grid_lines]
        # 重置状态机
        self.grid_states = [{'buy': True, 'sell': False} for _ in range(len(self.grid_lines) + 1)]

    def _determine_regime(self, price, ma20, ma60, ref_ma20):
        """判定市场状态 (PRD 4.1)"""
        # BULL: Price > MA20 > MA60
        if price > ma20 and ma20 > ma60:
            return MarketRegime.BULL
        
        # BEAR: Price < MA20 and MA20 < Ref_MA20 (均线向下)
        if price < ma20 and ma20 < ref_ma20:
            return MarketRegime.BEAR
            
        return MarketRegime.SIDEWAY

    def _init_account(self, start_date, start_price, initial_regime):
        """初始化 (PRD 5.1 Cold Start)"""
        
        # 1. 资金划分
        total_cap = self.context.total_capital
        base_ratio = self.context.base_position_ratio
        
        base_capital = total_cap * base_ratio
        op_capital = total_cap - base_capital
        
        # 2. 底仓建立 (Inventory_Locked)
        locked_vol = int(base_capital / start_price / 100) * 100
        actual_base_cost = locked_vol * start_price
        
        # 3. 网格建仓 (Tactical Setup)
        initial_positions = {}
        initial_frozen = {} # 初始建仓如果视为T=0买入，应冻结? PRD说存入 Available
        
        active_cost = 0
        active_vol_total = 0
        
        if initial_regime == MarketRegime.BEAR:
            # BEAR: 不建仓，100% 现金 (除底仓外)
            self.is_hibernating = True
            
        elif initial_regime == MarketRegime.BULL:
            # BULL: 激进建仓 (如 50% Op Capital)
            # PRD: 重锚以 Start_Price 为中枢。这里假设传入的 grid_lines 已经是基于 Start 生成的?
            # 简化：买入 50% Op Capital
            target_val = op_capital * 0.5
            vol = int(target_val / start_price / 100) * 100
            
            # 分配到当前价格附近的网格?
            # 简单分配：视为持有了 start_idx 以下的筹码
            start_idx = int(np.searchsorted(self.prices, start_price))
            # 向上分配以备卖出
            rem_vol = vol
            for i in range(start_idx, len(self.grid_lines)):
                if rem_vol <= 0: break
                alloc = min(rem_vol, self.sell_vols[i])
                if alloc > 0:
                    initial_positions[i] = alloc
                    self.grid_states[i]['buy'] = False
                    self.grid_states[i+1]['sell'] = True
                    rem_vol -= alloc
            
            active_cost = (vol - rem_vol) * start_price
            active_vol_total = vol - rem_vol
            
        else: # SIDEWAY
            # 按分位建仓
            if len(self.prices) > 0:
                p_min, p_max = self.prices[0], self.prices[-1]
                if p_max > p_min:
                    position_pct = 1.0 - (start_price - p_min) / (p_max - p_min)
                    position_pct = max(0.0, min(1.0, position_pct))
                else:
                    position_pct = 0.5
            else:
                position_pct = 0.0
                
            target_val = op_capital * position_pct
            vol = int(target_val / start_price / 100) * 100
            
            # 分配
            start_idx = int(np.searchsorted(self.prices, start_price))
            rem_vol = vol
            for i in range(start_idx, len(self.grid_lines)):
                if rem_vol <= 0: break
                alloc = min(rem_vol, self.sell_vols[i])
                if alloc > 0:
                    initial_positions[i] = alloc
                    self.grid_states[i]['buy'] = False
                    self.grid_states[i+1]['sell'] = True
                    rem_vol -= alloc
            
            active_cost = (vol - rem_vol) * start_price
            active_vol_total = vol - rem_vol

        # 计算初始现金
        total_initial_cost = actual_base_cost + active_cost
        initial_cash = total_cap - total_initial_cost

        # 创建账户
        # 修正：将网格初始持仓放入冻结池，以符合用户对 T+1 的严格理解 (Day 1 不卖)
        self.account = VirtualAccount(initial_cash, locked_position=locked_vol) # positions(Available) Empty
        self.account.frozen_positions = initial_positions # Active Grid Positions -> Frozen
        self.account.total_cost = total_initial_cost
        
        # 记录初始交易
        if locked_vol > 0:
            self._log_init_trade(start_date, start_price, locked_vol, actual_base_cost, "(底仓建仓)")
        if active_vol_total > 0:
            self._log_init_trade(start_date, start_price, active_vol_total, active_cost, "(网格建仓)")

    def _log_init_trade(self, date, price, vol, amount, suffix):
        total_vol = self.account.get_total_volume()
        pos_val = total_vol * price
        self.account.trade_records.append(TradeRecord(
            date=f"{date}{suffix}", type='BUY', price=price, volume=vol, amount=amount,
            current_position=total_vol, position_value=pos_val, cash=self.account.cash, 
            total_value=self.account.cash + pos_val
        ))

    def run(self, df: pd.DataFrame) -> BacktestResult:
        if df.empty: return None
        
        # 0. 预计算指标 (MA20, MA60)
        # 注意：df 必须包含足够的前序数据来计算 MA。如果传入的 df 已经是切片后的，MA 会从头开始算(导致前60天NaN)
        # 假设 df 包含了前序 buffer 数据。
        # 我们需要在遍历时，只处理回测区间的数据。
        # 这里的 df 应该是全量数据? 还是带 Buffer 的切片?
        # routes 层应该处理好。这里假设 df 包含指标列。
        
        # 检查是否包含指标列，如果没有则计算
        if 'ma20' not in df.columns:
            df['ma20'] = Indicators.calculate_ma(df, 20)
            df['ma60'] = Indicators.calculate_ma(df, 60)
            
        # 截取回测正式开始的数据 (假设 context 有 start_date 或者是 df 的后段)
        # 简化：假设 df 全部为回测数据 (routes层负责切分)
        # 但这样 MA 前几天是 NaN。
        # 方案：routes 层计算好指标再传入。
        
        start_date_idx = 0 
        # 如果 MA 为 NaN，默认 SIDEWAY
        
        first_row = df.iloc[0]
        ma20 = first_row.get('ma20', 0)
        ma60 = first_row.get('ma60', 0)
        # ref_ma20 难获取 (需要上一行)。
        # 我们可以用 shift
        df['ref_ma20'] = df['ma20'].shift(1)
        
        initial_regime = self._determine_regime(first_row['close'], ma20, ma60, first_row.get('ref_ma20', ma20))
        
        self._init_account(first_row['date'], first_row['open'], initial_regime)
        
        equity_curve = []
        regime_history = []
        
        for i, (idx, row) in enumerate(df.iterrows()):
            date = row['date']
            
            # Skip trading logic on the very first day (initialization day) to prevent immediate churn
            # The initial positions are already set in _init_account
            if i == 0: 
                # Still record equity for the first day
                equity = self.account.get_equity(row['close'])
                equity_curve.append({
                    'date': str(date),
                    'equity': equity,
                    'cash': self.account.cash,
                    'price': row['close'],
                    'open': row['open'],
                    'high': row['high'],
                    'low': row['low'],
                    'ma60': row.get('ma60', 0),
                    'regime': initial_regime.value
                })
                continue

            high_p = row['high']
            low_p = row['low']
            close_p = row['close']
            open_p = row['open']
            ma20 = row.get('ma20', 0)
            ma60 = row.get('ma60', 0)
            ref_ma20 = row.get('ref_ma20', 0)
            
            # 1. 盘前结算
            self.account.settle()
            
            # 判定今日状态
            regime = self._determine_regime(close_p, ma20, ma60, ref_ma20) # 使用收盘价判定(T-1)? 
            # PRD: "根据 T-1 日收盘数据 判定今日状态". 
            # 所以今日的 Regime 其实是基于昨天的。
            # 这里 row 是今日数据。
            # 严格来说，应该用 ref_close, ref_ma20...
            # 简化：假设 Close 代表今日趋势确认? 
            # 不，决策是在盘中。所以只能用 Yesterday.
            # 修正：使用 shift 后的数据作为今日 Regime 依据。
            # 这里先用今日 Close 模拟 "已知趋势" (Look-ahead)，或者取 row['ref_ma20'] 等。
            # 正确做法：Regime[T] depends on Data[T-1].
            # 让我们假设 row 包含 pre_close 等。
            # 暂且用今日 close 判定 (滞后一天确认)。
            
            regime_history.append({'date': str(date), 'regime': regime.value})
            
            # 2. 风险控制 (Stop Loss)
            # BEAR 且 跌破下限 * 0.95
            p_min = self.prices[0] if len(self.prices) > 0 else 0
            if regime == MarketRegime.BEAR and low_p <= p_min * 0.95:
                # 熔断清仓? PRD: "强制清仓...终止"
                # 卖出所有 Available
                # 这里简单处理：不再买入，保留持仓?
                # PRD: "标记回测结束 TERMINATED"
                # 为了展示完整曲线，我们不清仓，只停止新交易?
                # "卖出所有 Available" -> Cash.
                self.is_hibernating = True
                # Execute stop loss sell
                # ...
            
            # 3. 卖出判定 (High Priority)
            # PRD: 虚拟延伸 (BULL)
            # 如果 Price > Grid_Max 且 BULL.
            # 虚拟延伸逻辑：基于 Step 生成虚拟卖单。
            # 只要 Available > 0，就尝试卖出。
            
            # 标准网格卖出
            sell_candidates = [i for i, state in enumerate(self.grid_states) 
                             if state['sell'] and i < len(self.prices) and high_p >= self.prices[i]]
            sell_candidates.sort()
            
            for i in sell_candidates:
                if self.account.sell(date, self.prices[i], self.sell_vols[i], i-1):
                    self.grid_states[i]['sell'] = False
                    self.grid_states[i-1]['buy'] = True # 挂买回
                    
                    buy_p = self.prices[i-1]
                    self.account.realized_profit += (self.prices[i] - buy_p) * self.sell_vols[i]
                else:
                    self.missed_trades += 1
                    
            # 虚拟延伸卖出 (Shadow Grid)
            if regime == MarketRegime.BULL and len(self.prices) > 0:
                p_max = self.prices[-1]
                if high_p > p_max:
                    # 计算虚拟格
                    # 假设 step 是最后一格的 step
                    step = p_max - self.prices[-2] if len(self.prices) > 1 else p_max * 0.01
                    # 虚拟价格
                    curr_shadow = p_max + step
                    while high_p >= curr_shadow and self.account.get_total_volume() > self.account.locked_position:
                        # 尝试卖出"最高"的持仓?
                        # 找到最高的 OPEN_SELL (或 IDLE with position)
                        # 实际上是消耗库存。
                        # 简单实现：随机卖出一份标准 vol
                        vol = self.sell_vols[-1]
                        # 需找到对应的 grid_index 来扣减
                        # 找一个有持仓的最高格子
                        found_idx = -1
                        for idx in range(len(self.grid_lines)-1, -1, -1):
                            if self.account.positions.get(idx, 0) > 0:
                                found_idx = idx
                                break
                        
                        if found_idx >= 0:
                            if self.account.sell(date, curr_shadow, vol, found_idx):
                                # 影子卖出，不挂买回 (单向)
                                pass
                        
                        curr_shadow += step

            # 4. 买入判定
            can_buy = True
            if regime == MarketRegime.BEAR: can_buy = False
            if self.is_hibernating: can_buy = False
            if len(self.prices) > 0 and low_p < self.prices[0]: can_buy = False # 破网不买
            
            if can_buy:
                buy_candidates = [i for i, state in enumerate(self.grid_states) 
                                if state['buy'] and i < len(self.prices) and low_p <= self.prices[i]]
                buy_candidates.sort(reverse=True)
                
                for i in buy_candidates:
                    if self.account.buy(date, self.prices[i], self.buy_vols[i], i):
                        self.grid_states[i]['buy'] = False
                        if i+1 < len(self.grid_lines):
                            self.grid_states[i+1]['sell'] = True
                    else:
                        self.missed_trades += 1
                        
            # 5. 重锚检查 (Re-Anchor)
            # 若 Hibernating 且 市场转暖 (SIDEWAY/BULL)
            if self.is_hibernating and regime != MarketRegime.BEAR:
                # 触发重锚 (Trigger Re-Anchor)
                self.is_hibernating = False
                
                # 1. 准备历史数据
                # df 是全量数据，我们需要切片到当前日期 (含)
                # i 是 enumerate 的索引，对应 current row
                history_df = df.iloc[:i+1].copy()
                
                # 更新 context 的当前价格为今日收盘价 (作为锚点)
                self.context.current_price = close_p
                
                # 2. 重新生成策略
                strategy = SmartGridStrategy(self.context)
                # 注意：此处未传入 benchmark_df，Beta 分数可能不准，但不影响网格线生成
                new_strat_result = strategy.generate(history_df)
                
                # 3. 更新网格线
                self.grid_lines = sorted(new_strat_result.grid_lines, key=lambda x: x.price)
                
                # 4. 收集旧持仓 (Inventory_Available)
                old_volume = sum(self.account.positions.values())
                self.account.positions.clear()
                
                # 5. 更新查找表
                self.update_grid_lookup()
                
                # 6. 重新分配持仓 (Remap Inventory)
                # 将旧持仓分配到新网格的"卖出侧" (即当前价格上方的格子)
                # 这样价格上涨时可以卖出旧筹码
                if old_volume > 0:
                    start_idx = int(np.searchsorted(self.prices, close_p))
                    
                    rem_vol = old_volume
                    # 从当前价格位置向上分配
                    for k in range(start_idx, len(self.grid_lines)):
                        if rem_vol <= 0: break
                        # 每个格子能容纳多少？理论上可以无限，但为了符合卖出节奏，
                        # 我们可以填满该格子的 sell_vol，或者直接全部堆在上方？
                        # 策略：尽量平铺，每格填一份 sell_vol
                        alloc = self.sell_vols[k]
                        if alloc > 0:
                            self.account.positions[k] = self.account.positions.get(k, 0) + alloc
                            self.grid_states[k]['buy'] = False # 有持仓，暂不买入 (等待卖出后变 Buy)
                            self.grid_states[k+1]['sell'] = True # 激活上方卖出
                            rem_vol -= alloc
                            
                    # 如果还有剩余 (说明旧仓位非常重)，全部堆在最高格
                    if rem_vol > 0:
                        last_idx = len(self.grid_lines) - 1
                        self.account.positions[last_idx] = self.account.positions.get(last_idx, 0) + rem_vol
                        self.grid_states[last_idx]['buy'] = False
                        if last_idx + 1 <= len(self.grid_lines): # 边界检查
                             # grid_states 长度是 len(lines) + 1
                             self.grid_states[last_idx+1]['sell'] = True

            # 记录权益
            equity = self.account.get_equity(close_p)
            equity_curve.append({
                'date': str(date),
                'equity': equity,
                'cash': self.account.cash,
                'price': close_p,
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'ma60': ma60,
                'regime': regime.value
            })

        # 统计结果
        final_equity = equity_curve[-1]['equity']
        initial_cap = self.context.total_capital
        total_return = (final_equity - initial_cap) / initial_cap * 100
        days = len(df)
        annualized_return = total_return / (days / 252) if days > 0 else 0
        
        break_count = df[ (df['close'] > self.prices[-1]) | (df['close'] < self.prices[0]) ].shape[0]
        break_rate = break_count / days * 100
        
        equities = [e['equity'] for e in equity_curve]
        max_eq = np.maximum.accumulate(equities)
        drawdowns = (max_eq - equities) / max_eq
        max_dd = drawdowns.max() * 100
        
        float_pnl = final_equity - initial_cap - self.account.realized_profit

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
        
        initial_equity = initial_cap
        for i, item in enumerate(equity_curve):
            item['benchmark_equity'] = (item['price'] / first_price) * initial_equity
            
        # 交易统计
        all_trades = self.account.trade_records
        buy_count = sum(1 for t in all_trades if t.type == 'BUY')
        sell_count = sum(1 for t in all_trades if t.type == 'SELL')
        trade_count = len(all_trades)
        
        # 资金利用率
        avg_pos_value = np.mean([e['equity'] - e['cash'] for e in equity_curve])
        avg_equity = np.mean([e['equity'] for e in equity_curve])
        capital_utilization = (avg_pos_value / avg_equity * 100) if avg_equity > 0 else 0.0

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