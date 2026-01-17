# 📝 模块需求文档：SmartGrid 策略生成器 (v2.1)

## 1. 模块概述 (Module Overview)
* **模块定位**：宿主交易系统中的“策略辅助决策”子模块。
* **核心功能**：基于日线行情数据（OHLC）和用户录入的估值数据，自动计算适配当前波动率的网格参数，并提供日线级别的策略回测验证。
* **输入对象**：A 股场内 ETF 代码（宿主系统提供）。
* **输出对象**：结构化的网格挂单表（JSON/CSV），包含买卖价格、数量序列。

---

## 2. 数据交互规范 (Data Interaction)

本模块不直接连接外部 API，所有数据通过宿主系统的 `DataService` 获取。

### 2.1 输入数据需求
模块运行时，需向宿主系统请求以下数据对象：

1.  **基础行情 (`MarketData`):**
    * `symbol`: 标的代码
    * `period`: 日线 (Daily)
    * `adjust`: **前复权 (Forward Adjusted)** [重要：必须复权，否则回测失效]
    * `start_date`: 默认为 T-365 (1年)，可配置 T-3年。
    * `fields`: `date`, `open`, `high`, `low`, `close`

2.  **人工补充数据 (`ManualInput`):**
    * *前端表单录入，非系统获取*
    * `current_pe_percentile`: 当前 PE 百分位 (0-100)
    * `current_pb_percentile`: 当前 PB 百分位 (0-100)
    * `total_capital`: 计划投入总资金
    * `base_position_ratio`: 底仓比例 (0.0 - 1.0)

---

## 3. 核心算法逻辑 (Core Algorithms)

此部分为开发核心，需严格按公式实现。

### 3.1 波动率计算 (Volatility Engine)
* **TR (True Range) 计算**:
    $$TR = Max(High - Low, |High - PreClose|, |Low - PreClose|)$$
* **ATR (Average True Range)**:
    $$ATR(N) = MA(TR, N)$$
    * *参数 N*: 默认 14。
* **布林带 (Bollinger Bands)**:
    * 中轨: $MA(Close, 20)$
    * 上轨: $Mean + 2 * StdDev$
    * 下轨: $Mean - 2 * StdDev$

### 3.2 策略模式判定 (Strategy Mode Selector)
根据用户输入的 `PE/PB 百分位` 和系统计算的 `ATR`，自动推荐模式：

| 判定条件 (逻辑与) | 推荐模式 | 参数特征 |
| :--- | :--- | :--- |
| 估值 < 20% | **潜伏积累 (Accumulate)** | 买入量 > 卖出量 (1.2:1)，宽底 |
| 20% ≤ 估值 ≤ 70% | **标准震荡 (Neutral)** | 买入量 = 卖出量，标准网格 |
| 估值 > 70% | **趋势/防卖飞 (Trend)** | 买入量 > 卖出量，或区间大幅上移 |

### 3.3 参数生成逻辑 (Parameter Generator)

#### A. 区间计算 (Range)
* **上限 ($P_{max}$)** = $min(布林上轨, 最近60日最高价)$
* **下限 ($P_{min}$)** = $max(布林下轨, 最近60日最低价)$
* *例外处理：* 若选择“天地单”模式，则取历史极值。

#### B. 步长计算 (Step)
* **基准步长 ($Step_{base}$)** = $ATR(14)$ 的当前值
* **格数 ($N_{grids}$)** = $(P_{max} - P_{min}) / Step_{base}$
    * *约束：* 若 $N_{grids} < 10$，强制 $Step = (P_{max} - P_{min}) / 10$ (保证至少切分10格)。

#### C. 单格资金分配 (Position Sizing)
* **可动用资金** = `total_capital` * (1 - `base_position_ratio`)
* **单格金额** = 可动用资金 / $N_{grids}$
* **单格股数 ($Vol_{per\_grid}$)** = 单格金额 / 当前价格 (向下取整到 100 股)

#### D. 买卖序列生成 (Order Book)
生成一个 List，包含所有网格线：
* $Price_i = P_{min} + i * Step$
* $BuyVol_i$ 与 $SellVol_i$ 根据 **3.2 策略模式** 调整系数。
    * *Neutral:* Buy = Sell = $Vol_{per\_grid}$
    * *Accumulate/Trend:* Buy = $1.2 * Vol_{per\_grid}$, Sell = $0.8 * Vol_{per\_grid}$ (示例系数，需提供配置项)

