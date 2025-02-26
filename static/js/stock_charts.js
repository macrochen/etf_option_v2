// 全局变量
const periodOrder = ['3个月', '6个月', '1年', '3年', '5年', '10年'];
let currentChart = null;  // 存储当前图表实例

// 图表清理函数
function clearChart() {
    if (currentChart) {
        currentChart.dispose();
        currentChart = null;
    }
}

// 显示价格区间
function showPriceRange(stockCode, marketType, button) {
    // 获取当前行的价格输入框
    const priceCell = button.parentElement.parentElement.querySelector('td:nth-child(4)');
    const priceInput = priceCell.querySelector('input');
    
    let currentPrice = null;
    if (priceInput) {
        currentPrice = parseFloat(priceInput.value);
    }

    // 构建URL，添加currentPrice参数
    const url = `/api/price_range/${stockCode}?market_type=${marketType}${currentPrice ? `&current_price=${currentPrice}` : ''}`;

    // 显示加载动画
    document.getElementById('loading').style.display = 'flex';
    
    fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error("网络响应不正常");
            }
            return response.json();
        })
        .then(data => {
            clearChart();  // 清理旧图表
            const chartDom = document.getElementById('volatilityChart');
            currentChart = echarts.init(chartDom);
            
            const option = {
                title: {
                    text: `${stockCode} 价格走势`,
                    left: 'center'
                },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: {
                        type: 'line',
                        axis: 'y',     // 改为y轴方向
                        animation: false
                    },
                    formatter: function(params) {
                        const price = params[0].axisValue.toFixed(2);
                        let result = `价格: ${price}<br/>`;
                        // 只显示收盘价数据
                        const closePriceData = params.find(param => param.seriesName === '收盘价');
                        if (closePriceData && closePriceData.value !== '-') {
                            result += `${closePriceData.marker}${closePriceData.name}: ${typeof closePriceData.value === 'number' ? closePriceData.value.toFixed(2) : closePriceData.value}<br/>`;
                        }
                        return result;
                    }
                },
                legend: {
                    orient: 'vertical',      // 改为垂直布局
                    right: 10,              // 放在右侧
                    top: 'middle',          // 垂直居中
                    textStyle: {
                        fontSize: 12        // 调小字体
                    },
                    itemWidth: 25,          // 图例标记的宽度
                    itemHeight: 14,         // 图例标记的高度
                    itemGap: 10,            // 图例项之间的间隔
                },
                grid: {
                    left: '3%',
                    right: '15%',           // 增加右侧空间，为图例留出位置
                    bottom: '20%',
                    containLabel: true
                },
                dataZoom: [
                    {
                        type: 'slider',        // 滑动条型缩放组件
                        show: true,
                        xAxisIndex: [0],
                        bottom: '3%',          // 距离底部的距离
                        height: 20,            // 滑动条高度
                        start: 50,             // 默认显示最后50%的数据
                        end: 100
                    },
                    {
                        type: 'inside',        // 内置型缩放组件，允许鼠标滚轮缩放
                        xAxisIndex: [0],
                        start: 50,
                        end: 100
                    }
                ],
                xAxis: {
                    type: 'category',
                    data: data.dates,
                    boundaryGap: false
                },
                yAxis: {
                    type: 'value',
                    scale: true,
                    splitLine: {
                        show: true
                    }
                },
                series: [
                    {
                        name: '收盘价',
                        type: 'line',
                        data: data.closes,
                        symbol: 'none',
                        lineStyle: {
                            width: 1
                        }
                    },
                    {
                        name: '最新价格',
                        type: 'line',
                        data: new Array(data.dates.length).fill(data.latest_price.toFixed(2)),
                        symbol: 'none',
                        lineStyle: {
                            type: 'dashed',
                            width: 1,
                            color: '#000000'
                        }
                    }
                ]
            };

            // 如果有价格水平线数据，添加到图表中
            if (data.price_levels) {
                const periods = ['3个月', '6个月', '1年', '3年'];
                const colors = {
                    '3个月': { up: '#ff0000', down: '#00ff00' },
                    '6个月': { up: '#ff3333', down: '#33ff33' },
                    '1年': { up: '#ff6666', down: '#66ff66' },
                    '3年': { up: '#ff9999', down: '#99ff99' }
                };

                const priceLevels = [];

                // 先添加财报上涨波动（如果有）
                if (data.price_levels.earnings_max_up) {
                    priceLevels.push({
                        name: '财报最大上涨',
                        value: data.price_levels.earnings_max_up,
                        color: '#ff7777'
                    });
                    priceLevels.push({
                        name: '财报90分位上涨',
                        value: data.price_levels.earnings_p90_up,
                        color: '#ff7777'
                    });
                }

                // 添加月度上涨波动
                periods.forEach(period => {
                    priceLevels.push({
                        name: `月度90分位上涨(${period})`,
                        value: data.price_levels[`monthly_p90_up_${period}`],
                        color: colors[period].up,
                        opacity: 0.7
                    });
                });

                // 添加最新价格线
                priceLevels.push({
                    name: '最新价格',
                    value: data.latest_price,
                    color: '#000000',
                    type: 'dashed'
                });

                // 添加月度下跌波动
                periods.forEach(period => {
                    priceLevels.push({
                        name: `月度90分位下跌(${period})`,
                        value: data.price_levels[`monthly_p90_down_${period}`],
                        color: colors[period].down,
                        opacity: 0.7
                    });
                });

                // 最后添加财报下跌波动（如果有）
                if (data.price_levels.earnings_max_up) {
                    priceLevels.push({
                        name: '财报90分位下跌',
                        value: data.price_levels.earnings_p90_down,
                        color: '#77ff77'
                    });
                    priceLevels.push({
                        name: '财报最大下跌',
                        value: data.price_levels.earnings_max_down,
                        color: '#77ff77'
                    });
                }

                // 更新图表配置
                option.series = [
                    {
                        name: '收盘价',
                        type: 'line',
                        data: data.closes,
                        symbol: 'none',
                        lineStyle: {
                            width: 1
                        }
                    },
                    ...priceLevels.map(level => ({
                        name: level.name,
                        type: 'line',
                        data: new Array(data.dates.length).fill(level.value),
                        symbol: 'none',
                        lineStyle: {
                            type: level.type || 'dashed',
                            width: 1,
                            color: level.color,
                            opacity: level.opacity || 1
                        }
                    }))
                ];

                // 更新图例配置，确保顺序一致
                option.legend.data = ['收盘价', ...priceLevels.map(level => level.name)];
            }

            currentChart.setOption(option);
            $('#volatilityModal').modal('show');
        })
        .catch(error => {
            console.error("获取价格区间数据时出错:", error);
            alert("获取价格区间数据失败");
        })
        .finally(() => {
            // 隐藏加载动画
            document.getElementById('loading').style.display = 'none';
        });
}

