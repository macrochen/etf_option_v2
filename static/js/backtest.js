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
    let strategyType = '';
    
    // 判断策略类型
    if (putSellDelta === -0.5 && isNaN(putBuyDelta) && 
        callSellDelta === 0.5 && isNaN(callBuyDelta)) {
        // Wheel策略: PUT卖出Delta=-0.5，CALL卖出Delta=0.5
        strategyName = '轮转型期权策略 (Wheel Strategy)';
        strategyType = 'wheel';
    } else if (!isNaN(putSellDelta) && !isNaN(putBuyDelta) && 
        !isNaN(callSellDelta) && !isNaN(callBuyDelta)) {
        strategyName = '铁鹰策略 (Iron Condor)';
        strategyType = 'iron_condor';
    } else if (!isNaN(putSellDelta) && isNaN(putBuyDelta)) {
        strategyName = '单腿卖出看跌策略 (Naked Put)';
        strategyType = 'naked_put';
    } else if (!isNaN(putSellDelta) && !isNaN(putBuyDelta)) {
        strategyName = '牛市看跌策略 (Bull Put Spread)';
        strategyType = 'bullish_put';
    } else if (!isNaN(callSellDelta) && !isNaN(callBuyDelta)) {
        strategyName = '熊市看涨策略 (Bear Call Spread)';
        strategyType = 'bearish_call';
    }
    
    const indicator = $('.strategy-type-indicator');
    if (strategyName) {
        indicator.removeClass('d-none alert-danger').addClass('alert-info')
            .find('.strategy-name').text(strategyName);
    } else {
        indicator.addClass('d-none');
    }
    
    return strategyType;
}

// 验证Delta输入值
function validateDeltaInputs() {
    const putSellDelta = parseFloat($('#put_sell_delta').val());
    const putBuyDelta = parseFloat($('#put_buy_delta').val());
    const callSellDelta = parseFloat($('#call_sell_delta').val());
    const callBuyDelta = parseFloat($('#call_buy_delta').val());
    
    // 检测是否为Wheel策略
    if (putSellDelta === -0.5 && isNaN(putBuyDelta) && 
        callSellDelta === 0.5 && isNaN(callBuyDelta)) {
        return { isValid: true, errorMessage: '' };
    }
    
    let isValid = true;
    let errorMessage = '';

    // 根据策略类型进行验证
    const strategyType = detectStrategy();
    
    switch(strategyType) {
        case 'iron_condor':
            // 验证铁鹰策略
            const putValidation = validatePutLegs(putSellDelta, putBuyDelta);
            if (!putValidation.isValid) {
                return putValidation;
            }
            
            const callValidation = validateCallLegs(callSellDelta, callBuyDelta);
            if (!callValidation.isValid) {
                return callValidation;
            }
            break;
            
        case 'naked_put':
            // 验证单腿看跌策略
            if (!validatePutDelta(putSellDelta)) {
                return {
                    isValid: false,
                    errorMessage: '单腿PUT策略的Delta必须在-1到0之间'
                };
            }
            break;
            
        case 'bullish_put':
            // 验证牛市看跌策略
            return validatePutLegs(putSellDelta, putBuyDelta);
            
        case 'bearish_call':
            // 验证熊市看涨策略
            return validateCallLegs(callSellDelta, callBuyDelta);
    }
    
    return { isValid: true, errorMessage: '' };
}

// 验证PUT腿
function validatePutLegs(sellDelta, buyDelta) {
    // 验证Delta范围
    if (!validatePutDelta(sellDelta) || !validatePutDelta(buyDelta)) {
        return {
            isValid: false,
            errorMessage: 'PUT Delta值必须在-1到0之间'
        };
    }
    
    // 验证Delta关系
    if (sellDelta >= buyDelta) {
        return {
            isValid: false,
            errorMessage: 'PUT策略中，卖出Delta必须小于买入Delta'
        };
    }
    
    return { isValid: true, errorMessage: '' };
}

// 验证CALL腿
function validateCallLegs(sellDelta, buyDelta) {
    // 验证Delta范围
    if (!validateCallDelta(sellDelta) || !validateCallDelta(buyDelta)) {
        return {
            isValid: false,
            errorMessage: 'CALL Delta值必须在0到1之间'
        };
    }
    
    // 验证Delta关系
    if (sellDelta <= buyDelta) {
        return {
            isValid: false,
            errorMessage: 'CALL策略中，卖出Delta必须大于买入Delta'
        };
    }
    
    return { isValid: true, errorMessage: '' };
}

// 验证单个PUT Delta值
function validatePutDelta(delta) {
    return !isNaN(delta) && delta < 0 && delta > -1;
}

// 验证单个CALL Delta值
function validateCallDelta(delta) {
    return !isNaN(delta) && delta > 0 && delta < 1;
}

// 显示或清除错误信息
function updateValidationUI(validation) {
    if (!validation.isValid) {
        showError(validation.errorMessage);
        $('.strategy-type-indicator').removeClass('alert-info').addClass('alert-danger');
    } else {
        clearError();
        $('.strategy-type-indicator').removeClass('alert-danger').addClass('alert-info');
    }
}

