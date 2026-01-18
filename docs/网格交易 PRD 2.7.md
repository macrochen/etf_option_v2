这是为您生成的最终版需求文档（v2.7）。

这份文档融合了我们讨论的所有精华：**T+1 严谨回测**、**OMS 状态机**、**底仓与网格仓的物理隔离**，以及针对极端行情的**趋势防御（防卖飞/防接飞刀）机制**。它是开发人员实施量化回测的“完全行动指南”。

---

# 📝 模块需求文档：SmartGrid 策略生成器 (v2.7 - 趋势防御终极版)

## 1. 模块概述 (Module Overview)

* **模块定位**：宿主交易系统中的核心策略回测与生成引擎。
* **核心理念**：**"网格为体，趋势为用"**。
* **震荡市**：利用网格仓赚取 Alpha（波动收益）。
* **牛市**：利用底仓锁定 Beta（趋势收益），并利用影子网格防止过早离场。
* **熊市**：利用熔断机制保护 Principal（本金），拒绝在下跌趋势中建立新网格。


* **适用标的**：A 股场内 ETF（严格遵守 T+1 交易制度）。

---

## 2. 数据交互规范 (Data Specifications)

### 2.1 核心数据输入

必须通过宿主系统获取以下数据，若缺失则需由模块内部计算：

1. **基础行情 (`MarketData`)**:
* `frequency`: 日线 (Daily)
* `adjust`: **前复权 (Forward Adjusted)** [**铁律**：防止分红缺口导致错误的止损触发]


2. **趋势指标 (`Indicators`)**:
* `MA20`: 20日移动平均线（短期生命线）。
* `MA60`: 60日移动平均线（牛熊分界线）。
* `REF_MA20`: 昨日的 MA20 值（用于判断均线拐头方向）。



---

## 3. 资金与仓位模型 (Capital & Position Model) **[核心变更]**

为防止逻辑混淆，必须在代码层面严格区分“底仓”与“网格仓”。

### 3.1 资金结构

1. **总资金 (`Total_Capital`)**: 用户投入的总金额。
2. **底仓资金 (`Base_Capital`)**: `Total_Capital * Base_Ratio` (用户配置，如 30%)。
* *用途*：仅用于 T0 时刻建立长期持有的底仓。


3. **运营资金 (`Operational_Capital`)**: `Total_Capital - Base_Capital`。
* *用途*：**仅**这部分资金用于计算网格密度、单格金额和补仓操作。



### 3.2 仓位结构 (Inventory Buckets)

虚拟账户对象 (`VirtualAccount`) 必须维护三个独立的库存变量：

1. **`Inventory_Locked` (压舱石)**:
* 对应底仓资金买入的份额。
* **权限**：**Read-Only**。网格卖出逻辑**严禁**触碰此部分持仓。它只随市场涨跌，除非策略终止。


2. **`Inventory_Available` (可卖网格仓)**:
* 昨日及之前买入的网格筹码。
* **权限**：**Read/Write**。今日的卖出指令只能消耗此变量。


3. **`Inventory_Frozen` (今日冻结仓)**:
* 今日新买入的网格筹码。
* **权限**：**Write-Only**。今日不可卖出，需等次日结算转入 `Available`。



---

## 4. 核心算法逻辑 (Core Algorithms)

### 4.1 市场状态判定 (Market Regime)

在每日决策前，根据 **T-1 日收盘数据** 判定今日状态。

| 状态代码 | 判定公式 (逻辑与) | 业务含义 | 策略行为特征 |
| --- | --- | --- | --- |
| **BULL (强牛)** | `Price > MA20` **且** `MA20 > MA60` | 趋势共振向上 | **惜售模式**：启用影子网格延伸，允许价格突破上限继续持仓。 |
| **BEAR (深熊)** | `Price < MA20` **且** `MA20 < REF_MA20` | 破位且均线向下 | **熔断模式**：禁止开新买单，若价格击穿下限进入休眠。 |
| **SIDEWAY (震荡)** | 不满足上述任一条件 | 无序波动 | **标准模式**：执行标准的高抛低吸网格。 |

### 4.2 越界处理逻辑 (Out-of-Bounds Logic)

#### A. 向上破网 (Price > Grid_Max)

* **触发场景**: 价格突破网格上限，且 `Market_State == BULL`。
* **是否重置**: **否**。不要立即重新计算 ATR 重置网格。
* **行为**: **虚拟延伸 (Virtual Extension)**。
* 系统基于原 `Grid_Step`，在上限之上虚拟生成  条卖出线 ()。
* 只要 `Inventory_Available > 0` (手里还有剩余的网格仓)，就按这些虚拟线继续挂卖单。
* *目的*：让剩余的子弹飞一会儿，直到网格仓彻底卖空，只剩底仓。



#### B. 向下破网 (Price < Grid_Min)

