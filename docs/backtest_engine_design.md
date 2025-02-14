# 网格交易回测引擎设计

## 1. 核心类设计

### 1.1 网格生成器 (GridGenerator)
1. **功能职责**
   - 根据参数生成网格价格序列
   - 计算每个网格的买卖价格

2. **关键方法**
   - generate_grids(current_price, atr, grid_count, atr_factor)
     * 当前价格作为底仓买入价格（第一个网格）
     * 网格间距 = ATR * ATR系数
     * 向上生成 (grid_count-1)/2 个网格
     * 向下生成 (grid_count-1)/2 个网格

### 1.2 交易执行器 (TradeExecutor)
1. **功能职责**
   - 判断是否触发网格交易
   - 执行买卖操作
   - 记录交易明细

2. **关键方法**
   - check_and_trade(current_price, last_price, grids)
     * 检查是否触及网格线
     * 计算跨越网格数量
     * 如果跨越多个网格，按倍数计算交易量
     * 更新持仓状态
     * 记录交易明细

### 1.3 回测引擎 (BacktestEngine)
1. **功能职责**
   - 加载历史数据
   - 初始化网格
   - 模拟交易执行
   - 计算回测结果

2. **关键方法**
   - run_backtest(params, hist_data, atr)
     * 生成网格
     * 模拟交易执行
     * 计算评估指标

## 2. 数据结构

### 2.1 网格数据 (Grid)
- buy_price: float    # 买入价格
- sell_price: float   # 卖出价格
- position: float     # 当前持仓量

### 2.2 交易记录 (Trade)
- timestamp: datetime  # 交易时间
- price: float        # 成交价格
- amount: float       # 成交数量
- direction: str      # 买入/卖出
- grid_index: int     # 触发网格索引

### 2.3 回测结果 (BacktestResult)
- params: GridParams           # 回测参数
- trades: List[Trade]         # 交易记录
- daily_returns: pd.Series    # 每日收益率
- evaluation: EvaluationResult  # 评估结果

## 3. 实现流程

### 3.1 初始化阶段
- 加载历史数据
- 生成初始网格
- 设置初始资金和持仓

### 3.2 回测执行
- 遍历历史数据
- 检查是否触发网格
- 执行交易并记录
- 更新持仓状态

### 3.3 结果计算
- 统计交易记录
- 计算每日收益
- 计算评估指标
- 生成回测报告

## 4. 关键细节处理

### 4.1 资金管理
- 初始资金的50%用于建立底仓（第一个网格）
- 剩余资金平均分配到剩余网格

### 4.2 持仓管理
- 每个网格的基础交易量相等
- 跨越N个网格时，交易量为基础量的N倍
- 触发买入时检查可用资金
- 触发卖出时检查可用持仓

### 4.3 交易成本
- 买卖双向费用：万分之一