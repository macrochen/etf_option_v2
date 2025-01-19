# 表结构文档

## combined_signals 买卖点数据表
| 字段名           | 数据类型               | 约束          | 说明                       |
|------------------|------------------------|---------------|----------------------------|
| etf_code         | VARCHAR(10)            | NOT NULL      | ETF代码                    |
| trend_indicator   | VARCHAR(50)            | NOT NULL      | 存储趋势指标名称          |
| Buy_Signal       | TEXT                   | NOT NULL      | 存储买点日期的逗号分隔字符串 |
| Sell_Signal      | TEXT                   | NOT NULL      | 存储卖点日期的逗号分隔字符串 |
| 主键             | (etf_code, trend_indicator) |           |                            |

## etf_daily ETF历史价格表
| 字段名       | 数据类型               | 约束          | 说明       |
|--------------|------------------------|---------------|------------|
| etf_code     | VARCHAR(10)            | NOT NULL      | ETF代码    |
| date         | DATE                   | NOT NULL      | 日期       |
| open_price   | DECIMAL(10,4)         |               | 开盘价     |
| close_price  | DECIMAL(10,4)         |               | 收盘价     |
| 主键         | (etf_code, date)      |               |            |

## option_daily 期权链数据历史表
| 字段名         | 数据类型               | 约束          | 说明       |
|----------------|------------------------|---------------|------------|
| etf_code       | VARCHAR(10)            | NOT NULL      | ETF代码    |
| date           | DATE                   | NOT NULL      | 日期       |
| contract_code  | VARCHAR(20)            |               | 合约代码   |
| change_rate    | DECIMAL(10,4)         |               | 变动率     |
| open_price     | DECIMAL(10,4)         |               | 开盘价     |
| close_price    | DECIMAL(10,4)         |               | 收盘价     |
| strike_price   | DECIMAL(10,4)         |               | 行权价     |
| delta          | DECIMAL(10,4)         |               | Delta值    |
| settlement_price| DECIMAL(10,4)        |               | 结算价     |
| 主键           | (etf_code, date, contract_code) | |            |
| 外键           | (etf_code, date) REFERENCES etf_daily(etf_code, date) | | |

## volatility_stats ETF历史波动率数据表
| 字段名       | 数据类型               | 约束          | 说明       |
|--------------|------------------------|---------------|------------|
| etf_code     | VARCHAR(10)            |               | ETF代码    |
| calc_date    | DATE                   |               | 计算日期   |
| stats_data   | TEXT                   |               | 统计数据   |
| display_data  | TEXT                  |               | 显示数据   |
| start_date   | DATE                   |               | 起始日期   |
| end_date     | DATE                   |               | 结束日期   |
| 主键         | (etf_code, calc_date) |               |            |

## backtest_schemes 策略回测方案表
| 字段名       | 数据类型               | 约束          | 说明       |
|--------------|------------------------|---------------|------------|
| id           | INTEGER PRIMARY KEY AUTOINCREMENT | | 唯一标识符 |
| name         | VARCHAR(100)           | NOT NULL UNIQUE | 策略名称  |
| params       | TEXT                   | NOT NULL      | 参数       |
| results      | TEXT                   |               | 结果       |
| created_at   | TIMESTAMP              | NOT NULL      | 创建时间   |
| updated_at   | TIMESTAMP              | NOT NULL      | 更新时间   |
