$(document).ready(function() {
    // 等待DOM完全加载后再初始化图表
    let boxplotChart = null;
    let upwardVolatilityDistChart = null;
    let downwardVolatilityDistChart = null;

    function initCharts() {
        if (!boxplotChart && document.getElementById('volatility_boxplot')) {
            boxplotChart = echarts.init(document.getElementById('volatility_boxplot'));
        }
        if (!upwardVolatilityDistChart && document.getElementById('upward_volatility_dist')) {
            upwardVolatilityDistChart = echarts.init(document.getElementById('upward_volatility_dist'));
        }
        if (!downwardVolatilityDistChart && document.getElementById('downward_volatility_dist')) {
            downwardVolatilityDistChart = echarts.init(document.getElementById('downward_volatility_dist'));
        }
    }
    
    // ETF数据缓存
    let etfData = {
        volatilityStats: null,
        tradingRange: null
    };

    // 初始化事件处理
    // 使用 jQuery 的 off().on() 方法确保事件只绑定一次
    bindEvents();
    
    // 初始化图表并加载默认ETF数据
    initCharts();
    const defaultEtf = $('#etf_code').val();
    if (defaultEtf) {
        loadETFData(defaultEtf);
    }
    
    function bindEvents() {
        // ETF选择变更
        $('#etf_code').off('change').on('change', function() {
            loadETFData($(this).val());
        });

        // 波动率选择按钮点击事件
        ['sell_put', 'buy_put', 'sell_call', 'buy_call'].forEach(type => {
            $(`#${type}_vol_select`).off('click').on('click', function() {
                const stats = type.includes('call') ? 
                    etfData.volatilityStats.upward : 
                    etfData.volatilityStats.downward;
                    
                showVolatilitySelector(type, stats.percentiles);
            });
        });

        // 波动率选择和输入联动
        $('#put_volatility_select').off('change').on('change', function() {
            const stats = etfData.volatilityStats.downward;
            const value = $(this).val();
            if (value) {
                $('#put_volatility_input').val(stats.percentiles[value]);
            }
        });

        $('#call_volatility_select').off('change').on('change', function() {
            const stats = etfData.volatilityStats.upward;
            const value = $(this).val();
            if (value) {
                $('#call_volatility_input').val(stats.percentiles[value]);
            }
        });

        // 快捷日期选择
        $('.btn-group .btn').off('click').on('click', function() {
            if ($(this).prop('disabled')) return;
            
            const period = $(this).data('period');
            const endDate = new Date(etfData.tradingRange.end);
            const startDate = new Date(endDate);
            
            switch(period) {
                case '1M':
                    startDate.setMonth(startDate.getMonth() - 1);
                    break;
                case '3M':
                    startDate.setMonth(startDate.getMonth() - 3);
                    break;
                case '6M':
                    startDate.setMonth(startDate.getMonth() - 6);
                    break;
                case '1Y':
                    startDate.setMonth(startDate.getMonth() - 12);
                    break;
            }

            $('#start_date').val(startDate.toISOString().split('T')[0]);
            $('#end_date').val(endDate.toISOString().split('T')[0]);
        });

        // 回测按钮点击事件
        $('#run_backtest').off('click').on('click', function() {

            // 显示加载动画
            $('.loading').show();
            $('#results').hide();

            const strategy_params = {}
            
            // 只在有值时才添加参数
            const sell_put_vol = $('#sell_put_vol_input').val();
            const buy_put_vol = $('#buy_put_vol_input').val();
            const sell_call_vol = $('#sell_call_vol_input').val();
            const buy_call_vol = $('#buy_call_vol_input').val();

            if (sell_put_vol) {
                strategy_params.sell_put_volatility = parseFloat(sell_put_vol);
            }
            if (buy_put_vol) {
                strategy_params.buy_put_volatility = parseFloat(buy_put_vol);
            }
            if (sell_call_vol) {
                strategy_params.sell_call_volatility = parseFloat(sell_call_vol);
            }
            if (buy_call_vol) {
                strategy_params.buy_call_volatility = parseFloat(buy_call_vol);
            }

            const params = {
                etf_code: $('#etf_code').val(),
                strategy_params: strategy_params,
                start_date: $('#start_date').val(),
                end_date: $('#end_date').val(),
//                save_scheme: $('#save_scheme').is(':checked')
            };

            // 发送回测请求
            $.ajax({
                url: '/api/backtest/volatility',
                method: 'POST',
                data: JSON.stringify(params),
                contentType: 'application/json',
                success: function(response) {
                    if (response.error) {
                        showError(response.error);
                        return;
                    }

                    // 如果保存方案成功，显示提示
//                    if (saveScheme && schemeName) {
//                        showSuccess('方案保存成功！');
//                    }

                    // 处理回测结果
                    displayResults(response);
                },
                error: function(xhr) {
                    showError('请求失败: ' + xhr.statusText);
                },
                complete: function() {
                    $('.loading').hide();
                }
            });
        });

        // 方案管理
        $('#manage_scheme').off('click').on('click', function() {
            window.location.href = '/schemes';
        });
    }

    function loadETFData(etf_code) {
        $.get('/api/etf/volatility', { etf_code: etf_code }, function(data) {
            etfData.volatilityStats = data.volatility_stats;
            etfData.tradingRange = data.trading_range;
            
            // 更新日期范围
            updateDateRange();
            
            // 更新推荐参数
            updateRecommendedParams(data.volatility_stats);
            
            // 更新图表
            if (data.display_data) {
                updateVolatilityDisplay(data);
            }
        }).fail(function(xhr) {
            console.error('加载ETF数据失败：', xhr);
            alert('加载ETF数据失败：' + (xhr.responseJSON ? xhr.responseJSON.error : '未知错误'));
        });
    }

    function showVolatilitySelector(type, percentiles) {
        // 对百分位数进行排序
        percentiles.sort((a, b) => a - b);

        const selector = type === 'put' ? {
            sell: '#sell_put_vol_options',
            buy: '#buy_put_vol_options',
            sellInput: '#sell_put_vol_input',
            buyInput: '#buy_put_vol_input'
        } : {
            sell: '#sell_call_vol_options',
            buy: '#buy_call_vol_options',
            sellInput: '#sell_call_vol_input',
            buyInput: '#buy_call_vol_input'
        };

        // 清空并填充下拉选项
        $(selector.sell).empty();
        $(selector.buy).empty();

        // 清空输入框
        $(selector.sellInput).val('');
        $(selector.buyInput).val('');

        // 只添加25%、50%、75%分位数选项
        const percentileLabels = [0.25, 0.5, 0.75].map(p => {
            const index = Math.floor(p * (percentiles.length - 1));
            return {
                value: percentiles[index] * 100, // 转换为百分数
                label: `${(p * 100).toFixed(0)}分位: ${(percentiles[index] * 100).toFixed(1)}%`
            };
        });

        percentileLabels.forEach(item => {
            $(selector.sell).append(
                `<li><a class="dropdown-item" href="#" data-value="${item.value}">${item.label}</a></li>`
            );
            $(selector.buy).append(
                `<li><a class="dropdown-item" href="#" data-value="${item.value}">${item.label}</a></li>`
            );
        });

        // 绑定点击事件
        $(`${selector.sell} .dropdown-item`).off('click').on('click', function(e) {
            e.preventDefault();
            const value = $(this).data('value');
            $(selector.sellInput).val(value);
        });

        $(`${selector.buy} .dropdown-item`).off('click').on('click', function(e) {
            e.preventDefault();
            const value = $(this).data('value');
            $(selector.buyInput).val(value);
        });

        // 设置输入框验证
        const inputs = [selector.sellInput, selector.buyInput];
        inputs.forEach(inputSelector => {
            const $input = $(inputSelector);
            
            // 输入验证
            $input.off('input').on('input', function() {
                let value = parseFloat(this.value);
                if (isNaN(value)) {
                    this.value = '';
                } else {
                    // 限制在0-100之间
                    value = Math.max(0, Math.min(100, value));
                    this.value = value;
                }
            });
        });
    }

    function updateDateRange() {
        const range = etfData.tradingRange;
        if (range) {
            $('#start_date').val(range.start);
            $('#end_date').val(range.end);
        }
    }

    function updateRecommendedParams(statsData) {
        if (!statsData) return;
        
        // 格式化数字为百分比，保留1位小数
        const formatPercent = (value) => {
            if (isNaN(value)) return 'N/A';
            return (value * 100).toFixed(1) + '%';
        };
        
        $('#put_vol_range').html(`最小值: ${formatPercent(statsData.downward.min)}, 
                                平均值: ${formatPercent(statsData.downward.volatility)},
                                中位数: ${formatPercent(statsData.downward.percentiles['50'])}, 
                                最大值: ${formatPercent(statsData.downward.max)}`);
        
        $('#call_vol_range').html(`最小值: ${formatPercent(statsData.upward.min)}, 
                                 平均值: ${formatPercent(statsData.upward.volatility)},
                                 中位数: ${formatPercent(statsData.upward.percentiles['50'])}, 
                                 最大值: ${formatPercent(statsData.upward.max)}`);

        // 将对象格式的百分位数据转换为数组
        const downwardPercentiles = Object.values(statsData.downward.percentiles).map(Number);
        const upwardPercentiles = Object.values(statsData.upward.percentiles).map(Number);

        // 更新波动率选择器
        showVolatilitySelector('put', downwardPercentiles);
        showVolatilitySelector('call', upwardPercentiles);
    }

    function updateVolatilityDisplay(data) {
        if (!data || !data.volatility_stats || !data.display_data) return;

        // 更新波动率范围显示
        const statsData = data.volatility_stats;
        
        // 检查数据有效性
        const putRange = statsData.downward ? 
            `最小值: ${(statsData.downward.min * 100).toFixed(2)}%, 
             平均值: ${(statsData.downward.volatility * 100).toFixed(2)}%,
             中位数: ${(statsData.downward.percentiles[2] * 100).toFixed(2)}%, 
             最大值: ${(statsData.downward.max * 100).toFixed(2)}%` : 
            '暂无数据';
        
        const callRange = statsData.upward ? 
            `最小值: ${(statsData.upward.min * 100).toFixed(2)}%, 
             平均值: ${(statsData.upward.volatility * 100).toFixed(2)}%,
             中位数: ${(statsData.upward.percentiles[2] * 100).toFixed(2)}%, 
             最大值: ${(statsData.upward.max * 100).toFixed(2)}%` : 
            '暂无数据';

        $('#put_vol_range').html(putRange);
        $('#call_vol_range').html(callRange);

        const displayData = data.display_data;

        // 箱线图配置
        const boxPlotOption = {
            title: {
                text: '波动率分布箱线图',
                left: 'center'
            },
            tooltip: {
                trigger: 'item',
                formatter: function(params) {
                    // 如果是散点图（平均值标记）
                    if (params.seriesName === '平均值') {
                        return `平均值: ${(params.value * 100).toFixed(2)}%`;
                    }
                    
                    // 获取箱线图的原始数据
                    const values = params.data;
                    if (!Array.isArray(values)) return params.name;
                    
                    // ECharts会在data中添加额外的统计值，我们只使用后5个值
                    const [min, q1, median, q3, max] = values.slice(1, 6);
                    const mean = statsData[params.name === '下跌波动率' ? 'downward' : 'upward'].volatility;
                    
                    return `${params.name}<br/>
                            最大值: ${(max * 100).toFixed(2)}%<br/>
                            上四分位: ${(q3 * 100).toFixed(2)}%<br/>
                            <span style="color: #e6a23c">平均值: ${(mean * 100).toFixed(2)}%</span><br/>
                            中位数: ${(median * 100).toFixed(2)}%<br/>
                            下四分位: ${(q1 * 100).toFixed(2)}%<br/>
                            最小值: ${(min * 100).toFixed(2)}%`;
                }
            },
            grid: {
                left: '10%',
                right: '10%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                data: ['下跌波动率', '上涨波动率']
            },
            yAxis: {
                type: 'value',
                name: '波动率',
                axisLabel: {
                    formatter: value => (value * 100).toFixed(2) + '%'
                }
            },
            series: [{
                name: '波动率分布',
                type: 'boxplot',
                data: [
                    displayData.boxplot.downward,
                    displayData.boxplot.upward
                ],
                itemStyle: {
                    borderWidth: 2
                },
                boxWidth: ['40%', '40%']  // 控制箱线图的宽度
            },
            // 添加平均值标记
            {
                name: '平均值',
                type: 'scatter',
                data: [
                    {
                        value: statsData.downward.volatility,
                        xAxis: 0,
                        yAxis: statsData.downward.volatility
                    },
                    {
                        value: statsData.upward.volatility,
                        xAxis: 1,
                        yAxis: statsData.upward.volatility
                    }
                ],
                symbol: 'diamond',
                symbolSize: 10,
                itemStyle: {
                    color: '#e6a23c'
                }
            }]
        };

        // 正态分布图配置
        const normalDistOption = {
            title: {
                text: '波动率分布曲线',
                left: 'center'
            },
            tooltip: {
                trigger: 'axis',
                formatter: function(params) {
                    return params.map(param => {
                        if (param.data[1] === 0) return `${param.seriesName}: 暂无数据`;
                        return `${param.seriesName}<br/>波动率: ${(param.data[0] * 100).toFixed(2)}%<br/>概率密度: ${param.data[1].toFixed(4)}`;
                    }).join('<br/><br/>');
                }
            },
            legend: {
                data: ['下跌波动率', '上涨波动率'],
                top: 30
            },
            grid: {
                left: '10%',
                right: '10%',
                top: '15%',
                bottom: '15%',
                containLabel: true
            },
            xAxis: {
                type: 'value',
                name: '波动率',
                axisLabel: {
                    formatter: value => (value * 100).toFixed(2) + '%'
                },
                min: function(value) {
                    return value.min * 1.5; // 扩大50%的显示范围
                },
                max: function(value) {
                    return value.max * 1.5;
                }
            },
            yAxis: {
                type: 'value',
                name: '概率密度',
                splitLine: {
                    show: false
                }
            },
            series: [
                {
                    name: '下跌波动率',
                    type: 'line',
                    smooth: true,
                    z: 3,
                    data: displayData.distribution.downward.x.map((x, i) => [x, displayData.distribution.downward.y[i]]),
                    lineStyle: {
                        color: '#ff6b6b',
                        width: 2
                    },
                    itemStyle: {
                        color: '#ff6b6b'
                    },
                    areaStyle: {
                        opacity: 0.1,
                        color: '#ff6b6b'
                    },
                    markArea: {
                        silent: true,
                        data: [
                            [{
                                name: '一个标准差',
                                xAxis: displayData.distribution.downward.ranges['1std'][0],
                                itemStyle: {
                                    color: 'rgba(255, 107, 107, 0.1)'
                                }
                            }, {
                                xAxis: displayData.distribution.downward.ranges['1std'][1]
                            }],
                            [{
                                name: '两个标准差',
                                xAxis: displayData.distribution.downward.ranges['2std'][0],
                                itemStyle: {
                                    color: 'rgba(255, 107, 107, 0.05)'
                                }
                            }, {
                                xAxis: displayData.distribution.downward.ranges['2std'][1]
                            }]
                        ]
                    },
                    markLine: {
                        silent: true,
                        symbol: ['none', 'none'],
                        data: [
                            {
                                name: '均值',
                                xAxis: displayData.distribution.downward.mean,
                                lineStyle: {
                                    color: '#ff6b6b',
                                    width: 2
                                },
                                label: {
                                    formatter: (displayData.distribution.downward.mean * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            // 下跌标准差标记（底部）
                            {
                                name: '一个标准差',
                                xAxis: displayData.distribution.downward.ranges['1std'][0],
                                lineStyle: {
                                    color: '#ff6b6b',
                                    type: 'dashed'
                                },
                                label: {
                                    formatter: (displayData.distribution.downward.ranges['1std'][0] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            {
                                xAxis: displayData.distribution.downward.ranges['1std'][1],
                                lineStyle: {
                                    color: '#ff6b6b',
                                    type: 'dashed'
                                },
                                label: {
                                    formatter: (displayData.distribution.downward.ranges['1std'][1] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            {
                                name: '两个标准差',
                                xAxis: displayData.distribution.downward.ranges['2std'][0],
                                lineStyle: {
                                    color: '#ff6b6b',
                                    type: 'dotted'
                                },
                                label: {
                                    formatter: (displayData.distribution.downward.ranges['2std'][0] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            {
                                xAxis: displayData.distribution.downward.ranges['2std'][1],
                                lineStyle: {
                                    color: '#ff6b6b',
                                    type: 'dotted'
                                },
                                label: {
                                    formatter: (displayData.distribution.downward.ranges['2std'][1] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            }
                        ]
                    },
                    markArea: {
                        silent: true,
                        data: [
                            [{
                                name: '一个标准差',
                                xAxis: displayData.distribution.downward.ranges['1std'][0],
                                itemStyle: {
                                    color: 'rgba(255, 107, 107, 0.1)'
                                }
                            }, {
                                xAxis: displayData.distribution.downward.ranges['1std'][1]
                            }],
                            [{
                                name: '两个标准差',
                                xAxis: displayData.distribution.downward.ranges['2std'][0],
                                itemStyle: {
                                    color: 'rgba(255, 107, 107, 0.05)'
                                }
                            }, {
                                xAxis: displayData.distribution.downward.ranges['2std'][1]
                            }]
                        ]
                    }
                },
                {
                    name: '上涨波动率',
                    type: 'line',
                    smooth: true,
                    z: 3,
                    data: displayData.distribution.upward.x.map((x, i) => [x, displayData.distribution.upward.y[i]]),
                    lineStyle: {
                        color: '#4cd964',
                        width: 2
                    },
                    itemStyle: {
                        color: '#4cd964'
                    },
                    areaStyle: {
                        opacity: 0.1,
                        color: '#4cd964'
                    },
                    markArea: {
                        silent: true,
                        data: [
                            [{
                                name: '一个标准差',
                                xAxis: displayData.distribution.upward.ranges['1std'][0],
                                itemStyle: {
                                    color: 'rgba(76, 217, 100, 0.1)'
                                }
                            }, {
                                xAxis: displayData.distribution.upward.ranges['1std'][1]
                            }],
                            [{
                                name: '两个标准差',
                                xAxis: displayData.distribution.upward.ranges['2std'][0],
                                itemStyle: {
                                    color: 'rgba(76, 217, 100, 0.05)'
                                }
                            }, {
                                xAxis: displayData.distribution.upward.ranges['2std'][1]
                            }]
                        ]
                    },
                    markLine: {
                        silent: true,
                        symbol: ['none', 'none'],
                        data: [
                            {
                                name: '均值',
                                xAxis: displayData.distribution.upward.mean,
                                lineStyle: {
                                    color: '#4cd964',
                                    width: 2
                                },
                                label: {
                                    formatter: (displayData.distribution.upward.mean * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            // 上涨标准差标记（顶部）
                            {
                                name: '一个标准差',
                                xAxis: displayData.distribution.upward.ranges['1std'][0],
                                lineStyle: {
                                    color: '#4cd964',
                                    type: 'dashed'
                                },
                                label: {
                                    formatter: (displayData.distribution.upward.ranges['1std'][0] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            {
                                xAxis: displayData.distribution.upward.ranges['1std'][1],
                                lineStyle: {
                                    color: '#4cd964',
                                    type: 'dashed'
                                },
                                label: {
                                    formatter: (displayData.distribution.upward.ranges['1std'][1] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            {
                                name: '两个标准差',
                                xAxis: displayData.distribution.upward.ranges['2std'][0],
                                lineStyle: {
                                    color: '#4cd964',
                                    type: 'dotted'
                                },
                                label: {
                                    formatter: (displayData.distribution.upward.ranges['2std'][0] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            },
                            {
                                xAxis: displayData.distribution.upward.ranges['2std'][1],
                                lineStyle: {
                                    color: '#4cd964',
                                    type: 'dotted'
                                },
                                label: {
                                    formatter: (displayData.distribution.upward.ranges['2std'][1] * 100).toFixed(2) + '%',
                                    position: 'insideEndTop',
                                    fontSize: 10
                                }
                            }
                        ]
                    }
                }
            ]
        };

        // 创建上涨波动率分布图
        const upwardDistOption = {
            title: {
                text: '上涨波动率分布',
                left: 'center'
            },
            tooltip: {
                trigger: 'axis',
                formatter: function(params) {
                    return `波动率: ${(params[0].data[0] * 100).toFixed(2)}%<br/>概率密度: ${params[0].data[1].toFixed(4)}`;
                }
            },
            grid: {
                left: '10%',
                right: '10%',
                top: '15%',
                bottom: '15%',
                containLabel: true
            },
            xAxis: {
                type: 'value',
                name: '波动率',
                axisLabel: {
                    formatter: value => (value * 100).toFixed(2) + '%'
                }
            },
            yAxis: {
                type: 'value',
                name: '概率密度'
            },
            series: [{
                type: 'line',
                smooth: true,
                data: displayData.distribution.upward.x.map((x, i) => [x, displayData.distribution.upward.y[i]]),
                lineStyle: {
                    color: '#4cd964',
                    width: 2
                },
                itemStyle: {
                    color: '#4cd964'
                },
                areaStyle: {
                    opacity: 0.2,
                    color: '#4cd964'
                },
                markArea: {
                    silent: true,
                    data: [
                        [{
                            name: '一个标准差',
                            xAxis: displayData.distribution.upward.ranges['1std'][0],
                            itemStyle: {
                                color: 'rgba(76, 217, 100, 0.2)'
                            }
                        }, {
                            xAxis: displayData.distribution.upward.ranges['1std'][1]
                        }],
                        [{
                            name: '两个标准差',
                            xAxis: displayData.distribution.upward.ranges['2std'][0],
                            itemStyle: {
                                color: 'rgba(76, 217, 100, 0.1)'
                            }
                        }, {
                            xAxis: displayData.distribution.upward.ranges['2std'][1]
                        }]
                    ]
                },
                markLine: {
                    silent: true,
                    symbol: ['none', 'none'],
                    data: [
                        {
                            name: '均值',
                            xAxis: displayData.distribution.upward.mean,
                            lineStyle: {
                                color: '#4cd964',
                                width: 2
                            },
                            label: {
                                formatter: (displayData.distribution.upward.mean * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            name: '一个标准差',
                            xAxis: displayData.distribution.upward.ranges['1std'][0],
                            lineStyle: {
                                color: '#4cd964',
                                type: 'dashed'
                            },
                            label: {
                                formatter: (displayData.distribution.upward.ranges['1std'][0] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            xAxis: displayData.distribution.upward.ranges['1std'][1],
                            lineStyle: {
                                color: '#4cd964',
                                type: 'dashed'
                            },
                            label: {
                                formatter: (displayData.distribution.upward.ranges['1std'][1] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            name: '两个标准差',
                            xAxis: displayData.distribution.upward.ranges['2std'][0],
                            lineStyle: {
                                color: '#4cd964',
                                type: 'dotted'
                            },
                            label: {
                                formatter: (displayData.distribution.upward.ranges['2std'][0] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            xAxis: displayData.distribution.upward.ranges['2std'][1],
                            lineStyle: {
                                color: '#4cd964',
                                type: 'dotted'
                            },
                            label: {
                                formatter: (displayData.distribution.upward.ranges['2std'][1] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        }
                    ]
                }
            }]
        };

        // 创建下跌波动率分布图
        const downwardDistOption = {
            title: {
                text: '下跌波动率分布',
                left: 'center'
            },
            tooltip: {
                trigger: 'axis',
                formatter: function(params) {
                    return `波动率: ${(params[0].data[0] * 100).toFixed(2)}%<br/>概率密度: ${params[0].data[1].toFixed(4)}`;
                }
            },
            grid: {
                left: '10%',
                right: '10%',
                top: '15%',
                bottom: '15%',
                containLabel: true
            },
            xAxis: {
                type: 'value',
                name: '波动率',
                axisLabel: {
                    formatter: value => (value * 100).toFixed(2) + '%'
                }
            },
            yAxis: {
                type: 'value',
                name: '概率密度'
            },
            series: [{
                type: 'line',
                smooth: true,
                data: displayData.distribution.downward.x.map((x, i) => [x, displayData.distribution.downward.y[i]]),
                lineStyle: {
                    color: '#ff6b6b',
                    width: 2
                },
                itemStyle: {
                    color: '#ff6b6b'
                },
                areaStyle: {
                    opacity: 0.2,
                    color: '#ff6b6b'
                },
                markArea: {
                    silent: true,
                    data: [
                        [{
                            name: '一个标准差',
                            xAxis: displayData.distribution.downward.ranges['1std'][0],
                            itemStyle: {
                                color: 'rgba(255, 107, 107, 0.2)'
                            }
                        }, {
                            xAxis: displayData.distribution.downward.ranges['1std'][1]
                        }],
                        [{
                            name: '两个标准差',
                            xAxis: displayData.distribution.downward.ranges['2std'][0],
                            itemStyle: {
                                color: 'rgba(255, 107, 107, 0.1)'
                            }
                        }, {
                            xAxis: displayData.distribution.downward.ranges['2std'][1]
                        }]
                    ]
                },
                markLine: {
                    silent: true,
                    symbol: ['none', 'none'],
                    data: [
                        {
                            name: '均值',
                            xAxis: displayData.distribution.downward.mean,
                            lineStyle: {
                                color: '#ff6b6b',
                                width: 2
                            },
                            label: {
                                formatter: (displayData.distribution.downward.mean * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            name: '一个标准差',
                            xAxis: displayData.distribution.downward.ranges['1std'][0],
                            lineStyle: {
                                color: '#ff6b6b',
                                type: 'dashed'
                            },
                            label: {
                                formatter: (displayData.distribution.downward.ranges['1std'][0] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            xAxis: displayData.distribution.downward.ranges['1std'][1],
                            lineStyle: {
                                color: '#ff6b6b',
                                type: 'dashed'
                            },
                            label: {
                                formatter: (displayData.distribution.downward.ranges['1std'][1] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            name: '两个标准差',
                            xAxis: displayData.distribution.downward.ranges['2std'][0],
                            lineStyle: {
                                color: '#ff6b6b',
                                type: 'dotted'
                            },
                            label: {
                                formatter: (displayData.distribution.downward.ranges['2std'][0] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        },
                        {
                            xAxis: displayData.distribution.downward.ranges['2std'][1],
                            lineStyle: {
                                color: '#ff6b6b',
                                type: 'dotted'
                            },
                            label: {
                                formatter: (displayData.distribution.downward.ranges['2std'][1] * 100).toFixed(2) + '%',
                                position: 'insideEndTop',
                                fontSize: 10
                            }
                        }
                    ]
                }
            }]
        };

        // 设置图表选项
        boxplotChart.setOption(boxPlotOption);
        upwardVolatilityDistChart.setOption(upwardDistOption);
        downwardVolatilityDistChart.setOption(downwardDistOption);

        // 监听窗口大小变化，调整图表大小
        window.addEventListener('resize', function() {
            boxplotChart.resize();
            upwardVolatilityDistChart.resize();
            downwardVolatilityDistChart.resize();
        });
    }

    function updateTable(tableId, data, allowHtml = false) {
        try {
            const table = $(`#${tableId}`);
            if (!table.length) {
                throw new Error(`找不到表格: ${tableId}`);
            }
            
            // 清空表格内容
            table.find('tbody').empty();
            
            // 如果有表头数据，更新表头
            if (data.headers) {
                const headerRow = $('<tr>');
                data.headers.forEach(header => {
                    headerRow.append($('<th>').text(header));
                });
                table.find('thead').html(headerRow);
            }
            
            // 添加数据行
            if (data.data) {
                data.data.forEach(row => {
                    const tr = $('<tr>');
                    row.forEach(cell => {
                        if (allowHtml) {
                            tr.append($('<td>').html(cell));
                        } else {
                            tr.append($('<td>').text(cell));
                        }
                    });
                    table.find('tbody').append(tr);
                });
            } else if (Array.isArray(data)) {
                // 如果直接是数组，就直接添加
                data.forEach(row => {
                    const tr = $('<tr>');
                    row.forEach(cell => {
                        if (allowHtml) {
                            tr.append($('<td>').html(cell));
                        } else {
                            tr.append($('<td>').text(cell));
                        }
                    });
                    table.find('tbody').append(tr);
                });
            }
        } catch (error) {
            console.error('更新表格时出错:', {
                tableId: tableId,
                error: error,
                data: data
            });
            throw error;
        }
    }
});
