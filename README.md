# 交易策略与资产组合分析平台

一个以 Flask 为核心的交易研究、回测与投资组合管理平台，覆盖 A 股与海外市场，当前将以下能力整合在同一个项目中：

- A 股 ETF 期权 Delta 回测
- A 股 ETF 期权波动率回测
- 回测方案管理
- 香农网格评分与回测
- A 股 / 美股 / 港股波动率与数据管理
- 国内 / 海外持仓管理
- 投资组合分析与资产全景管理
- 财报期权策略分析
- 威科夫分析
- 大 V 跟投管理
- 名称映射与数据下载工具

## 技术栈

- 后端：Python 3、Flask、Pandas、NumPy、SQLite
- 前端：Jinja2、Bootstrap 5、jQuery、Plotly、ECharts、Highcharts
- 数据源与集成：AkShare、yfinance、Tiger OpenAPI、Futu API
- 图像处理：pytesseract、Pillow

## 项目命名

- 产品名称：`交易策略与资产组合分析平台`
- 项目目录 / 仓库建议名称：`strategy_portfolio_platform`

## 当前项目结构

```text
strategy_portfolio_platform/
├── app.py                    # Flask 应用入口，注册所有蓝图
├── start.sh                  # 本地启动脚本
├── backtest_engine.py        # ETF 期权回测主引擎
├── strategy_analyzer.py      # 回测指标与绩效分析
├── visualization.py          # 回测图表生成与结果格式化
├── routes/                   # Flask 蓝图与 HTTP API
├── strategies/               # 期权策略实现与工厂
├── grid/                     # 香农网格相关引擎、边界计算、分钟数据加载
├── services/                 # OCR、价格、评分、相似场景搜索等服务
├── db/                       # SQLite 数据库、数据库访问层、迁移脚本
├── templates/                # Jinja2 页面模板
├── static/                   # 前端 JS / CSS / 图标
├── utils/                    # 通用工具、错误处理、配置辅助
├── docs/                     # 设计文档、PRD、业务说明
├── data/                     # 历史数据与缓存数据
└── config/                   # 应用配置、券商配置文件
```

## 核心模块说明

### 1. Web 应用入口

- `app.py`
  - 创建 Flask 应用
  - 注册各业务蓝图
  - 提供首页和汇率接口
  - 统一处理部分日志与错误

### 2. ETF 期权回测

- `backtest_engine.py`
  - 负责加载 `db/market_data.db` 中的 ETF 和期权历史数据
  - 根据策略上下文创建策略实例
  - 按交易日驱动策略执行
  - 汇总交易记录、资金曲线、分析结果和图表

- `strategies/`
  - `factory.py`：策略工厂
  - `strategy_context.py`：回测上下文
  - `base.py`：策略基类
  - `delta_*`：基于 Delta 的策略实现
  - `volatility_*`：基于波动率的策略实现
  - `wheel.py`：轮转策略
  - `option_selector.py`：期权选择逻辑
  - `wyckoff_analyzer.py`：威科夫相关分析逻辑

- `strategy_analyzer.py`
  - 计算收益率、波动率、夏普、回撤、交易胜率、风险指标
  - 支持与 ETF 买入持有收益对比

### 3. 路由与页面

`routes/` 下按业务拆分蓝图，主要包括：

- `backtest_routes.py`：Delta 回测、信号查看、方案保存
- `volatility_routes.py`：波动率回测和 ETF 波动率接口
- `scheme_routes.py`：回测方案管理
- `etf_data_routes.py`：A 股 ETF 波动率管理
- `stock_data_routes.py`：美股 / 港股波动率、价格、下载、财报数据
- `option_routes.py`：期权提醒、Delta 刷新、收盘价刷新
- `portfolio_routes.py`：国内持仓与资产全景
- `tiger_routes.py`：海外持仓与 Tiger 数据接口
- `futu_routes.py`：富途持仓接口
- `earnings_routes.py`：财报期权策略分析
- `shannon_routes.py`：香农网格评分、数据下载、历史相似场景、回测
- `hpc_routes.py`：大 V 跟投管理
- `data_download_routes.py`：CSV 下载相关入口
- `wyckoff_routes.py`：威科夫分析
- `symbol_mapping_routes.py`：标的名称映射维护

