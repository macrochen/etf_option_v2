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
    
    const formData = {
        etf_code: $('#etf_code').val(),
        start_date: $('#start_date').val(),
        end_date: $('#end_date').val(),
        strategy: {
            put_sell_delta: parseFloat($('#put_sell_delta').val()) || null,
            put_buy_delta: parseFloat($('#put_buy_delta').val()) || null,
            call_sell_delta: parseFloat($('#call_sell_delta').val()) || null,
            call_buy_delta: parseFloat($('#call_buy_delta').val()) || null
        }
    };
    
    $.ajax({
        url: '/api/backtest',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(formData),
        success: function(response) {
            $('.loading').hide();
            displayResults(response);
        },
        error: function(xhr) {
            $('.loading').hide();
            showError('回测执行失败：' + (xhr.responseJSON?.message || '未知错误'));
        }
    });
} 