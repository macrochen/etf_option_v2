from numba import jit
from numba.typed import List
import numpy as np
import time

# 模拟数据: 10万条分钟线 (约1年)
# open, high, low, close
prices = np.random.normal(3.0, 0.1, (100000, 4))
# 构造 High/Low
for i in range(100000):
    base = prices[i, 0]
    prices[i, 1] = base + 0.01 # High
    prices[i, 2] = base - 0.01 # Low
    prices[i, 3] = base        # Close

@jit(nopython=True)
def core_backtest(price_data, grid_density, sell_gap):
    # price_data: [N, 4] (Open, High, Low, Close)
    
    cash = 100000.0
    initial_cash = 100000.0
    
    # 持仓列表: List of [cost_price, volume]
    # Numba typed list
    positions_price = List()
    positions_vol = List()
    
    trade_count = 0
    
    # 简单的网格逻辑
    last_buy_price = price_data[0, 0]
    
    for i in range(len(price_data)):
        o, h, l, c = price_data[i]
        
        # 卖出判定 (LIFO)
        # 从后往前遍历
        # 注意：在循环中删除列表元素比较棘手，通常倒序遍历
        n_pos = len(positions_price)
        if n_pos > 0:
            # 只检查最后一个 (LIFO - 严格)
            # 或者检查所有？"优先卖出最近买入的"。如果是检查所有，那就不是严格栈，而是通过策略选择。
            # PRD: "优先卖出最近买入的那一笔"。通常意味着如果最后一笔能卖，就卖它。
            # 如果最后一笔不能卖，倒数第二笔能卖吗？
            # 严格 LIFO 网格通常指：这一笔买入对应的卖单是独立的。
            # 只要满足 (High >= Cost * (1+Gap)) 就可以卖。
            # "优先"意味着如果同时满足多个，先卖最近的。
            # 所以我们可以倒序遍历，遇到第一个能卖的就卖出并 break (假设一分钟只成交一单)
            # 或者一分钟能成交多单？实盘通常挂单都会成交。
            # 这里简化：一分钟内处理所有满足条件的卖单，从后往前。
            
            # 倒序索引
            for j in range(n_pos - 1, -1, -1):
                cost = positions_price[j]
                target_sell = cost * (1 + sell_gap)
                
                if h >= target_sell:
                    # 成交卖出
                    vol = positions_vol[j]
                    revenue = target_sell * vol
                    cash += revenue
                    
                    # 移除该持仓
                    positions_price.pop(j)
                    positions_vol.pop(j)
                    
                    trade_count += 1
        
        # 买入判定
        # 简单逻辑：比上次买入价跌 Grid_Density
        # 这里只是性能测试，逻辑不完全
        target_buy = last_buy_price * (1 - grid_density)
        if l <= target_buy:
            if cash >= target_buy * 100:
                cash -= target_buy * 100
                positions_price.append(target_buy)
                positions_vol.append(100)
                last_buy_price = target_buy
                trade_count += 1
                
    return cash, trade_count

def test_numba():
    # 第一次运行会包含编译时间
    start = time.time()
    c, t = core_backtest(prices, 0.01, 0.02)
    print(f"First run (compile): {time.time() - start:.4f}s, Trades: {t}")
    
    # 第二次运行 (纯执行)
    start = time.time()
    c, t = core_backtest(prices, 0.01, 0.02)
    print(f"Second run (cached): {time.time() - start:.4f}s, Trades: {t}")

if __name__ == "__main__":
    test_numba()