// 初始化表单验证
function initializeFormValidation() {
    $('#backtest-form').on('submit', function(e) {
        e.preventDefault();
        
        // 显示加载动画
        $('.loading').show();
        $('#results').hide();
        
        // 获取方案保存相关参数
        const saveScheme = $('#saveScheme').is(':checked');
        const schemeName = saveScheme ? $('#schemeName').val() : null;
        
        const validation = validateDeltaInputs();
        updateValidationUI(validation);
        
        if (!validation.isValid) {
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
        if (isNaN(putSellDelta) && isNaN(callSellDelta)) {
            showError('请至少设置一个有效的期权策略');
            return false;
        }
        
        // 发送回测请求
        $.ajax({
            url: '/api/backtest',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                etf_code: $('#etf_code').val(),
                start_date: $('#start_date').val() || undefined,
                end_date: $('#end_date').val() || undefined,
                strategy_params: {
                    put_sell_delta: parseFloat($('#put_sell_delta').val()) || undefined,
                    put_buy_delta: parseFloat($('#put_buy_delta').val()) || undefined,
                    call_sell_delta: parseFloat($('#call_sell_delta').val()) || undefined,
                    call_buy_delta: parseFloat($('#call_buy_delta').val()) || undefined
                },
                save_scheme: saveScheme,
                scheme_name: schemeName
            }),
            success: function(response) {
                console.log('收到回测响应:', response);
                if (response.error) {
                    showError(response.error);
                    $('.loading').hide();
                    return;
                }
                // 如果保存方案成功，显示提示
                if (saveScheme && schemeName) {
                    showSuccess('方案保存成功！');
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
                console.error('Ajax request failed:', status, error);
                alert('回测执行失败，请重试');
            },
            complete: function() {
                // 隐藏加载动画
                $('.loading').hide();
            }
        });
    });
}

// 显示错误信息
function showError(message, error = null) {
    clearError();
    
    // 打印详细的错误堆栈
    if (error) {
        console.error('Error details:', {
            message: message,
            error: error,
            stack: error.stack,
            timestamp: new Date().toISOString()
        });
    }
    
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

// 将updateTable函数从index.html移到这里
function updateTable(tableId, data, allowHtml = false) {
    try {
        console.log(`Updating table ${tableId} with data:`, data);  // 调试日志
        const table = $(`#${tableId}`);
        const tbody = table.find('tbody');
        tbody.empty();
        
        // 如果数据为空，直接返回
        if (!data) {
            console.error(`No data provided for table ${tableId}`);
            return;
        }
        
        // 处理数据格式
        let tableData;
        if (data.data && Array.isArray(data.data)) {
            // 如果数据是{headers, data}格式
            tableData = data.data;
        } else if (Array.isArray(data)) {
            // 如果数据直接是数组
            tableData = data;
        } else {
            console.error(`Invalid data format for table ${tableId}:`, data);
            return;
        }
        
        // 生成表格行
        tableData.forEach(row => {
            if (!Array.isArray(row)) {
                console.error(`Invalid row data for table ${tableId}:`, row);
                return;
            }
            
            const tr = $('<tr>');
            row.forEach(cell => {
                const td = $('<td>');
                if (allowHtml) {
                    td.html(cell || '');
                } else {
                    td.text(cell || '');
                }
                tr.append(td);
            });
            tbody.append(tr);
        });
        
        console.log(`Table ${tableId} updated successfully`);  // 成功日志
    } catch (error) {
        console.error(`Error updating table ${tableId}:`, error);
    }
}

// 显示回测结果
function displayResults(response) {
    try {
        console.log('开始处理回测结果:', response);
        
        if (!response) {
            throw new Error('回测结果为空');
        }
        
        // 显示结果区域
        $('#results').show();
        
        // 更新表格数据
        if (response.strategy_comparison) {
            updateTable('strategy-comparison', response.strategy_comparison);
        }
        
        if (response.trade_summary) {
            updateTable('trade-summary', response.trade_summary);
        }
        
        if (response.trade_records) {
            updateTable('trade-records', response.trade_records);  // 直接传递整个对象
        }
        
        if (response.daily_pnl) {
            updateTable('daily-pnl', response.daily_pnl, true);  // 允许HTML内容
        }
        
        // 渲染图表
        if (response.plots) {
            if (response.plots.performance) {
                Plotly.newPlot('performance-plot', 
                    JSON.parse(response.plots.performance).data,
                    JSON.parse(response.plots.performance).layout
                );
            }
            
            if (response.plots.drawdown) {
                Plotly.newPlot('drawdown-plot',
                    JSON.parse(response.plots.drawdown).data,
                    JSON.parse(response.plots.drawdown).layout
                );
            }
            
            if (response.plots.pnl_distribution) {
                Plotly.newPlot('pnl-distribution-plot',
                    JSON.parse(response.plots.pnl_distribution).data,
                    JSON.parse(response.plots.pnl_distribution).layout
                );
            }
        }
        
        console.log('回测结果显示完成');
    } catch (error) {
        console.error('显示回测结果时出错:', {
            error: error,
            stack: error.stack,
            timestamp: new Date().toISOString(),
            responseData: response
        });
        showError('显示回测结果时出错: ' + error.message, error);
    }
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

// 添加快速设置Wheel策略的函数
function setupWheelStrategy() {
    // 清空所有Delta输入
    $('#put_buy_delta, #call_buy_delta').val('');
    
    // 设置卖出Delta
    $('#put_sell_delta').val(-0.5);
    $('#call_sell_delta').val(0.5);
    
    // 触发策略检测
    detectStrategy();
}

// 显示成功提示
function showSuccess(message) {
    const alertDiv = $('<div>')
        .addClass('alert alert-success alert-dismissible fade show')
        .attr('role', 'alert')
        .html(`
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `);
    
    $('#error-container').empty().append(alertDiv);
    
    // 3秒后自动消失
    setTimeout(() => {
        alertDiv.alert('close');
    }, 3000);
} 