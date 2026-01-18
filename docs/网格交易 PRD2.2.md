这份更新后的需求文档（v2.2）融合了网格交易的核心理念：**基于状态机的 OMS 模拟**、**T+1 库存冻结机制**以及**悲观优先的撮合逻辑**。

这份文档将作为开发人员实施“防造假回测”的直接依据。

---

# 📝 模块需求文档：SmartGrid 策略生成器 (v2.2 - 严谨回测版)

## 1. 模块概述 (Module Overview)

* **模块定位**：宿主交易系统中的“策略辅助决策”子模块。
* **核心功能**：基于日线行情数据（OHLC）和用户录入的估值数据，自动计算适配当前波动率的网格参数。
* **核心差异化**：**引入“影子账户”与“T+1 冻结”机制**，在日线级别回测中严格剔除虚假利润（Look-ahead Bias），提供接近实盘的压力测试结果。
* **输入对象**：A 股场内 ETF 代码（宿主系统提供）。
* **输出对象**：结构化的网格挂单表及防伪回测报告。

---

## 2. 数据交互规范 (Data Interaction)

本模块通过 `DataService` 获取数据，不做变更。

### 2.1 输入数据需求

1. **基础行情 (`MarketData`):**
* `period`: 日线 (Daily)
* `adjust`: **前复权 (Forward Adjusted)** [**核心约束**：必须复权，防止分红缺口干扰网格逻辑]
* `fields`: `date`, `open`, `high`, `low`, `close`


2. **人工补充数据 (`ManualInput`):**
* `total_capital`: 计划投入总资金
* `base_position_ratio`: **锁定底仓比例** (0.0 - 1.0)。
    * *定义修正*：此比例对应的资金用于买入**永久持有的底仓 (Locked Position)**，无论价格如何上涨均**不卖出**，仅享受长期趋势收益。
    * *网格资金*：剩余资金 (`1 - ratio`) 用于网格交易（买卖周转）。

---

## 3. 核心算法逻辑 (Core Algorithms)

此部分定义网格的“静态参数生成”，即生成网格的刻度。

### 3.1 波动率计算 (Volatility Engine)

* 同 v2.1（保留 TR、ATR、布林带计算公式）。

### 3.2 策略模式判定 (Strategy Mode Selector)

* 同 v2.1（潜伏积累、标准震荡、趋势防卖飞）。

### 3.3 参数生成逻辑 (Parameter Generator)

* 同 v2.1（区间计算、等比步长、资金分配）。
* **资金分配修正**：
    * `Grid_Capital` = `Total_Capital` * (1 - `Base_Position_Ratio`)
    * 单格买卖量基于 `Grid_Capital` 计算。

* **网格状态字典 (`GridStateDict`)**: 初始化时，需生成一个包含所有网格价格线的字典，默认状态为 `IDLE`（空闲）。

---

## 4. 回测引擎逻辑 (Backtest Engine - Event Driven)

**[重大变更]** 弃用简单的向量化计算，改为**基于事件驱动的 T+1 影子账户模拟**。

### 4.1 虚拟账户对象 (Virtual Account Model)

在回测内存中维护一个账户对象，包含以下库存变量：

1. **`Inventory_Locked` (锁定底仓)**: 根据 `base_position_ratio` 买入的筹码，**永不卖出**。
2. **`Inventory_Available` (网格可用)**: 用于网格卖出的筹码（昨日及之前买入）。
3. **`Inventory_Frozen` (网格冻结)**: 当日网格买入的筹码，**T+1 可卖**。
4. **`Cash`**: 可用资金。

### 4.2 撮合循环逻辑 (The Matching Loop)

对每一根 K 线（Day T），必须严格按以下 **4 步顺序** 执行，不可颠倒：

#### Step 0: 初始化 (Initialization - Day 0 Only)

* **锁定底仓买入**: 使用 `Total_Capital * Base_Ratio` 买入股票，计入 `Inventory_Locked`。
* **网格初始建仓 (Auto Active Position)**:
    * 根据 `Start_Price` 在网格区间的位置，计算需持有的**活跃筹码**。
    * *逻辑*：假设价格处于网格 60% 分位，则买入下方 60% 网格对应的筹码，计入 `Inventory_Available`，以便后续上涨时有货可卖。
    * *资金来源*：从剩余的 `Grid_Capital` 中扣除。

#### Step 1: 盘前结算 (Pre-Market Settlement)

* **动作**：模拟过夜。
* **逻辑**：
* `Inventory_Available += Inventory_Frozen`
* `Inventory_Frozen = 0`
* *解释*：将昨天的冻结持仓全部转为今日可用持仓。



