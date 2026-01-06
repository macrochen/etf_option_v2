# 威科夫理论股票分析系统 - 需求与设计文档 (PRD)

## 1. 项目概述 (Project Overview)

**目标**: 在现有 `etf_option_v2` 交易系统中增加“威科夫分析 (Wyckoff Analysis)”模块。该模块旨在帮助交易者通过威科夫方法论（Wyckoff Methodology）及其现代改良版（如 David Weis 的理论），识别市场结构、供需关系及关键交易信号。

**核心价值**: 通过自动化识别“吸筹/派发”区间以及“弹簧效应 (Spring)”和“上冲回落 (Upthrust)”等关键行为，辅助用户在低风险点位（Danger Point）进行交易决策。

## 2. 核心功能需求 (Functional Requirements)

### 2.1 数据输入 (Data Input)
系统需支持两种数据来源模式：

1.  **在线搜索与下载 (Search & Download)**:
    *   复用现有的数据下载模块（基于 `akshare` / `yfinance`）。
    *   支持 A股、港股、美股代码输入。
    *   自动获取日线（Daily）及周线（Weekly）数据。

2.  **本地数据上传 (CSV Upload)**:
    *   用户可上传本地 CSV 文件。
    *   **格式要求**: 必须包含表头，至少包含以下列：`Date` (日期), `Open` (开盘), `High` (最高), `Low` (最低), `Close` (收盘), `Volume` (成交量)。
    *   **数据清洗**: 系统需自动解析日期格式，处理空值，并按时间排序。

### 2.2 核心分析引擎 (Core Analysis Engine)

分析引擎将基于 `pandas` 处理 OHLCV 数据，执行以下逻辑：

#### A. 市场结构与趋势识别
*   **波段识别 (Swing Identification)**: 识别关键的高点（Swing Highs）和低点（Swing Lows）。
*   **自动画线 (Support & Resistance)**:
    *   基于波段低点聚类识别 **支撑线 (Ice Line)**。
    *   基于波段高点聚类识别 **阻力线 (Creek)**。
*   **交易区间 (Trading Range)**: 识别价格横盘震荡的区域，定义为潜在的吸筹或派发区。

#### B. 关键威科夫事件检测 (Wyckoff Events)
基于 David Weis 的《Trades About to Happen》理论，重点检测以下信号：

1.  **弹簧效应 (Spring) / 震仓 (Shakeout)**:
    *   **定义**: 价格跌破近期关键支撑位（Trading Range Low），但在短时间内（1-3根K线）收回支撑位之上。
    *   **过滤器**: 结合成交量判断。低量 Spring 暗示供应枯竭（测试成功）；高量 Spring 需要随后的二次测试（Secondary Test）。
    *   **信号输出**: 标记为 Potential Spring。

2.  **上冲回落 (Upthrust - UT)**:
    *   **定义**: 价格突破近期关键阻力位（Trading Range High），但在短时间内跌回阻力位之下。
    *   **信号输出**: 标记为 Potential Upthrust。

3.  **停止行为 (Stopping Action)**:
    *   **恐慌抛售 (Selling Climax - SC)**: 下跌趋势中出现的极长阴线或长下影线，配合极巨量。
    *   **购买高潮 (Buying Climax - BC)**: 上涨趋势中出现的极长阳线或长上影线，配合极巨量。

4.  **努力与结果 (Effort vs Result) - 简易版**:
    *   识别“高量滞涨”或“高量止跌”的 K 线。

### 2.3 可视化与报告 (Visualization & Reporting)

*   **交互式 K 线图**:
    *   展示 OHLC 蜡烛图。
    *   叠加自动计算的 支撑线 (绿色) 和 阻力线 (红色)。
    *   在特定 K 线上方/下方标记信号图标 (如 "S" 代表 Spring, "UT" 代表 Upthrust, "SC" 代表 Selling Climax)。
*   **成交量图**:
    *   传统的成交量柱状图。
    *   *(进阶保留)*: 累积波浪成交量 (Weis Wave Volume)。
*   **分析结论面板**:
    *   **当前状态**: e.g., "处于震荡区间", "尝试突破", "潜在底部反转"。
    *   **信号列表**: 按时间倒序列出最近检测到的威科夫事件。

## 3. 用户界面设计 (UI Design)

**页面地址**: `/wyckoff_analysis`

**布局**:
1.  **控制栏**:
    *   Tab 1: **搜索代码** (输入框 + 市场选择 + "分析"按钮)。
    *   Tab 2: **上传文件** (文件选择框 + "上传并分析"按钮)。
2.  **主图表区**:
    *   大尺寸 K 线图，包含自动画线和信号标注。
3.  **详情面板 (Side/Bottom Panel)**:
    *   显示检测到的支撑/压力位价格。
    *   显示最近一次“Spring”或“Upthrust”发生的日期和置信度。

## 4. 技术栈 (Tech Stack)

*   **后端**: Python, Flask, Pandas, NumPy (用于计算波峰波谷和回归分析)。
*   **前端**: HTML5, Bootstrap 5, ECharts (百度开源图表库，适合绘制 K 线和标注)。

## 5. 开发计划 (Development Plan)

1.  **基础设施**:
    *   创建 `routes/wyckoff_routes.py`。
    *   创建 `templates/wyckoff_analysis.html`。
2.  **数据处理层**:
    *   实现 CSV 解析与标准化工具。
    *   集成现有的数据获取工具。
3.  **核心算法实现 (`strategies/wyckoff_analyzer.py`)**:
    *   Step 1: 实现 `find_swings()` (识别高低点)。
    *   Step 2: 实现 `identify_support_resistance()` (确定箱体)。
    *   Step 3: 实现 `detect_springs_upthrusts()` (核心信号)。
4.  **前端集成**:
    *   使用 ECharts 渲染数据和信号。
5.  **测试与调优**:
    *   使用历史经典案例（如 PDF 中的案例）测试算法准确性。

---
*文档版本: v1.1*
*最后更新: 2026-01-04*