### 4. 香农网格模块

- `grid/`
  - `shannon_engine.py`：网格回测主引擎
  - `boundary_calc.py`：动态上下限计算
  - `data_loader.py` / `min_data_loader.py`：日线 / 分钟线数据加载
  - `valuation_manager.py`：估值处理

- `services/shannon_scorer.py`
  - 对标的进行香农网格适配评分

- `services/similarity_searcher.py`
  - 查询历史相似市场情景

### 5. 持仓与辅助服务

- `services/ocr_service.py`：截图 OCR
- `services/price_service.py`：价格服务
- `routes/portfolio_routes.py`：国内账户、资产、价格刷新、截图上传
- `routes/tiger_routes.py` / `routes/futu_routes.py`：海外券商持仓接口

## 模板与前端

- `templates/base.html`：站点公共布局和导航
- `templates/index.html`：Delta 回测首页
- `templates/volatility_backtest.html`：波动率回测页面
- `templates/shannon_grid.html`：香农网格页面
- `templates/portfolio.html`：国内持仓页面
- `templates/positions.html`：海外持仓页面
- `templates/earnings_analysis.html`：财报分析页面
- `templates/wyckoff_analysis.html`：威科夫分析页面

前端脚本主要放在 `static/js/`，采用 jQuery 直接调用各 Flask API：

- `volatility_backtest.js`
- `delta_backtest.js`
- `portfolio.js`
- `shannon_grid.js`
- `scheme_management.js`
- `hpc.js`

## 数据库

项目当前主要使用 SQLite，本地数据库位于 `db/`：

- `market_data.db`：ETF、期权、波动率等核心市场数据
- `market_data_min.db`：分钟级数据
- `backtest_schemes.db`：回测方案
- `portfolio.db`：国内持仓与账户
- `us_stock.db`：海外股票与波动率相关数据
- `hpc.db`：大 V 跟投数据

数据库路径配置在 `db/config.py`。

## 运行方式

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动项目

推荐直接使用脚本：

```bash
bash start.sh
```

脚本会：

- 检查并释放 `5001` 端口
- 激活 `.venv`
- 启动 `app.py`
- 尝试自动打开浏览器

也可以手动启动：

```bash
source .venv/bin/activate
python app.py
```

默认访问地址：

- [http://127.0.0.1:5001](http://127.0.0.1:5001)

## 主要页面入口

项目导航在 `templates/base.html` 中统一维护，常用入口包括：

- `/`：基于 Delta 的 ETF 期权回测
- `/volatility_backtest`：基于波动率的回测
- `/scheme_management`：回测方案管理
- `/etf_volatility_management`：A 股波动率管理
- `/us_stock_volatility_management`：海外波动率管理
- `/shannon`：香农网格
- `/positions_page`：海外持仓
- `/portfolio`：国内持仓
- `/symbol_mapping`：名称映射
- `/hpc`：大 V 跟投
- `/watchlist`：自选股
- `/earnings_analysis`：财报期权策略
- `/data_download_page`：数据下载
- `/wyckoff_analysis`：威科夫分析

## 文档说明

`docs/` 下已经积累了较多业务和设计文档，重点包括：

- 回测引擎设计
- 回测方案管理设计
- ETF / 美股波动率设计
- 香农网格 PRD 与实现说明
- 威科夫分析设计
- 资产组合与跟投文档

如果要修改某个业务模块，建议先查对应文档，再看对应 `routes/`、`templates/`、`static/js/` 和服务层代码。

## 开发建议

- 新增 HTTP 功能时，优先在 `routes/` 中按业务增加蓝图或扩展现有蓝图
- 新增策略时，放到 `strategies/` 并注册到策略工厂
- 前端页面遵循“模板 + 页面级 JS”的现有模式
- 数据结构变更时，同时检查 `db/` 访问层和对应模板 / 路由
- 这个仓库是长期演化项目，README 仅做总览，具体实现以代码为准

## 风险提示

- 回测、评分和分析结果仅用于研究与策略验证
- 不构成投资建议
- 实盘交易中的流动性、滑点、手续费、保证金约束可能与历史回测不同