#### Step 2: 卖出判定 (Sell Logic - High Priority)

* **依据**：当日最高价 (`High`)。
* **逻辑**：
* 遍历所有状态为 `OPEN_SELL` 的网格线。
* 若 `High >= Grid_Price` **且** `Inventory_Available > 0`：
* **执行成交**：`Cash += Grid_Price * Volume`
* **扣减库存**：`Inventory_Available -= Volume` (扣减老股)
* **状态变更**：
* 当前网格置为 `IDLE`。
* 下方一格置为 `OPEN_BUY` (允许低吸接回)。




* *例外*：若 `Inventory_Available == 0`，即使价格触发也**严禁成交**（视为踏空）。



#### Step 3: 买入判定 (Buy Logic - Low Priority)

* **依据**：当日最低价 (`Low`)。
* **逻辑**：
* 遍历所有状态为 `OPEN_BUY` 的网格线。
* 若 `Low <= Grid_Price` **且** `Cash >= Cost`：
* **执行成交**：`Cash -= Grid_Price * Volume`
* **增加库存**：`Inventory_Frozen += Volume` (**注意：直接进入冻结池**)
* **状态变更**：
* 当前网格置为 `FILLED`。
* 上方一格置为 `OPEN_SELL` (挂出卖单，但需等 T+1 解冻后才能实际生效)。







#### Step 4: 收盘状态更新 (Post-Market Update)

* 更新每日资产净值：`NetValue = Cash + (Available + Frozen) * Close`。

### 4.3 路径模糊处理 (Path Ambiguity Handling)

* **默认假设**：采用上述“先判卖、后判买”的逻辑，本质是模拟“利用底仓做 T”或“持有待涨”。
* **理由**：在缺乏分钟线数据时，假设“先卖后买”是利用 T+0 规则的合法边界；而假设“先买后卖”则默认了当日买入当日卖出，违反 T+1 规则。因此，**先卖后买是回测的合规下限**。

---

## 5. 前端功能交互 (UI/UX Logic)

### 5.1 配置面板

* 保持不变。

### 5.2 结果面板 (Result Dashboard)

新增关键指标，体现回测严谨性：

1. **真实换手率 (Turnover Rate)**:
* 展示网格策略实际消耗的交易费用。


2. **无效触网次数 (Missed Trades)**:
* 统计因 `Inventory_Available = 0` (无货可卖) 或 `Cash = 0` (无钱可买) 而错过的理论交易次数。
* *提示文案*：“检测到 X 次价格触发但未成交，主要原因为 T+1 锁仓或资金耗尽，这通常意味着该区间网格密度过大。”


3. **图表增强**:
* 在 K 线图上，仅标记**真实成交**的点。触发但未成交的“虚假信号”用灰色空心点标记，方便用户复盘。



---

## 6. 开发注意事项 (Dev Notes)

1. **OMS 状态机持久化**: 回测虽然是跑历史数据，但内部必须维护一个 `Grid_State_Map`。
* `{ Price_1.0: "OPEN_BUY", Price_1.1: "IDLE", ... }`
* 严禁使用 `if Price > 1.1 then Sell` 这种无状态判断。必须是 `if Price > 1.1 AND State == 'OPEN_SELL' then Sell`。


2. **精度陷阱**:
* `Inventory_Available` 必须是整数（股数）。
* 资金计算保留 2 位小数。


3. **底仓初始化 (Initial Position)**:
* 回测第一天 (`Start_Date`)，如果用户设置了底仓，这部分底仓应直接初始化进入 `Inventory_Available`，确保第一天如果冲高可以卖出。


4. **性能优化**:
* 虽然逻辑变复杂了，但 Python 处理 500-1000 行日线数据的循环依然是毫秒级的。务必保持实时计算，不要预缓存。



---

## 7. 验收标准 (Acceptance Criteria)

1. **T+1 铁律**: 在任何单日回测记录中，卖出的数量 **绝对不可** 大于 (昨日持仓 + 今日盘前持仓)。当日买入的量必须在次日才能卖出。
2. **无状态冲突**: 同一网格线在未完成“买入-卖出”闭环前，不可连续触发两次同方向交易。
3. **收益率修正**: 相比旧版简易回测，新版回测在震荡下跌市中的收益率应明显更低（因为被 T+1 锁死无法逃顶），这属于**符合预期**的正确结果。
4. **边界测试**: 选取一个历史上的“一字涨停”日进行测试，系统应判定为无法买入（Low > Grid_Buy_Price），或只能卖出底仓。