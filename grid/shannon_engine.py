import numpy as np
import pandas as pd
from numba import jit
from numba.typed import List
from dataclasses import dataclass
from typing import Dict, Any

@jit(nopython=True)
def _core_backtest(
    timestamps, opens, highs, lows, closes, 
    initial_capital, grid_density, sell_gap, pos_per_grid, 
    faith_ratio, grid_ratio, lower_limit, upper_limit, fee_rate, min_fee
):
    # --- 状态初始化 ---
    cash = float(initial_capital)
    free_shares = 0.0
    frozen_shares = 0.0
    
    # 交易记录
    trades_log = List()
    
    # LIFO 栈
    pos_stack_price = List()
    pos_stack_vol = List()
    
    # 参考价格
    ref_price = opens[0]
    
    # 日期追踪
    current_date = timestamps[0] // 10000
    
    # --- 1. 顶层资产配置初始化 (T=0) ---
    locked_shares = 0.0
    
    # A. 信仰底仓 (Core Holding)
    if faith_ratio > 0:
        target_faith_amt = initial_capital * faith_ratio
        faith_shares = np.floor(target_faith_amt / ref_price / 100.0) * 100.0
        
        if faith_shares > 0:
            faith_cost = ref_price * faith_shares
            faith_fee = faith_cost * fee_rate
            if cash >= (faith_cost + faith_fee):
                cash -= (faith_cost + faith_fee)
                locked_shares = faith_shares
                trades_log.append(np.array([float(timestamps[0]), 1.1, ref_price, faith_shares, faith_fee, cash, locked_shares]))

    # B. 网格底仓 (Grid Inventory)
    if grid_ratio > 0:
        target_grid_amt = initial_capital * grid_ratio
        grid_shares = np.floor(target_grid_amt / ref_price / 100.0) * 100.0
        
        if grid_shares > 0:
            grid_cost = ref_price * grid_shares
            grid_fee = grid_cost * fee_rate
            if cash >= (grid_cost + grid_fee):
                cash -= (grid_cost + grid_fee)
                
                # 切碎并入栈
                std_buy_vol = np.floor(pos_per_grid / ref_price / 100.0) * 100.0
                if std_buy_vol <= 0: std_buy_vol = 100.0
                
                # 1. 先计算总共能切多少格
                # (不做实际 push，只算 count)
                num_steps = 0
                temp_rem = grid_shares
                while temp_rem > 0:
                    vol = min(temp_rem, std_buy_vol)
                    temp_rem -= vol
                    num_steps += 1
                
                # 2. 倒序生成并压栈 (从 High 到 Low)
                # 这样最后压入的是 Low (Ref Price)，位于栈顶
                # step 范围: num_steps-1 -> 0
                
                # 我们需要重新计算每一格的 volume。
                # 注意：如果是均分或者最后余数在最后，倒序时要小心。
                # 正序时：[Std, Std, ..., Remainder] (Price Low -> High)
                # 倒序时：我们要先压 Remainder (High Price)，最后压 Std (Low Price)?
                # 不，Price 是固定的阶梯。
                # 第 k 格 (k=0...N-1) 的 Price 是 Ref * (1+g)^k
                # 第 k 格的 Volume 是 Std (除了最后一格 k=N-1 是 Remainder)
                
                # 所以我们循环 k 从 N-1 到 0
                for k in range(num_steps - 1, -1, -1):
                    virtual_cost = ref_price * ((1.0 + sell_gap) ** k)
                    
                    # 计算这一格的 volume
                    # 如果是最后一格 (k=num_steps-1)，它可能是余数
                    # 实际上：总 grid_shares = (N-1)*Std + Remainder
                    # 所以 k=N-1 时，vol = grid_shares - (N-1)*Std
                    # k < N-1 时，vol = Std
                    
                    if k == num_steps - 1:
                        # 最高价的一格，承担余数
                        # 防止精度误差，直接减
                        vol = grid_shares - (num_steps - 1) * std_buy_vol
                    else:
                        vol = std_buy_vol
                        
                    pos_stack_price.append(virtual_cost)
                    pos_stack_vol.append(vol)
                
                # 记录交易
                # 注意：此时 total_shares = locked + grid
                current_total = locked_shares + grid_shares
                trades_log.append(np.array([float(timestamps[0]), 1.2, ref_price, grid_shares, grid_fee, cash, current_total]))
                
                # 关键修复：将初始网格底仓加入冻结池，等待 T+1 解冻后变为可用
                frozen_shares += grid_shares

    # --- 2. 循环遍历 K 线 ---
    n_steps = len(timestamps)
    equity_curve = np.zeros(n_steps)
    cash_history = np.zeros(n_steps)
    
    for i in range(n_steps):
        ts = timestamps[i]
        today = ts // 10000
        
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        
        # --- T+1 结算 ---
        if today > current_date:
            free_shares += frozen_shares
            frozen_shares = 0.0
            current_date = today
            
        # [Adjusted] 移除突破上限清仓逻辑，改为仅停止买入(断电)
        # 上限之上，持仓仍可正常止盈，但不补回。

        # --- 卖出逻辑 (LIFO) ---
        while len(pos_stack_price) > 0:
            cost = pos_stack_price[-1]
            vol = pos_stack_vol[-1]
            target_sell_price = cost * (1.0 + sell_gap)
            
            if h >= target_sell_price:
                if free_shares >= vol:
                    # 撮合逻辑：如果开盘价就高过止盈价，按开盘价成交（高卖）
                    actual_sell_price = max(target_sell_price, o)
                    
                    revenue = actual_sell_price * vol
                    sell_fee = revenue * fee_rate
                    cash += (revenue - sell_fee)
                    free_shares -= vol
                    pos_stack_price.pop()
                    pos_stack_vol.pop()
                    ref_price = pos_stack_price[-1] if len(pos_stack_price) > 0 else cost
                    
                    current_total_shares = locked_shares + free_shares + frozen_shares
                    trades_log.append(np.array([float(ts), -1.0, actual_sell_price, float(vol), sell_fee, cash, current_total_shares]))
                else:
                    break
            else:
                break
        
        # --- 买入逻辑 ---
        if c > lower_limit and c < upper_limit:
            next_buy_price = ref_price * (1.0 - grid_density)
            if l <= next_buy_price:
                # 撮合逻辑：如果开盘价就低于买入价，按开盘价成交（低买）
                actual_buy_price = min(next_buy_price, o)
                
                buy_vol = np.floor(pos_per_grid / actual_buy_price / 100.0) * 100.0
                if buy_vol > 0:
                    total_pay = (actual_buy_price * buy_vol) * (1.0 + fee_rate)
                    if cash >= total_pay:
                        cash -= total_pay
                        frozen_shares += buy_vol
                        pos_stack_price.append(actual_buy_price)
                        pos_stack_vol.append(buy_vol)
                        ref_price = actual_buy_price
                        
                        current_total_shares = locked_shares + free_shares + frozen_shares
                        trades_log.append(np.array([float(ts), 1.0, actual_buy_price, float(buy_vol), total_pay - (actual_buy_price * buy_vol), cash, current_total_shares]))
        
        # --- 记录净值 ---
        total_shares = locked_shares + free_shares + frozen_shares
        equity = cash + total_shares * c
        equity_curve[i] = equity
        cash_history[i] = cash

    return equity_curve, trades_log, cash_history

