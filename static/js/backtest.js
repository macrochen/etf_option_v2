$(document).ready(function() {
    // 初始化下拉选择器
    initializeDropdowns();
    
    // 实时策略类型检测
    initializeStrategyDetection();
    
    // 表单验证和提交
    initializeFormValidation();
});

// 初始化下拉选择器
function initializeDropdowns() {
    $('.dropdown-item').click(function(e) {
        e.preventDefault();
        const value = $(this).data('value');
        const input = $(this).closest('.input-group').find('input');
        input.val(value);
        validateDeltaInputs();
    });
}

// 实时策略类型检测
function initializeStrategyDetection() {
    const deltaInputs = ['put_sell_delta', 'put_buy_delta', 'call_sell_delta', 'call_buy_delta'];
    deltaInputs.forEach(id => {
        $(`#${id}`).on('input', function() {
            detectStrategy();
            validateDeltaInputs();
        });
    });
}

// 检测当前策略类型
function detectStrategy() {
    const putSellDelta = parseFloat($('#put_sell_delta').val());
    const putBuyDelta = parseFloat($('#put_buy_delta').val());
    const callSellDelta = parseFloat($('#call_sell_delta').val());
    const callBuyDelta = parseFloat($('#call_buy_delta').val());
    
    let strategyName = '';
    
    // 判断策略类型
    if (!isNaN(putSellDelta) && !isNaN(putBuyDelta) && isNaN(callSellDelta) && isNaN(callBuyDelta)) {
        strategyName = '牛市看跌策略 (Bull Put Spread)';
    } else if (isNaN(putSellDelta) && isNaN(putBuyDelta) && !isNaN(callSellDelta) && !isNaN(callBuyDelta)) {
        strategyName = '熊市看涨策略 (Bear Call Spread)';
    } else if (!isNaN(putSellDelta) && !isNaN(putBuyDelta) && !isNaN(callSellDelta) && !isNaN(callBuyDelta)) {
        strategyName = '铁鹰策略 (Iron Condor)';
    }
    
    const indicator = $('.strategy-type-indicator');
    if (strategyName) {
        indicator.removeClass('d-none').find('.strategy-name').text(strategyName);
    } else {
        indicator.addClass('d-none');
    }
}

// 验证Delta输入值
function validateDeltaInputs() {
    const putSellDelta = parseFloat($('#put_sell_delta').val());
    const putBuyDelta = parseFloat($('#put_buy_delta').val());
    const callSellDelta = parseFloat($('#call_sell_delta').val());
    const callBuyDelta = parseFloat($('#call_buy_delta').val());
    
    let isValid = true;
    let errorMessage = '';
    
    // 验证PUT策略
    if (!isNaN(putSellDelta) || !isNaN(putBuyDelta)) {
        if (isNaN(putSellDelta) || isNaN(putBuyDelta)) {
            errorMessage = 'PUT策略需要同时设置买入和卖出Delta';
            isValid = false;
        } else if (putSellDelta >= putBuyDelta) {
            errorMessage = 'PUT策略中，卖出Delta必须小于买入Delta';
            isValid = false;
        }
    }
    
    // 验证CALL策略
    if (!isNaN(callSellDelta) || !isNaN(callBuyDelta)) {
        if (isNaN(callSellDelta) || isNaN(callBuyDelta)) {
            errorMessage = 'CALL策略需要同时设置买入和卖出Delta';
            isValid = false;
        } else if (callSellDelta <= callBuyDelta) {
            errorMessage = 'CALL策略中，卖出Delta必须大于买入Delta';
            isValid = false;
        }
    }
    
    // 显示或清除错误信息
    if (!isValid) {
        showError(errorMessage);
    } else {
        clearError();
    }
    
    return isValid;
}

// 初始化表单验证
function initializeFormValidation() {
    $('#backtest-form').on('submit', function(e) {
        e.preventDefault();
        
        if (!validateDeltaInputs()) {
            return false;
        }
        
        // 验证日期
        const startDate = new Date($('#start_date').val());
        const endDate = new Date($('#end_date').val());
        
        if (startDate >= endDate) {
            showError('结束日期必须晚于开始日期');
            return false;
        }
        
        // 验证是否选择了至少一组完整的策略
        const putSellDelta = parseFloat($('#put_sell_delta').val());
        const putBuyDelta = parseFloat($('#put_buy_delta').val());
        const callSellDelta = parseFloat($('#call_sell_delta').val());
        const callBuyDelta = parseFloat($('#call_buy_delta').val());
        
        if ((isNaN(putSellDelta) || isNaN(putBuyDelta)) && 
            (isNaN(callSellDelta) || isNaN(callBuyDelta))) {
            showError('请至少设置一组完整的期权策略');
            return false;
        }
        
        // 提交表单
        submitBacktest();
    });
}

