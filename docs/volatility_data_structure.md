# ETF波动率数据结构说明文档

本文档详细说明了ETF波动率数据生成工具(`tools/volatility_data_generator.py`)所生成的数据结构。数据主要分为两个部分：统计数据(`stats_data`)和展示数据(`display_data`)。

## 1. 统计数据 (stats_data)

统计数据包含上行波动率和下行波动率的统计信息，JSON结构如下：

```json
{
    "upward": {
        "min": 0.123,          // 最小波动率
        "max": 0.456,          // 最大波动率
        "volatility": 0.234,   // 平均波动率
        "std": 0.078,          // 标准差
        "percentiles": {
            "25": 0.189,       // 25分位数
            "50": 0.234,       // 50分位数（中位数）
            "75": 0.289,       // 75分位数
            "90": 0.345        // 90分位数
        }
    },
    "downward": {
        // 结构同upward，但统计的是下行波动率数据
    }
}
```

## 2. 展示数据 (display_data)

展示数据用于前端图表展示，包含箱线图和分布图数据，JSON结构如下：

```json
{
    "boxplot": {
        "upward": [
            0.123,  // 最小值
            0.189,  // Q1 (25分位数)
            0.234,  // 中位数
            0.289,  // Q3 (75分位数)
            0.456   // 最大值
        ],
        "downward": [
            // 结构同upward，但是下行波动率的箱线图数据
        ]
    },
    "distribution": {
        "upward": {
            "x": [...],        // x轴数据点（波动率值）
            "y": [...],        // y轴数据点（概率密度）
            "mean": 0.234,     // 平均值
            "std": 0.078,      // 标准差
            "ranges": {
                "1std": [0.156, 0.312],  // 一个标准差范围
                "2std": [0.078, 0.390]   // 两个标准差范围
            }
        },
        "downward": {
            // 结构同upward，但是下行波动率的分布图数据
        }
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