// 显示波动率
function showVolatility(stockCode, marketType, currentPrice, windowDays) {
    fetch(`/api/volatility/${stockCode}?window_days=${windowDays}&market_type=${marketType}`)
        .then(response => {
            if (!response.ok) {
                throw new Error("网络响应不正常");
            }
            return response.json();
        })
        .then(data => {
            clearChart();  // 清理旧图表
            const chartDom = document.getElementById('volatilityChart');
            currentChart = echarts.init(chartDom);
            
            // 过滤有效的数据系列
            const validSeries = [];
            
            // 检查月度数据
            if (data.monthly_stats) {
                // 月上涨波动率
                const monthlyUpData = periodOrder.map(period => {
                    const stats = data.monthly_stats[period];
                    return stats ? [
                        stats.up_volatility.min * 100,
                        stats.up_volatility.percentiles['25'] * 100,
                        stats.up_volatility.percentiles['50'] * 100,
                        stats.up_volatility.percentiles['75'] * 100,
                        stats.up_volatility.percentiles['90'] * 100,
                        stats.up_volatility.max * 100
                    ].map(value => value.toFixed(2)) : null;
                }).filter(item => item !== null);
                
                if (monthlyUpData.length > 0) {
                    validSeries.push({
                        name: '月上涨波动率',
                        type: 'boxplot',
                        data: monthlyUpData
                    });
                }
                
                // 月下跌波动率
                const monthlyDownData = periodOrder.map(period => {
                    const stats = data.monthly_stats[period];
                    return stats ? [
                        stats.down_volatility.min * 100,
                        stats.down_volatility.percentiles['25'] * 100,
                        stats.down_volatility.percentiles['50'] * 100,
                        stats.down_volatility.percentiles['75'] * 100,
                        stats.down_volatility.percentiles['90'] * 100,
                        stats.down_volatility.max * 100
                    ].map(value => value.toFixed(2)) : null;
                }).filter(item => item !== null);
                
                if (monthlyDownData.length > 0) {
                    validSeries.push({
                        name: '月下跌波动率',
                        type: 'boxplot',
                        data: monthlyDownData
                    });
                }
            }
            
            // 检查周度数据
            if (data.weekly_stats) {
                // 周上涨波动率
                const weeklyUpData = periodOrder.map(period => {
                    const stats = data.weekly_stats[period];
                    return stats ? [
                        stats.up_volatility.min * 100,
                        stats.up_volatility.percentiles['25'] * 100,
                        stats.up_volatility.percentiles['50'] * 100,
                        stats.up_volatility.percentiles['75'] * 100,
                        stats.up_volatility.percentiles['90'] * 100,
                        stats.up_volatility.max * 100
                    ].map(value => value.toFixed(2)) : null;
                }).filter(item => item !== null);
                
                if (weeklyUpData.length > 0) {
                    validSeries.push({
                        name: '周上涨波动率',
                        type: 'boxplot',
                        data: weeklyUpData
                    });
                }
                
                // 周下跌波动率
                const weeklyDownData = periodOrder.map(period => {
                    const stats = data.weekly_stats[period];
                    return stats ? [
                        stats.down_volatility.min * 100,
                        stats.down_volatility.percentiles['25'] * 100,
                        stats.down_volatility.percentiles['50'] * 100,
                        stats.down_volatility.percentiles['75'] * 100,
                        stats.down_volatility.percentiles['90'] * 100,
                        stats.down_volatility.max * 100
                    ].map(value => value.toFixed(2)) : null;
                }).filter(item => item !== null);
                
                if (weeklyDownData.length > 0) {
                    validSeries.push({
                        name: '周下跌波动率',
                        type: 'boxplot',
                        data: weeklyDownData
                    });
                }
            }
            
            const option = {
                title: {
                    text: `${stockCode} 波动率数据 (当前价格: ${currentPrice.toFixed(2)})`,
                    left: 'center',
                    top: 'top',
                    textStyle: {
                        fontSize: 18,
                        fontWeight: 'bold'
                    }
                },
                tooltip: {
                    trigger: 'item',
                    formatter: function(params) {
                        // 只显示当前箱线图的数据
                        if (params.seriesType === 'boxplot') {
                            const isUp = params.seriesName.includes('上涨');
                            const calcPrice = (percent) => {
                                const factor = isUp ? (1 + percent/100) : (1 - percent/100);
                                return (currentPrice * factor).toFixed(2);
                            };
                            
                            return `${params.seriesName} - ${params.name}<br/>
                                    最大值: ${params.data[6]}% (${calcPrice(params.data[6])})<br/>
                                    90分位: ${params.data[5]}% (${calcPrice(params.data[5])})<br/>
                                    上四分位: ${params.data[4]}% (${calcPrice(params.data[4])})<br/>
                                    中位数: ${params.data[3]}% (${calcPrice(params.data[3])})<br/>
                                    下四分位: ${params.data[2]}% (${calcPrice(params.data[2])})<br/>
                                    最小值: ${params.data[1]}% (${calcPrice(params.data[1])})`;
                        }
                        return '';
                    }
                },
                legend: {
                    data: validSeries.map(series => series.name),
                    orient: 'horizontal',
                    left: 'center',
                    top: 'bottom'
                },
                xAxis: {
                    type: 'category',
                    data: periodOrder
                },
                grid: {
                    left: '2%',  // 增加左边距，为新增的Y轴留出空间
                    right: '2%',
                    top: '10%',
                    bottom: '10%',
                    containLabel: true
                },
                yAxis: [
                    {
                        type: 'value',
                        name: '上涨波动率',
                        position: 'left',
                        nameLocation: 'middle',
                        nameGap: 95,
                        axisLabel: {
                            formatter: function(value) {
                                const price = currentPrice * (1 + value/100);
                                return `${value}% (${price.toFixed(2)})`;
                            }
                        },
                        min: 0,
                        max: function(value) {
                            return Math.ceil(Math.max(...validSeries.flatMap(s => 
                                s.data.map(d => Math.max(...d.map(Number)))
                            )) / 10) * 10;
                        },
                        interval: 2
                    },
                    {
                        type: 'value',
                        name: '下跌波动率',
                        position: 'right',
                        nameLocation: 'middle',
                        nameGap: 95,
                        axisLabel: {
                            formatter: function(value) {
                                const price = currentPrice * (1 - value/100);
                                return `${value}% (${price.toFixed(2)})`;
                            }
                        },
                        min: 0,
                        max: function(value) {
                            return Math.ceil(Math.max(...validSeries.flatMap(s => 
                                s.data.map(d => Math.max(...d.map(Number)))
                            )) / 10) * 10;
                        },
                        interval: 2
                    }
                ],
                series: validSeries.map(series => ({
                    ...series,
                    yAxisIndex: 0  // 所有系列都使用左侧Y轴
                }))
            };
            
            currentChart.setOption(option);
            $('#volatilityModal').modal('show');
        })
        .catch(error => {
            console.error("获取波动率数据时出错:", error);
        });
}

