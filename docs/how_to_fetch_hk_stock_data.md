# 港股历史数据抓取设计文档

## 1. 项目概述

### 1.1 目标
开发一个程序，通过 Yahoo Finance API 抓取港股的历史交易数据。

### 1.2 数据来源
- API：Yahoo Finance Chart API
- 基础URL：https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
- 示例：https://query1.finance.yahoo.com/v8/finance/chart/0700.HK

## 2. 技术方案

### 2.1 技术栈选择
- 编程语言：Python
- 主要库：
  - requests：处理 HTTP 请求
  - pandas：数据处理和格式转换
  - json：解析 API 响应

### 2.2 数据获取方式

1. API 参数说明

    period1: 起始时间戳      # 例如：1737170453
    period2: 结束时间戳      # 例如：1737599955
    interval: 1d            # 数据间隔（日线）
    events: capitalGain|div|split  # 包含分红派息等信息
    includeAdjustedClose: true

2. 响应数据结构

    chart:
        result:
            - meta:
                currency: HKD
                symbol: 0700.HK
                exchangeName: HKG
            - timestamp: [...]  # 时间戳数组
            - indicators:
                quote:
                    - volume: [...]   # 成交量
                    - close: [...]    # 收盘价
                    - high: [...]     # 最高价
                    - low: [...]      # 最低价
                    - open: [...]     # 开盘价
                adjclose:
                    - adjclose: [...]  # 复权收盘价

### 2.3 数据结构设计

    数据类属性：
        date: datetime       # 交易日期
        open: float         # 开盘价
        close: float        # 收盘价
        high: float         # 最高价
        low: float          # 最低价
        volume: int         # 成交量
        adj_close: float    # 复权收盘价

## 3. 实现流程

1. 时间戳处理
   - 计算当前时间前5年的时间戳
   - 转换为 Unix 时间戳格式

2. 构建请求
   - 添加必要的请求头
   - 设置查询参数
   - 处理股票代码格式（添加 .HK 后缀）

3. 数据解析
   - 解析 JSON 响应
   - 将时间戳转换为日期
   - 提取价格和成交量数据
   - 处理空值和异常数据

4. 数据存储
   - 保存到数据库
   - 记录更新时间

## 4. 异常处理

1. API 错误处理
   - 请求超时
   - 响应格式错误
   - 数据缺失

2. 数据验证
   - 价格范围检查
   - 日期连续性检查
   - 数据完整性验证

## 5. 注意事项

1. 请求头设置示例：

    User-Agent: Mozilla/5.0...
    Accept: application/json
    Referer: https://finance.yahoo.com

2. 访问频率控制
3. 数据有效性验证
4. 错误重试机制

## 6. 后续优化

1. 支持批量下载
2. 增加数据缓存
3. 添加数据更新机制
4. 支持其他时间周期