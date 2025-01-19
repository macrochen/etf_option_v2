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


function initializeFormValidation() {
    $('#backtest-form').on('submit', function(e) {
        e.preventDefault();
        
        // 清除之前的错误信息
        clearError();
        
        // 显示加载动画
        $('.loading').show();
        $('#results').hide();
        
        // 获取方案保存相关参数
        const saveScheme = $('#saveScheme').is(':checked');
        const schemeId = $('#schemeId').val(); // 获取方案 ID
        const schemeName = saveScheme ? $('#schemeName').val() : null;
        
        // 验证方案名称
        if (saveScheme && !schemeName) {
            showError('请输入方案名称');
            $('.loading').hide();
            return false;
        }
        
        // 构建请求数据
        const requestData = {
            etf_code: $('#etf_code').val(),
            start_date: $('#start_date').val() || undefined,
            end_date: $('#end_date').val() || undefined,
            strategy_params: {
                put_sell_delta: parseFloat($('#put_sell_delta').val()) || undefined,
                put_buy_delta: parseFloat($('#put_buy_delta').val()) || undefined,
                call_sell_delta: parseFloat($('#call_sell_delta').val()) || undefined,
                call_buy_delta: parseFloat($('#call_buy_delta').val()) || undefined
            },
            save_scheme: saveScheme,  // 添加保存方案标志
            scheme_name: schemeName,   // 添加方案名称
            scheme_id: schemeId        // 添加方案 ID
        };
        
        // 发送回测请求
        $.ajax({
            url: '/api/backtest',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(requestData),
            success: function(response) {
                if (response.error) {
                    showError(response.error);
                    return;
                }
                
                // 如果保存方案成功，显示提示
                if (saveScheme && schemeName) {
                    showSuccess('方案保存成功！');
                }
                
                // 处理回测结果
                displayResults(response);
            },
            error: function(xhr) {
                // 显示后端返回的错误信息
                const errorMessage = xhr.responseJSON ? xhr.responseJSON.message : '请求失败: ' + xhr.statusText;
                showError(errorMessage);
            },
            complete: function() {
                $('.loading').hide();
            }
        });
    });
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

// 添加快速设置Iron Condor策略的函数
function setupIronCondorStrategy() {
    
    // 设置卖出和买入Delta
    $('#put_sell_delta').val(-0.5);
    $('#put_buy_delta').val(-0.2);
    $('#call_sell_delta').val(0.5);
    $('#call_buy_delta').val(0.2);
    
    // 触发策略检测（如果需要）
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


// 获取完整的方案参数
function getSchemeParams() {
    // 获取所有 delta 值
    const deltaInputs = ['put_sell_delta', 'put_buy_delta', 'call_sell_delta', 'call_buy_delta'];
    const strategyParams = {};
    const deltaList = [];
    
    deltaInputs.forEach(id => {
        const value = parseFloat($(`#${id}`).val());
        if (!isNaN(value)) {
            strategyParams[id] = value;
            deltaList.push(value);
        }
    });

    return {
        etf_code: $('#etf_code').val(),
        start_date: $('#start_date').val(),
        end_date: $('#end_date').val(),
        delta_list: deltaList,
        strategy_params: strategyParams
    };
}

// 获取 Delta 列表
function getDeltaList() {
    const deltaInputs = ['put_sell_delta', 'put_buy_delta', 'call_sell_delta', 'call_buy_delta'];
    const deltas = [];
    
    deltaInputs.forEach(id => {
        const value = parseFloat($(`#${id}`).val());
        if (!isNaN(value)) {
            deltas.push(value);
        }
    });
    
    return deltas;  // 返回数组格式
}

// 生成默认方案名称
function generateDefaultSchemeName() {
    const etfCode = $('#etf_code').val() || '';
    const deltaList = getDeltaList();
    const startDate = $('#start_date').val()?.replace(/-/g, '') || '';
    const endDate = $('#end_date').val()?.replace(/-/g, '') || '';
    
    let name = etfCode || '方案';
    if (deltaList.length > 0) {
        name += `_${deltaList.join(',')}`;
    }
    if (startDate) {
        name += `_${startDate}`;
    }
    if (endDate) {
        name += `_${endDate}`;
    }
    
    return name;
}

// 在保存方案的逻辑中
$('#saveScheme').off('change').on('change', function() {
    const saveScheme = $(this).is(':checked');

    if (saveScheme) {
        // 生成默认方案名称
        const schemeName = generateDefaultSchemeName(); // 生成默认方案名称

        // 显示输入弹窗
        const userInput = prompt("请输入方案名称:", schemeName);
        if (userInput === null) {
            $(this).prop('checked', false); // 用户取消，取消勾选
            return;
        }

        // 检查当前方案名称是否已存在
        checkIfSchemeExists(userInput).then(response => {
            if (response.status === 'exists') {
                // 提示用户是否覆盖已有方案
                if (confirm(`方案"${userInput}"已存在，是否覆盖原有的回测结果？`)) {
                    // 保存方案 ID 以便在执行回测时使用
                    $('#schemeId').val(response.existing_scheme_id); // 假设在 HTML 中有一个隐藏的输入框
                    $('#schemeName').val(userInput); // 更新输入框
                } else {
                    $(this).prop('checked', false); // 用户选择不覆盖，取消勾选
                }
            } else {
                $('#schemeName').val(userInput); // 更新输入框
            }
        });
    }
});

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

// 修改 fillBacktestForm 函数
function fillBacktestForm(params) {
    // 基础参数填充
    $('#etf_code').val(params.etf_code || '');
    $('#start_date').val(params.start_date || '');
    $('#end_date').val(params.end_date || '');
    
    // 清空所有 Delta 输入框
    ['put_sell_delta', 'put_buy_delta', 'call_sell_delta', 'call_buy_delta'].forEach(id => {
        $(`#${id}`).val('');
    });
    
    // 优先使用 delta_list
    if (params.delta_list) {
        const deltaInputs = ['put_sell_delta', 'put_buy_delta', 'call_sell_delta', 'call_buy_delta'];
        const deltaValues = Array.isArray(params.delta_list) ? 
            params.delta_list : 
            JSON.parse(JSON.stringify(params.delta_list));
            
        deltaValues.forEach((delta, index) => {
            if (index < deltaInputs.length && delta !== null && !isNaN(delta)) {
                $(`#${deltaInputs[index]}`).val(delta);
            }
        });
    }
    // 如果没有 delta_list 但有 strategy_params，则使用 strategy_params
    else if (params.strategy_params) {
        Object.entries(params.strategy_params).forEach(([key, value]) => {
            if (value !== null && !isNaN(value)) {
                $(`#${key}`).val(value);
            }
        });
    }
    
    // 触发策略检测
    detectStrategy();
} 