$(document).ready(function() {
    // 等待DOM完全加载后再初始化图表
    let boxplotChart = null;
    let upwardVolatilityDistChart = null;
    let downwardVolatilityDistChart = null;

    
    // ETF数据缓存
    let etfData = {
        volatilityStats: null,
        tradingRange: null
    };

    // 初始化事件处理
    // 使用 jQuery 的 off().on() 方法确保事件只绑定一次
    bindEvents();
    
    // 初始化图表并加载默认ETF数据
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

        // 绑定复选框事件
        $('#save_scheme').off('change').on('change', function() {
            if ($(this).is(':checked')) {
                const defaultSchemeName = generateSchemeName(); // 生成默认方案名称
                const userInput = prompt("请输入方案名称:", defaultSchemeName);
                if (userInput === null) {
                    $(this).prop('checked', false); // 用户取消，取消勾选
                    return;
                }

                // 检查当前方案名称是否已存在
                checkIfSchemeExists(userInput).then(response => {
                    if (response.status === 'exists') {
                        // 提示用户是否覆盖已有方案
                        if (confirm(`方案"${userInput}"已存在，是否覆盖原有的回测结果？`)) {
                            $('#schemeId').val(response.existing_scheme_id); // 保存方案 ID
                            $('#scheme_name').val(userInput); // 更新方案名称输入框
                            $('#schemeNameGroup').removeClass('d-none'); // 显示方案名称输入框
                        } else {
                            $('#save_scheme').prop('checked', false); // 用户选择不覆盖，取消勾选
                        }
                    } else {
                        $('#scheme_name').val(userInput); // 更新方案名称输入框
                        $('#schemeNameGroup').removeClass('d-none'); // 显示方案名称输入框
                    }
                });
            } else {
                $('#scheme_name').val(''); // 取消勾选时清空方案名称
                $('#schemeId').val(''); // 清空方案 ID
                $('#schemeNameGroup').addClass('d-none'); // 隐藏方案名称输入框
            }
        });

        // 回测按钮点击事件
        $('#run_backtest').off('click').on('click', function() {
            // 显示加载动画
            $('.loading').show();
            $('#results').hide();

            const strategy_params = {};
            // 获取波动率输入值
            const sell_put_vol = $('#sell_put_vol_input').val();
            const buy_put_vol = $('#buy_put_vol_input').val();
            const sell_call_vol = $('#sell_call_vol_input').val();
            const buy_call_vol = $('#buy_call_vol_input').val();

            if (sell_put_vol) {
                strategy_params.put_sell_volatility = parseFloat(sell_put_vol);
            }
            if (buy_put_vol) {
                strategy_params.put_buy_volatility = parseFloat(buy_put_vol);
            }
            if (sell_call_vol) {
                strategy_params.call_sell_volatility = parseFloat(sell_call_vol);
            }
            if (buy_call_vol) {
                strategy_params.call_buy_volatility = parseFloat(buy_call_vol);
            }

            const params = {
                etf_code: $('#etf_code').val(),
                strategy_params: strategy_params,
                start_date: $('#start_date').val(),
                end_date: $('#end_date').val(),
                save_scheme: $('#save_scheme').is(':checked'), // 获取保存方案标志
                scheme_name: $('#scheme_name').val(), // 获取方案名称
                scheme_id: $('#schemeId').val() // 获取方案 ID
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

        // 绑定查看波动率按钮事件
        $('#view_volatility').off('click').on('click', function() {
            const etfCode = $('#etf_code').val();
            if (!etfCode) {
                alert('请先选择一个ETF标的物');
                return;
            }

            // 加载波动率数据
            loadVolatilityData(etfCode);
        });
    }

    function loadETFData(etf_code) {
        $.get('/api/etf/volatility', { etf_code: etf_code ,data_range: '3个月'}, function(data) {
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
            const index = Math.floor(p * 4 - 1);
            return {
                value: Math.round(percentiles[index] * 1000) / 10, // 转换为百分数并四舍五入
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

        // 更新看跌波动率范围
        $('#put_vol_range').html(`最小值: ${formatPercent(statsData.down_volatility.min)}, 
                                平均值: ${formatPercent(statsData.down_volatility.volatility)},
                                中位数: ${formatPercent(statsData.down_volatility.percentiles['50'])}, 
                                最大值: ${formatPercent(statsData.down_volatility.max)}`);

        // 更新看涨波动率范围
        $('#call_vol_range').html(`最小值: ${formatPercent(statsData.up_volatility.min)}, 
                                 平均值: ${formatPercent(statsData.up_volatility.volatility)},
                                 中位数: ${formatPercent(statsData.up_volatility.percentiles['50'])}, 
                                 最大值: ${formatPercent(statsData.up_volatility.max)}`);

        // 将对象格式的百分位数据转换为数组
        const downwardPercentiles = Object.values(statsData.down_volatility.percentiles).map(Number);
        const upwardPercentiles = Object.values(statsData.up_volatility.percentiles).map(Number);

        // 更新波动率选择器
        showVolatilitySelector('put', downwardPercentiles);
        showVolatilitySelector('call', upwardPercentiles);
    }

    function updateVolatilityDisplay(data) {
        if (!data || !data.volatility_stats || !data.display_data) return;

        // 更新波动率范围显示
        const statsData = data.volatility_stats;

        // 检查数据有效性
        const putRange = statsData.down_volatility ? 
            `最小值: ${(statsData.down_volatility.min * 100).toFixed(2)}%, 
             平均值: ${(statsData.down_volatility.volatility * 100).toFixed(2)}%,
             中位数: ${(statsData.down_volatility.percentiles['50'] * 100).toFixed(2)}%, 
             最大值: ${(statsData.down_volatility.max * 100).toFixed(2)}%` : 
            '暂无数据';

        const callRange = statsData.up_volatility ? 
            `最小值: ${(statsData.up_volatility.min * 100).toFixed(2)}%, 
             平均值: ${(statsData.up_volatility.volatility * 100).toFixed(2)}%,
             中位数: ${(statsData.up_volatility.percentiles['50'] * 100).toFixed(2)}%, 
             最大值: ${(statsData.up_volatility.max * 100).toFixed(2)}%` : 
            '暂无数据';

        $('#put_vol_range').html(putRange);
        $('#call_vol_range').html(callRange);
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

    function generateSchemeName() {
        const etfCode = $('#etf_code').val() || '';
        const sellPutVol = $('#sell_put_vol_input').val() || '';
        const buyPutVol = $('#buy_put_vol_input').val() || '';
        const sellCallVol = $('#sell_call_vol_input').val() || '';
        const buyCallVol = $('#buy_call_vol_input').val() || '';
        const startDate = $('#start_date').val() || '';
        const endDate = $('#end_date').val() || '';

        return `${etfCode}_${sellPutVol}_${buyPutVol}_${sellCallVol}_${buyCallVol}_${startDate}_${endDate}_波动率回测`;
    }

    // 检查方案名称是否已存在
    function checkIfSchemeExists(schemeName) {
        return new Promise((resolve, reject) => {
            $.ajax({
                url: '/api/schemes/check_exists', // 假设的 API 路径
                method: 'POST',
                data: JSON.stringify({ name: schemeName }),
                contentType: 'application/json',
                success: function(response) {
                    resolve(response); // 确保解析为响应
                },
                error: function(err) {
                    reject(err); // 处理错误
                }
            });
        });
    }

    function loadVolatilityData(etfCode) {

        const periodOrder = ['3个月', '6个月', '1年', '3年', '5年', '10年'];
        $.get('/api/etf/volatility', { etf_code: etfCode }, function(data) {
            if (data.error) {
                $('#volatilityContent').html(data.error);
            } else {

                // 绘制箱线图
                const chartDom = document.getElementById('volatilityChart');
                const myChart = echarts.init(chartDom);
                const option = {
                    title: {
                        text: `${etfCode} 波动率数据`,
                        left: 'center',
                        top: 'top',
                        textStyle: {
                            fontSize: 18,
                            fontWeight: 'bold'
                        }
                    },
                    tooltip: {},
                    legend: {
                        data: ['月上涨波动率', '月下跌波动率', '周上涨波动率', '周下跌波动率'],
                        orient: 'horizontal',
                        left: 'center',
                        top: 'bottom'
                    },
                    xAxis: {
                        type: 'category',
                        data: periodOrder // 根据需要调整
                    },
                    yAxis: {
                        type: 'value',
                        axisLabel: {
                            formatter: '{value}%' // 将 y 轴标签格式化为百分数
                        }
                    },
                    series: [
                        {
                            name: '月上涨波动率',
                            type: 'boxplot',
                            data: periodOrder.map(period => {
                                const stats = data[period];
                                if (!stats) return [0, 0, 0, 0, 0]; // 如果 stats 为空，返回默认值
                                return [
                                    stats.up_volatility.min * 100,                // 最小值
                                    stats.up_volatility.percentiles['25'] * 100,  // 25%分位数
                                    stats.up_volatility.percentiles['50'] * 100,  // 50%分位数
                                    stats.up_volatility.percentiles['75'] * 100,  // 75%分位数
                                    stats.up_volatility.max * 100                 // 最大值
                                ].map(value => value.toFixed(2)); // 保留两位小数
                            })
                        },
                        {
                            name: '月下跌波动率',
                            type: 'boxplot',
                            data: periodOrder.map(period => {
                                const stats = data[period];
                                if (!stats) return [0, 0, 0, 0, 0]; // 如果 stats 为空，返回默认值
                                return [
                                    stats.down_volatility.min * 100,                // 最小值
                                    stats.down_volatility.percentiles['25'] * 100,  // 25%分位数
                                    stats.down_volatility.percentiles['50'] * 100,  // 50%分位数
                                    stats.down_volatility.percentiles['75'] * 100,  // 75%分位数
                                    stats.down_volatility.max * 100                 // 最大值
                                ].map(value => value.toFixed(2)); // 保留两位小数
                            })
                        }
                        // 可以添加周上涨和周下跌波动率的系列
                    ]
                };
                myChart.setOption(option);
            }
        }).fail(function(xhr) {
            $('#volatilityContent').html('加载波动率数据失败：' + xhr.statusText);
        }).always(function() {
            // 显示模态窗口
            $('#volatilityModal').modal('show');
        });
    }
});