* **触发场景**: 价格跌破网格下限。
* **行为分歧**:
* 若 `Market_State == BEAR`: **休眠 (Hibernate)**。保持旧网格参数，**停止买入**，不建立新网格（防止接飞刀）。
* 若 `Market_State` 转为 `SIDEWAY/BULL` (止跌企稳): **触发重锚 (Trigger Re-Anchor)**。
* 废弃旧网格。
* 以当前价格为中枢，重新计算新的网格区间 (`Grid_Min` ~ `Grid_Max`)。
* *目的*：确认安全后，在低位重新铺开网格。





---

## 5. 回测引擎逻辑 (Backtest Engine - Event Driven)

**架构核心**：基于时间序列的事件驱动循环。

### 5.1 初始化 (Cold Start Logic)

解决“开局即巅峰”或“开局即崩盘”的问题。

1. **计算 T0 状态**: 获取 Start_Date 的 MA 数据。
2. **底仓建立**:
* 花费 `Base_Capital` 市价买入，存入 `Inventory_Locked`。


3. **网格建仓 (Tactical Setup)**:
* **If BEAR**: `Operational_Capital` 保持 100% 现金。**不建仓**，直接进入休眠，等待右侧信号。
* **If BULL**: `Operational_Capital` 激进建仓 (如 50%)。**重锚**：无视历史数据，以 `Start_Price` 为中枢生成网格。
* **If SIDEWAY**: 计算 `Start_Price` 在网格中的分位，按比例建仓 (如价格在低位则买 70%，高位则买 30%)，存入 `Inventory_Available`。



### 5.2 每日撮合循环 (The Daily Loop)

对每一根 K 线，严格按以下顺序执行：

#### Step 1: 盘前结算 (Pre-Market)

* `Inventory_Available += Inventory_Frozen` (T+1 解冻)。
* `Inventory_Frozen = 0`。
* 更新 `Market_State`。

#### Step 2: 风险控制 (Stop Loss)

* 若 `Low <= Grid_Lower_Limit * (1 - Stop_Threshold)` (如 -5%) 且 `Market_State == BEAR`:
* **强制清仓**: 卖出所有 `Available` 和 `Locked` (可选) 持仓。
* **终止**: 标记回测结束 `TERMINATED`。



#### Step 3: 卖出判定 (Sell Logic)

* **依据**: `High`。
* **逻辑**:
* 遍历 `OPEN_SELL` 挂单（含虚拟延伸单）。
* 若 `High >= Sell_Price` **且** `Inventory_Available > 0`:
* **执行**: `Cash` 增加，`Available` 减少。
* **挂单更新**:
* 若在**标准网格区**：成交后，下方挂出 `OPEN_BUY`。
* 若在**虚拟延伸区** (影子网格)：成交后，**不挂回接买单** (单向卖出)。







#### Step 4: 买入判定 (Buy Logic)

* **依据**: `Low`。
* **逻辑**:
* **熔断检查**: 若 `Market_State == BEAR`，**直接 Return** (跳过买入)。
* **休眠检查**: 若 `Price < Grid_Min` (已破网) 且未触发重锚，**直接 Return**。
* 遍历 `OPEN_BUY` 挂单。
* 若 `Low <= Buy_Price` **且** `Cash >= Cost`:
* **执行**: `Cash` 减少，`Frozen` 增加 (**进入冻结池**)。
* **挂单更新**: 当前网格转为 `FILLED`，上方挂出 `OPEN_SELL`。





#### Step 5: 重锚检查 (Re-Anchor Check)

* 若系统处于“休眠”状态 (已向下破网)，且今日 `Market_State != BEAR`:
* 执行 **3.3.B** 的重锚逻辑，生成新网格。



---

## 6. 前端功能交互 (UI/UX)

### 6.1 结果面板增强

1. **K 线图状态色带**:
*
* **红色背景带**: 标记 `BEAR` 区间。
* **绿色背景带**: 标记 `BULL` 区间。


2. **交易点标记**:
* **实心三角**: 真实成交。
* **空心灰三角 (Ghost Signal)**:
* *Tooltip*: "触发买入，但因熊市熔断/向下破网休眠，操作已屏蔽。"
* *Tooltip*: "触发卖出，但因触及底仓锁定阈值，拒绝操作。"





---

## 7. 开发注意事项 (Dev Notes)

1. **未来函数校验**: 计算 MA 时，务必使用 `shift(1)` 的数据。
2. **精度控制**: `Inventory` 必须为整型，资金计算保留 2 位小数。
3. **性能**: 即使逻辑复杂，日线回测仍应在客户端实时计算，避免预处理导致的用户参数调整延迟。

---

## 8. 验收标准 (Acceptance Criteria)

1. **底仓铁律**: 在任何非止损场景下，`Inventory_Locked` 的数量不得减少。
2. **T+1 铁律**: 单日卖出量  昨日总持仓。
3. **熊市表现**: 在 2022 年单边下跌行情中，策略应在跌破 MA20 后停止买入，并没有在底部区域频繁“接飞刀”（除非趋势反转）。
4. **牛市表现**: 在 2020 年单边上涨行情中，策略应能通过“虚拟延伸”机制，比传统网格多吃到至少 20% 的涨幅段。