class ShannonEngine:
    def __init__(self, df_min: pd.DataFrame):
        self.df = df_min.copy()
        if 'timestamp' not in self.df.columns:
            self.df['timestamp'] = self.df['date']
        
        if self.df['timestamp'].dtype == 'object':
            self.df['ts_int'] = self.df['timestamp'].astype(str).str.replace(r'[-: ]', '', regex=True).str[:12].astype('int64')
        else:
            self.df['ts_int'] = self.df['timestamp'].astype('int64')

        self.timestamps = self.df['ts_int'].values
        self.opens = self.df['open'].values.astype('float64')
        self.highs = self.df['high'].values.astype('float64')
        self.lows = self.df['low'].values.astype('float64')
        self.closes = self.df['close'].values.astype('float64')

    @classmethod
    def from_simulated_stream(cls, price_stream, dates_int):
        """
        从模拟的分钟流创建引擎
        price_stream: numpy array [N_days * 240]
        dates_int: numpy array [N_days] (YYYYMMDD)
        """
        n_days = len(dates_int)
        n_min = 240
        total_len = n_days * n_min
        
        # 构造伪 timestamps (用于 T+1 判定)
        # 每天 240 分钟，格式: YYYYMMDD0000 -> YYYYMMDD0239
        timestamps = np.zeros(total_len, dtype='int64')
        for i in range(n_days):
            base_ts = dates_int[i] * 10000
            for m in range(n_min):
                timestamps[i * n_min + m] = base_ts + m
                
        # 在模拟流中，OHLC 都是同一个 Price (因为是 Tick 流)
        # 或者我们可以直接修改 _core_backtest 接受 raw stream
        # 为了兼容性，我们将 stream 视为 OHLC
        instance = cls.__new__(cls)
        instance.timestamps = timestamps
        instance.opens = price_stream
        instance.highs = price_stream
        instance.lows = price_stream
        instance.closes = price_stream
        # 记录用于降采样的 meta
        instance.sim_dates = dates_int
        return instance

    def run(self, initial_capital=100000, grid_density=0.015, sell_gap=0.02, 
            pos_per_grid=5000, faith_ratio=0.2, grid_ratio=0.3, lower_limit=0.0, upper_limit=999.0):
        
        fee_rate = 0.00006
        min_fee = 0.0
        
        equity_curve, trades_raw, cash_history = _core_backtest(
            self.timestamps, self.opens, self.highs, self.lows, self.closes,
            initial_capital, grid_density, sell_gap, pos_per_grid,
            faith_ratio, grid_ratio, lower_limit, upper_limit, fee_rate, min_fee
        )
        
        trades = []
        for t in trades_raw:
            price = t[2]
            cash = t[5]
            total_shares = t[6]
            type_val = t[1]
            
            # 转换方向标签
            if type_val == 1.1: type_label = 'BUY(信仰底仓)'
            elif type_val == 1.2: type_label = 'BUY(网格底仓)'
            elif type_val > 0: type_label = 'BUY'
            else: type_label = 'SELL'
            
            trades.append({
                'timestamp': str(int(t[0])),
                'type': type_label,
                'price': price,
                'volume': int(t[3]),
                'fee': t[4],
                'cash': cash,
                'total_shares': int(total_shares),
                'total_equity': cash + total_shares * price
            })
            
        return {
            'equity_curve': equity_curve,
            'cash_history': cash_history,
            'trades': trades,
            'final_equity': equity_curve[-1] if len(equity_curve) > 0 else initial_capital
        }
