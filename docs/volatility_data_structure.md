# ETF波动率数据结构说明文档

本文档详细说明了ETF波动率数据生成工具(`tools/volatility_data_generator.py`)所生成的数据结构。数据主要分为两个部分：统计数据(`stats_data`)和展示数据(`display_data`)。

## 1. 统计数据 (stats_data)

统计数据包含上行波动率和下行波动率的统计信息，JSON结构如下：

```json
{
    "3个月": {
        "up_volatility": {
            "volatility": 0.05,
            "std": 0.015,
            "min": 0.042,
            "max": 0.102,
            "percentiles": {
                "25": 0.044,
                "50": 0.046,
                "75": 0.048
            }
        },
        "down_volatility": {
            "volatility": 0.059,
            "std": 0.026,
            "min": 0.041,
            "max": 0.115,
            "percentiles": {
                "25": 0.041,
                "50": 0.047,
                "75": 0.063
            }
        }
    },
    ...其他不同时长的波动率数据
    "trading_range": {
        "start": "2023-01-01",
        "end": "2023-10-01"
    }
    
}
```

## 3. 数据说明

1. **上行/下行波动率**
   - 上行波动率(`upward`): 计算ETF价格上涨时的波动率
   - 下行波动率(`downward`): 计算ETF价格下跌时的波动率的绝对值

2. **数据精度**
   - 所有波动率数据保留3位小数
   - 波动率以月度值表示（使用21个交易日计算）

3. **数据存储**
   - 数据存储在SQLite数据库的`volatility_stats`表中
   - `stats_data`和`display_data`以JSON字符串形式存储
   - 每个ETF代码对应一条记录，包含计算日期和数据有效期

## 4. 使用示例

前端可以通过API获取波动率数据：

```javascript
$.get('/api/etf/volatility', { etf_code: etf_code }, function(data) {
    // data.stats_data 包含统计数据
    // data.display_data 包含展示数据
    
    // 使用Plotly.js绘制箱线图
    const boxplotData = data.display_data.boxplot;
    
    // 使用Plotly.js绘制分布图
    const distributionData = data.display_data.distribution;
});
```