function getCurrentPrice(stockCode, marketType, buttonElement) {
    // 显示加载状态
    buttonElement.disabled = true;
    buttonElement.textContent = '加载中...';

    fetch(`/api/current_price/${stockCode}?market_type=${marketType}`)
        .then(response => response.json())
        .then(data => {
            // 创建只读输入框
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'form-control form-control-sm';
            input.value = data.current_price.toFixed(2);
            input.readOnly = true;
            input.style.width = '100px';
            input.style.display = 'inline-block';
            
            // 替换按钮为输入框
            buttonElement.parentNode.replaceChild(input, buttonElement);
        })
        .catch(error => {
            console.error('获取价格失败:', error);
            // 创建可编辑的输入框
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'form-control form-control-sm';
            input.style.width = '100px';
            input.style.display = 'inline-block';
            input.placeholder = '请输入价格';
            
            // 添加数字输入验证
            input.addEventListener('input', function() {
                const value = this.value;
                if (value && !/^\d*\.?\d*$/.test(value)) {
                    this.value = value.replace(/[^\d.]/g, '');
                }
            });
            
            // 替换按钮为输入框
            buttonElement.parentNode.replaceChild(input, buttonElement);
        });
}

// 显示财报波动分析
function showEarningsVolatility(stockCode, marketType, button) {
    // 获取当前行的价格输入框
    const priceCell = button.parentElement.parentElement.querySelector('td:nth-child(4)');
    const priceInput = priceCell.querySelector('input');
    
    let currentPrice = null;
    if (priceInput) {
        currentPrice = parseFloat(priceInput.value);
    }
    
    // 获取财报波动数据
    fetch(`/api/earnings_volatility/${stockCode}?market_type=${marketType}`)
        .then(response => {
            if (!response.ok) {
                throw new Error("网络响应不正常");
            }
            return response.json();
        })
        .then(data => {
            clearChart();  // 清理旧图表
            const chartDom = document.getElementById('volatilityChart');
            currentChart = echarts.init(chartDom);
            
            
            // 处理财报波动数据统计
            const upStats = {
                count: data.up_stats.count,
                avg: data.up_stats.avg_volatility,  // 已经是百分比，不需要 * 100
                max: data.up_stats.max_volatility,
                min: data.up_stats.min_volatility,
                p90: data.up_stats.percentiles['90'],
                p75: data.up_stats.percentiles['75'],
                p50: data.up_stats.percentiles['50'],
                p25: data.up_stats.percentiles['25'],
                p10: data.up_stats.percentiles['10']
            };

            const downStats = {
                count: data.down_stats.count,
                avg: data.down_stats.avg_volatility,  // 已经是百分比，不需要 * 100
                max: data.down_stats.max_volatility,
                min: data.down_stats.min_volatility,
                p90: data.down_stats.percentiles['90'],
                p75: data.down_stats.percentiles['75'],
                p50: data.down_stats.percentiles['50'],
                p25: data.down_stats.percentiles['25'],
                p10: data.down_stats.percentiles['10']
            };

            const option = {
                title: {
                    text: `${stockCode} 历史财报波动统计分析${currentPrice ? ` (当前价格: ${currentPrice.toFixed(2)})` : ''}`,
                    subtext: `上涨样本: ${upStats.count} / 下跌样本: ${downStats.count}`,
                    left: 'center',
                    top: 10
                },
                tooltip: {
                    trigger: 'item',
                    formatter: function(params) {
                        const stats = params.seriesName.includes('上涨') ? upStats : downStats;
                        const isUp = params.seriesName.includes('上涨');
                        const calcPrice = (percent) => {
                            if (!currentPrice) return '';
                            const factor = isUp ? (1 + percent/100) : (1 - percent/100);
                            return ` (${(currentPrice * factor).toFixed(2)})`;
                        };
                        
                        return `${params.seriesName}<br/>
                            <hr style="margin: 5px 0">
                            90分位: ${stats.p90.toFixed(2)}%${calcPrice(stats.p90)}<br/>
                            75分位: ${stats.p75.toFixed(2)}%${calcPrice(stats.p75)}<br/>
                            中位数: ${stats.p50.toFixed(2)}%${calcPrice(stats.p50)}<br/>
                            25分位: ${stats.p25.toFixed(2)}%${calcPrice(stats.p25)}<br/>
                            10分位: ${stats.p10.toFixed(2)}%${calcPrice(stats.p10)}<br/>
                            <hr style="margin: 5px 0">
                            最大值: ${stats.max.toFixed(2)}%${calcPrice(stats.max)}<br/>
                            平均值: ${stats.avg.toFixed(2)}%${calcPrice(stats.avg)}<br/>
                            最小值: ${stats.min.toFixed(2)}%${calcPrice(stats.min)}<br/>
                            样本数: ${stats.count}`;
                    }
                },
                grid: {
                    left: '10%',
                    right: '10%',
                    top: '15%',
                    bottom: '10%'
                },
                xAxis: {
                    type: 'category',
                    data: ['上涨波动', '下跌波动']
                },
                yAxis: [
                    {
                        type: 'value',
                        name: '上涨波动率',
                        position: 'left',
                        nameLocation: 'middle',
                        nameGap: 95,
                        axisLabel: {
                            formatter: function(value) {
                                const price = currentPrice ? currentPrice * (1 + value/100) : value;
                                return currentPrice ? `${value}% (${price.toFixed(2)})` : `${value}%`;
                            }
                        },
                        min: 0,
                        max: function(value) {
                            return Math.ceil(Math.max(upStats.max, upStats.p90) / 5) * 5;
                        }
                    },
                    {
                        type: 'value',
                        name: '下跌波动率',
                        position: 'right',
                        nameLocation: 'middle',
                        nameGap: 95,
                        axisLabel: {
                            formatter: function(value) {
                                const price = currentPrice ? currentPrice * (1 - value/100) : value;
                                return currentPrice ? `${value}% (${price.toFixed(2)})` : `${value}%`;
                            }
                        },
                        min: 0,
                        max: function(value) {
                            return Math.ceil(Math.max(downStats.max, downStats.p90) / 5) * 5;
                        }
                    }
                ],
                series: [
                    {
                        name: '上涨波动',
                        type: 'boxplot',
                        data: [[
                            upStats.min,
                            upStats.p25,
                            upStats.p50,
                            upStats.p75,
                            upStats.p90,
                            upStats.max
                        ], []],
                        itemStyle: {
                            color: '#c23531',
                            borderColor: '#c23531'
                        },
                        yAxisIndex: 0  // 使用左侧Y轴
                    },
                    {
                        name: '上涨分位点',
                        type: 'scatter',
                        data: [
                            ['上涨波动', upStats.p90],
                            ['上涨波动', upStats.p10]
                        ],
                        itemStyle: {
                            color: '#c23531'
                        },
                        yAxisIndex: 0  // 使用左侧Y轴
                    },
                    {
                        name: '下跌波动',
                        type: 'boxplot',
                        data: [[], [
                            downStats.min,
                            downStats.p25,
                            downStats.p50,
                            downStats.p75,
                            downStats.p90,
                            downStats.max
                        ]],
                        itemStyle: {
                            color: '#2f4554',
                            borderColor: '#2f4554'
                        },
                        yAxisIndex: 1  // 使用右侧Y轴
                    },
                    {
                        name: '下跌分位点',
                        type: 'scatter',
                        data: [
                            ['下跌波动', downStats.p90],
                            ['下跌波动', downStats.p10]
                        ],
                        itemStyle: {
                            color: '#2f4554'
                        },
                        yAxisIndex: 1  // 使用右侧Y轴
                    }
                ]
            };
            
            currentChart.setOption(option);
            $('#volatilityModal').modal('show');
        })
        .catch(error => {
            console.error("获取财报波动数据时出错:", error);
            alert("获取财报波动数据失败");
        });
}