---

## 4. 回测引擎逻辑 (Backtest Engine - Daily)

由于只有日线数据，需采用 **Path Simulation (路径模拟)** 算法。

### 4.1 撮合机制
对每一根 K 线 ($O, H, L, C$)，按以下逻辑判断是否触发网格：

1.  **路径假设 (Path Assumption)**:
    * 若 $Close > Open$ (阳线): 假设路径为 $Open \rightarrow Low \rightarrow High \rightarrow Close$
    * 若 $Close < Open$ (阴线): 假设路径为 $Open \rightarrow High \rightarrow Low \rightarrow Close$
    * *注：此假设能覆盖日内主要波动，比单纯用 Close 判定更准确。*

2.  **触发判定**:
    * 遍历生成的网格线集合 $\{G_1, G_2, ... G_n\}$。
    * **买入触发**: 当模拟路径**向下**穿过网格线 $Price_i$ 时，标记买入。
    * **卖出触发**: 当模拟路径**向上**穿过网格线 $Price_i$ 时，且当前持有该网格的筹码，标记卖出。

3.  **穿透修正 (Filters)**:
    * **High/Low 穿透率**: 若某网格价格 $P$ 刚好等于当日 $High$，为了防止虚假成交，仅当 $High > P * (1 + 0.001)$ (滑点保护) 时才算卖出成交。

### 4.2 回测产出指标
* **总收益率 (Total Return)**
* **网格利润 (Grid Profit)**: 仅统计“低吸高抛”产生的已实现收益。
* **浮动盈亏 (Unrealized PNL)**: 底仓及未卖出网格的市值波动。
* **交易频率**: 平均每日成交单数。
* **破网率**: 价格超出区间上下限的天数占比。

---

## 5. 前端功能交互 (UI/UX Logic)

本模块作为宿主系统的一个 Tab 或 弹窗存在。

### 5.1 配置面板 (Config Panel)
* **标的选择**: 下拉框选择 (数据源自宿主系统)。
* **基本面参数**: 输入框 (PE/PB 百分位)。
* **资金设置**: 输入框 (总金额，底仓 %)。
* **高级设置 (折叠)**:
    * ATR 系数 (默认 1.0)
    * 模式强制覆盖 (下拉：自动/震荡/多头)
    * 回测时间跨度 (默认 1年)

### 5.2 结果面板 (Result Dashboard)
* **可视化图表**:
    * 主图：K线图 + 上下轨横线 + 买卖点图标 (Triangle)。
    * 副图：资金曲线 vs 标的净值曲线。
* **核心数据卡片**:
    * [建议区间: 1.88 - 2.15]
    * [建议步长: 1.5% (0.03元)]
    * [回测年化: 15.2%] vs [持仓年化: -3.4%]
* **执行方案导出**:
    * 表格展示：`序号 | 触发价格 | 买入量 | 卖出量`
    * 按钮：`导出 CSV` (供用户手动去券商软件导入)。

---

## 6. 开发注意事项 (Dev Notes)

1.  **复权陷阱**: 必须反复确认宿主系统传入的数据是**前复权**数据。不复权的数据会导致回测中因分红/拆股产生的巨大价格缺口，导致网格逻辑崩盘。
2.  **精度控制**: 价格计算保留 3 位小数 (ETF 最小变动 0.001)，股数向下取整到 100 的倍数。
3.  **性能**: 日线回测计算量极小，建议在该模块加载时**实时计算**，无需预处理存储。
4.  **状态保持**: 回测时需维护一个虚拟账户对象 `VirtualAccount`，包含 `cash`, `positions dict {price_level: volume}`，严禁使用“未来函数”。

---

## 7. 验收标准 (Acceptance Criteria)
1.  **数据准确性**: 能够正确读取宿主系统的 K 线数据，ATR 计算结果与主流软件（如通达信/同花顺）误差 < 1%。
2.  **逻辑自洽**: 在极端行情（如连续一字涨停/跌停）下，回测引擎不应报错，且不应产生错误的“穿透成交”。
3.  **参数合理**: 针对低波 ETF（如银行）生成的网格应当比高波 ETF（如券商）更密集。
4.  **输出可用**: 导出的 CSV 文件格式清晰，用户可直接理解并用于实盘挂单。