// 显示错误信息
function showError(message) {
    clearError();
    const alertHtml = `
        <div class="alert alert-danger alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    $('#error-container').html(alertHtml);
}

// 清除错误信息
function clearError() {
    $('#error-container').empty();
}

// 提交回测请求
function submitBacktest() {
    $('.loading').show();
    
    // 构建策略参数
    const strategy_params = {};
    const putSellDelta = parseFloat($('#put_sell_delta').val());
    const putBuyDelta = parseFloat($('#put_buy_delta').val());
    const callSellDelta = parseFloat($('#call_sell_delta').val());
    const callBuyDelta = parseFloat($('#call_buy_delta').val());
    
    // 只添加有效的参数
    if (!isNaN(putSellDelta)) strategy_params.put_sell_delta = putSellDelta;
    if (!isNaN(putBuyDelta)) strategy_params.put_buy_delta = putBuyDelta;
    if (!isNaN(callSellDelta)) strategy_params.call_sell_delta = callSellDelta;
    if (!isNaN(callBuyDelta)) strategy_params.call_buy_delta = callBuyDelta;
    
    // 构建请求数据，只包含有值的字段
    const formData = {
        etf_code: $('#etf_code').val(),
        strategy_params: strategy_params
    };

    // 只添加有值的日期字段
    const startDate = $('#start_date').val();
    const endDate = $('#end_date').val();
    if (startDate) formData.start_date = startDate;
    if (endDate) formData.end_date = endDate;
    
    console.log('发送回测请求:', formData);
    
    $.ajax({
        url: '/api/backtest',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(formData),
        success: function(response) {
            console.log('收到回测响应:', response);
            if (response.error) {
                showError(response.error);
                $('.loading').hide();
                return;
            }
            $('.loading').hide();
            try {
                displayResults(response);
            } catch (error) {
                console.error('显示结果时出错:', error);
                showError('显示回测结果时出错: ' + error.message);
            }
        },
        error: function(xhr, status, error) {
            $('.loading').hide();
            console.error('回测请求失败:', {xhr, status, error});
            const errorMessage = xhr.responseJSON?.error || error || '未知错误';
            showError('回测执行失败：' + errorMessage);
        }
    });
}

// 显示回测结果
function displayResults(response) {
    try {
        console.log('开始处理回测结果:', response);
        
        // 验证响应数据
        if (!response) {
            throw new Error('回测结果为空');
        }
        
        // 清除之前的结果
        $('#results-container').empty();
        
        // 创建结果展示区域
        const resultsHtml = `
            <div class="results-section mt-4">
                <h3>回测结果</h3>
                
                <!-- 策略收益对比表格 -->
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">策略表现对比</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-bordered">
                                <thead>
                                    <tr>
                                        <th>指标</th>
                                        <th>期权策略</th>
                                        <th>ETF买入持有</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${generateStrategyComparisonTable(response.strategy_comparison)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- 交易记录 -->
                ${response.trade_records ? `
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">交易记录</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover">
                                <thead>
                                    <tr>
                                        ${response.trade_records.headers ? response.trade_records.headers.map(header => `<th>${header}</th>`).join('') : ''}
                                    </tr>
                                </thead>
                                <tbody>
                                    ${generateTradeRecordsTable(response.trade_records.data)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                ` : ''}

                <!-- 每日盈亏 -->
                ${response.daily_pnl ? `
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0">每日盈亏</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-striped table-hover">
                                <thead>
                                    <tr>
                                        ${response.daily_pnl.headers ? response.daily_pnl.headers.map(header => `<th>${header}</th>`).join('') : ''}
                                    </tr>
                                </thead>
                                <tbody>
                                    ${generateDailyPnlTable(response.daily_pnl.data)}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                ` : ''}

                <!-- 图表展示 -->
                ${response.plots ? Object.keys(response.plots).map(plotName => {
                    const plotId = plotName.replace(/\s+/g, '_');
                    console.log('创建图表容器:', plotId);
                    return `
                    <div class="card mb-4">
                        <div class="card-header">
                            <h5 class="mb-0">${plotName}</h5>
                        </div>
                        <div class="card-body">
                            <div id="${plotId}" style="width:100%; height:400px;"></div>
                        </div>
                    </div>
                    `;
                }).join('') : ''}
            </div>
        `;
        
        // 显示结果
        $('#results-container').html(resultsHtml);

        // 渲染图表
        if (response.plots) {
            Object.entries(response.plots).forEach(([plotName, plotData]) => {
                try {
                    const plotId = plotName.replace(/\s+/g, '_');
                    console.log('渲染图表:', plotId);
                    const plotJson = JSON.parse(plotData);
                    Plotly.newPlot(plotId, plotJson.data, plotJson.layout);
                } catch (error) {
                    console.error('渲染图表失败:', {plotName, error, plotData});
                }
            });
        }
        
        console.log('回测结果显示完成');
    } catch (error) {
        console.error('显示回测结果时出错:', error);
        showError('显示回测结果时出错: ' + error.message);
        throw error;
    }
}

// 生成策略对比表格
function generateStrategyComparisonTable(comparisonData) {
    // 检查数据是否是数组
    if (Array.isArray(comparisonData)) {
        return comparisonData.map(row => `
            <tr>
                ${row.map(cell => `<td>${cell}</td>`).join('')}
            </tr>
        `).join('');
    }
    // 如果不是数组，检查是否有data属性
    if (comparisonData && comparisonData.data) {
        return comparisonData.data.map(row => `
            <tr>
                ${row.map(cell => `<td>${cell}</td>`).join('')}
            </tr>
        `).join('');
    }
    // 如果都不是，返回空字符串
    console.error('无效的对比数据格式:', comparisonData);
    return '';
}

// 生成交易记录表格
function generateTradeRecordsTable(tradeData) {
    if (!tradeData || !Array.isArray(tradeData)) {
        console.error('无效的交易记录数据:', tradeData);
        return '';
    }
    return tradeData.map(row => `
        <tr>
            ${row.map(cell => `<td>${cell}</td>`).join('')}
        </tr>
    `).join('');
}

// 生成每日盈亏表格
function generateDailyPnlTable(pnlData) {
    if (!pnlData || !Array.isArray(pnlData)) {
        console.error('无效的每日盈亏数据:', pnlData);
        return '';
    }
    return pnlData.map(row => `
        <tr>
            ${row.map(cell => `<td>${cell}</td>`).join('')}
        </tr>
    `).join('');
}

// 格式化金额
function formatMoney(amount) {
    return new Intl.NumberFormat('zh-CN', {
        style: 'currency',
        currency: 'CNY'
    }).format(amount);
} 