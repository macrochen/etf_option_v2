$(document).ready(function() {
    let priceChart = null;
    let scoreChart = null;
    let currentATR = null;  // 添加全局变量存储当前ATR值

    function handleAjaxError(xhr, status, error) {
        console.error('Ajax Error:', {
            status: status,
            error: error,
            response: xhr.responseText
        });
        alert('操作失败：' + (xhr.responseJSON?.error || '未知错误'));
    }


    // 加载ETF列表
    function loadEtfList(selectedCode = '') {
        $.get('/api/grid_trade/etf_list', function(data) {
            const $select = $('#etf-select');
            $select.empty().append('<option value="">-- 选择ETF --</option>');
            data.forEach(etf => {
                const option = `<option value="${etf.code}" 
                    data-start="${etf.start_date}" 
                    data-end="${etf.end_date}">
                    ${etf.code} - ${etf.name} 
                </option>`;
                $select.append(option);
            });
            
            if (selectedCode) {
                $select.val(selectedCode);
                // 更新数据范围显示
                const $selected = $select.find('option:selected');
                const startDate = $selected.data('start');
                const endDate = $selected.data('end');
                
                if (startDate && endDate) {
                    $('#date-range-info').removeClass('d-none')
                        .text(`数据范围: ${startDate} ~ ${endDate}`);
                } else {
                    $('#date-range-info').addClass('d-none');
                }
            }
        });
    }

    // 添加ETF选择变化事件处理
    $('#etf-select').on('change', function() {
        const etfCode = $(this).val();
        $('#etf-code-input').val(etfCode); // 将选中的ETF代码填充到输入框

        const $selected = $(this).find('option:selected');
        const startDate = $selected.data('start');
        const endDate = $selected.data('end');
        
        if (startDate && endDate) {
            $('#date-range-info').removeClass('d-none')
                .text(`数据范围: ${startDate} ~ ${endDate}`);
        } else {
            $('#date-range-info').addClass('d-none');
        }
    });

    // 加载ETF数据按钮
    $('#load-etf-btn').on('click', function() {
        const code = $('#etf-code-input').val().trim();
        
        if (!code) {
            alert('请输入ETF代码');
            return;
        }
        
        $('#loading-status').removeClass('d-none');
        
        $.ajax({
            url: '/api/grid_trade/load_etf',
            method: 'POST',
            data: JSON.stringify({ etf_code: code }),
            contentType: 'application/json',
            success: function(response) {
                loadEtfList(code);  // 传入当前代码，使其被选中
                $('#etf-code-input').val('');  // 清空输入框
            },
            error: function(xhr) {
                alert('加载失败：' + (xhr.responseJSON?.error || '未知错误'));
            },
            complete: function() {
                $('#loading-status').addClass('d-none');
            }
        });
    });


    // 初始化图表
    function initCharts() {
        // 确保元素存在后再初始化
        const priceChartElement = document.getElementById('price-chart');
        const scoreChartElement = document.getElementById('score-chart');

        if (priceChartElement) {
            priceChart = echarts.init(priceChartElement);
        }
        if (scoreChartElement) {
            scoreChart = echarts.init(scoreChartElement);
        }

        // 监听窗口大小变化
        $(window).on('resize', function() {
            priceChart?.resize();
            scoreChart?.resize();
        });
    }

    // 表单提交处理
    $('#grid-trade-form').on('submit', function(e) {
        e.preventDefault();
        
        const formData = {
            etf_code: $('#etf-select').val(),
            months: $('input[name="period-type"]:checked').val() || '12',
            initial_amount: parseFloat($('#initial-capital').val() || 100000)
        };

        // 发送分析请求
        $.ajax({
            url: '/api/grid_trade/analyze',
            method: 'POST',
            contentType: 'application/json',
            dataType: 'json',  // 添加这行
            data: JSON.stringify(formData),
            success: function(response) {
                console.log('Success:', response);  // 添加调试日志
                updateCharts(response);
                updateResults(response);
            },
            error: function(xhr, status, error) {  // 添加更详细的错误信息
                console.log('Error:', {
                    status: status,
                    error: error,
                    response: xhr.responseText
                });
                alert('分析失败：' + xhr.responseJSON?.error || '未知错误');
            }
        });
    });



    // 更新图表
    function updateCharts(data) {
        // 更新评分雷达图
        const scoreOption = {
            title: {
                text: '网格交易适应性评分',
                left: 'center',
                top: 0,
                padding: [0, 0, 20, 0]  // 增加底部内边距
            },
            radar: {
                center: ['50%', '60%'],  // 将雷达图向下移动
                radius: '60%',           // 适当调整雷达图大小
                indicator: [
                    { name: '波动性', max: 100 },
                    { name: '趋势性', max: 100 },
                    { name: '震荡性', max: 100 },
                    { name: '安全性', max: 100 }
                ]
            },
            series: [{
                type: 'radar',
                data: [{
                    value: [
                        data.scores.volatility_score,
                        data.scores.trend_score,
                        data.scores.oscillation_score,
                        data.scores.safety_score
                    ],
                    name: '评分',
                    areaStyle: {
                        color: 'rgba(0, 128, 255, 0.3)'
                    }
                }]
            }]
        };
        scoreChart.setOption(scoreOption);
    }

    // 更新分析结果
    function updateResults(data) {
        // 保存ATR值供后续使用
        currentATR = data.atr;
        // 创建结果HTML
        const resultHtml = `
            <div class="alert ${data.suitable ? 'alert-success' : 'alert-warning'} mb-3">
                <h4 class="alert-heading">${data.suitable ? '适合网格交易' : '不建议网格交易'}</h4>
                <p>${data.reason}</p>
                <hr>
                <div class="row">
                    <div class="col-md-3">
                        <strong>波动性评分：</strong> ${data.scores.volatility_score}
                        <button class="btn btn-link btn-sm p-0 ms-2" type="button" data-bs-toggle="collapse" 
                                data-bs-target="#volatilityDesc" aria-expanded="false">
                            <i class="bi bi-info-circle"></i>
                        </button>
                    </div>
                    <div class="col-md-3">
                        <strong>趋势性评分：</strong> ${data.scores.trend_score}
                        <button class="btn btn-link btn-sm p-0 ms-2" type="button" data-bs-toggle="collapse" 
                                data-bs-target="#trendDesc" aria-expanded="false">
                            <i class="bi bi-info-circle"></i>
                        </button>
                    </div>
                    <div class="col-md-3">
                        <strong>震荡性评分：</strong> ${data.scores.oscillation_score}
                        <button class="btn btn-link btn-sm p-0 ms-2" type="button" data-bs-toggle="collapse" 
                                data-bs-target="#oscillationDesc" aria-expanded="false">
                            <i class="bi bi-info-circle"></i>
                        </button>
                    </div>
                    <div class="col-md-3">
                        <strong>安全性评分：</strong> ${data.scores.safety_score}
                        <button class="btn btn-link btn-sm p-0 ms-2" type="button" data-bs-toggle="collapse" 
                                data-bs-target="#safetyDesc" aria-expanded="false">
                            <i class="bi bi-info-circle"></i>
                        </button>
                    </div>
                </div>
                
                <!-- 折叠说明区域 -->
                <div class="row mt-3">
                    <div class="col-12">
                        <div class="collapse" id="volatilityDesc">
                            <div class="card card-body">
                                <h6>波动性评分</h6>
                                <p>衡量ETF的价格波动幅度。适中的波动率（20%-50%）最适合网格交易，过高或过低的波动率都不利于网格策略的执行。得分越高表示波动率越适中。</p>
                            </div>
                        </div>
                        <div class="collapse" id="trendDesc">
                            <div class="card card-body">
                                <h6>趋势性评分</h6>
                                <p>基于<span class="text-primary" data-bs-toggle="tooltip" data-bs-placement="top" 
                                title="平均趋向指标(ADX)：用来衡量价格走势的强弱程度。通过计算上升动量与下降动量的差异来判断趋势强度，计算过程包括：1)计算上升动量(今日最高价与昨日最高价之差)和下降动量(昨日最低价与今日最低价之差)；2)取两者中较大值作为主导动量；3)对动量值进行平滑处理得出最终指标。数值越大表示趋势越强，数值越小表示震荡越明显。">ADX</span>指标评估价格趋势的强度。较弱的趋势（ADX < 25）更适合网格交易，因为强趋势可能导致单向持续上涨或下跌。得分越高表示趋势越弱，越适合网格交易。</p>
                            </div>
                        </div>
                        <div class="collapse" id="oscillationDesc">
                            <div class="card card-body">
                                <h6>震荡性评分</h6>
                                <p>根据布林带评估价格的震荡特性。价格在布林带内震荡的时间比例越高，越适合网格交易。理想的震荡比例应在60%-90%之间。得分越高表示震荡特性越好。</p>
                            </div>
                        </div>
                        <div class="collapse" id="safetyDesc">
                            <div class="card card-body">
                                <h6>安全性评分</h6>
                                <p>基于<span class="text-primary" data-bs-toggle="tooltip" data-bs-placement="top" title="真实波动幅度(ATR)：反映市场波动的剧烈程度，计算当日价格波动与前一日收盘价的差异。数值越大表示波动越剧烈，风险越高。">ATR</span>与价格的比值评估交易风险。较低的ATR/价格比值表示相对安全，有利于网格交易的稳定执行。得分越高表示风险越小。</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // 更新结果区域
        $('#analysis-result').html(resultHtml);
        
        // 初始化所有tooltip
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    // 初始化事件监听
    function initializeEventListeners() {
        // 监听网格参数变化
        $('#grid-count, #initial-capital').on('change', updateGridPreview);
        
        // 监听回测按钮点击
        $('#start-analyze-btn').on('click', startAnalyze);

        // 初始化 Manual Backtest Modal
        const manualBacktestModal = new bootstrap.Modal(document.getElementById('manualBacktestModal'));

        // 显示手动回测 Modal
        $('#manual-backtest-btn').on('click', function() {
            const etfCode = $('#etf-select').val() || $('#etf-code-input').val();
            if (!etfCode) {
                alert('请先选择或输入 ETF 代码');
                return;
            }
            $('#manual-etf-code').val(etfCode);
            
            // 尝试从 localStorage 加载上次的设置
            const savedStartDate = localStorage.getItem('manual_start_date');
            const savedBasePrice = localStorage.getItem('manual_base_price');
            const savedTradeSize = localStorage.getItem('manual_trade_size');
            const savedGridPercent = localStorage.getItem('manual_grid_percent');
            const savedGridCount = localStorage.getItem('manual_grid_count');
            const savedInitialCapital = localStorage.getItem('manual_initial_capital');

            if (savedStartDate) {
                $('#manual-start-date').val(savedStartDate);
            } else {
                // 如果没有保存的日期，默认设置为 1 年前
                const today = new Date();
                const lastYear = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
                // 格式化为 YYYY-MM-DD
                const year = lastYear.getFullYear();
                const month = String(lastYear.getMonth() + 1).padStart(2, '0');
                const day = String(lastYear.getDate()).padStart(2, '0');
                $('#manual-start-date').val(`${year}-${month}-${day}`);
            }

            if (savedBasePrice) $('#manual-base-price').val(savedBasePrice);
            if (savedTradeSize) $('#manual-trade-size').val(savedTradeSize);
            if (savedGridPercent) $('#manual-grid-percent').val(savedGridPercent);
            if (savedGridCount) $('#manual-grid-count').val(savedGridCount);
            if (savedInitialCapital) $('#manual-initial-capital').val(savedInitialCapital);
            
            manualBacktestModal.show();
        });

        // 执行手动回测
        $('#run-manual-backtest-btn').on('click', function() {
            const etfCode = $('#manual-etf-code').val();
            const startDate = $('#manual-start-date').val();
            const basePrice = $('#manual-base-price').val();
            const tradeSize = $('#manual-trade-size').val();
            const gridPercent = $('#manual-grid-percent').val();
            const gridCount = $('#manual-grid-count').val();
            const initialCapital = $('#manual-initial-capital').val();
            
            if (!startDate || !gridPercent || !gridCount || !initialCapital) {
                alert('请填写所有必填字段');
                return;
            }

            // 保存设置到 localStorage
            localStorage.setItem('manual_start_date', startDate);
            localStorage.setItem('manual_base_price', basePrice);
            localStorage.setItem('manual_trade_size', tradeSize);
            localStorage.setItem('manual_grid_percent', gridPercent);
            localStorage.setItem('manual_grid_count', gridCount);
            localStorage.setItem('manual_initial_capital', initialCapital);

            // 显示遮罩层
            $('body').append(`
                <div class="analysis-overlay">
                    <div class="loading-content">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <h5 class="mt-3">正在执行回测，请稍候...</h5>
                    </div>
                </div>
            `);
            
            manualBacktestModal.hide();

            $.ajax({
                url: '/api/grid_trade/manual_backtest',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    etf_code: etfCode,
                    start_date: startDate,
                    initial_base_price: basePrice,
                    trade_size: tradeSize,
                    grid_percent: gridPercent,
                    grid_count: gridCount,
                    initial_capital: initialCapital
                }),
                success: function(result) {
                    // 隐藏参数优化结果区域，避免混淆
                    $('#optimization-result-section').addClass('d-none');
                    
                    showBacktestResult(result);
                    
                    // 滚动到回测结果区域
                    document.getElementById('backtest-result-section').scrollIntoView({ behavior: 'smooth' });
                },
                error: handleAjaxError,
                complete: function() {
                    $('.analysis-overlay').remove();
                }
            });
        });
    }

    // 更新网格预览
    function updateGridPreview() {
        const etfCode = $('#etf-select').val() || $('#etf-code-input').val();
        const periodType = $('input[name="period-type"]:checked').val();
        const gridCount = $('#grid-count').val();
        const initialCapital = $('#initial-capital').val();
        
        if (!etfCode || !periodType) return;
        
        $.get('/api/grid_trade/calculate_range', {
            etf_code: etfCode,
            period_type: periodType,
            grid_count: gridCount,
            initial_capital: initialCapital
        })
        .done(function(response) {
            $('#grid-upper-preview').text(response.upper.toFixed(3));
            $('#grid-lower-preview').text(response.lower.toFixed(3));
            $('#grid-amount-preview').text(response.grid_amount.toFixed(2));
            $('#start-backtest-btn').prop('disabled', false);
        })
        .fail(handleAjaxError);
    }

    // 添加遮罩层样式到页面头部
    $('head').append(`
        <style>
            .analysis-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 9999;
            }
            .analysis-overlay .loading-content {
                background: white;
                padding: 2rem;
                border-radius: 8px;
                text-align: center;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                min-width: 200px;
            }
            .analysis-overlay h5 {
                margin-top: 1rem;
                margin-bottom: 0;
                color: #333;
                font-size: 1.1rem;
            }
            .analysis-overlay .spinner-border {
                width: 3rem;
                height: 3rem;
            }
        </style>
    `);

    // 开始参数分析
    function startAnalyze() {
        const etfCode = $('#etf-select').val() || $('#etf-code-input').val();
        const months = $('input[name="period-type"]:checked').val();
        
        // 隐藏之前的分析结果
        $('#optimization-result-section').addClass('d-none');
        $('#backtest-result-section').addClass('d-none');
        
        // 显示遮罩层
        $('body').append(`
            <div class="analysis-overlay">
                <div class="loading-content">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <h5 class="mt-3">正在分析中，请稍候...</h5>
                </div>
            </div>
        `);
        
        // 显示加载状态
        const $btn = $('#start-analyze-btn');
        const originalText = $btn.text();
        
        $.ajax({
            url: '/api/grid_trade/analyze_params',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                etf_code: etfCode,
                months: months,
                atr: currentATR
            })
        })
        .done(function(result) {
            console.log('Backtest result:', result);
            displayAnalyzeResult(result);
        })
        .fail(function(xhr, status, error) {
            console.error('Backtest error:', {
                status: status,
                error: error,
                response: xhr.responseText
            });
            handleAjaxError(xhr, status, error);
        })
        .always(function() {
            // 移除遮罩层
            $('.analysis-overlay').remove();
        });
    }

    // 显示分析结果
    function displayAnalyzeResult(result) {
        // 显示参数优化结果区域
        $('#optimization-result-section').removeClass('d-none');
        
        // 更新参数组合表格
        updateParamsTable(result);
        
        // 默认显示得分最高的回测结果
        showBacktestResult(result);
    }

    // 更新参数组合表格
    function updateParamsTable(result) {
        params = result.parameter_results
        const tbody = $('#params-table tbody');
        tbody.empty();
        
        // 添加标的持有结果行
        const benchmark = result.benchmark;  // 使用第一组参数的标的数据
        tbody.append(`
            <tr class="table-info">
                <td colspan="3">标的持有</td>
                <td>${(benchmark.annual_return * 100).toFixed(2)}%</td>
                <td>${(benchmark.total_return * 100).toFixed(2)}%</td>
                <td>${benchmark.sharpe_ratio.toFixed(2)}</td>
                <td>${(benchmark.max_drawdown * 100).toFixed(2)}%</td>
                <td>1</td>
                <td>100%</td>
                <td>1.00</td>
                <td>${(benchmark.total_score * 100).toFixed(2)}</td>
                <td>-</td>
            </tr>
            <tr><td colspan="9" class="border-bottom"></td></tr>
        `);
        
        // 添加网格策略结果
        params.forEach((param, index) => {
            // 获取网格间距百分比
            const gridPercent = param.params.grid_percent || 
            (param.best_backtest && param.best_backtest.grids[0].grid_percent) || 0;

            
            tbody.append(`
                <tr>
                    <td>${index + 1}</td>
                    <td>${param.params.grid_count}</td>
                    <td>${gridPercent.toFixed(2)}%</td>
                    <td>${(param.metrics.annual_return * 100).toFixed(2)}%</td>
                    <td>${(param.metrics.total_return * 100).toFixed(2)}%</td>
                    <td>${param.metrics.sharpe_ratio.toFixed(2)}</td>
                    <td>${(param.metrics.max_drawdown * 100).toFixed(2)}%</td>
                    <td>${param.metrics.trade_count}</td>
                    <td>${(param.metrics.capital_utilization * 100).toFixed(2)}%</td>
                    <td>${param.metrics.relative_return.toFixed(2)}</td>
                    <td>${(param.metrics.score * 100).toFixed(2)}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary run-backtest-btn"
                                data-grid-count="${param.params.grid_count}"
                                data-atr-factor="${param.params.atr_factor}"
                                data-grid-percent="${gridPercent}">
                            执行回测
                        </button>
                    </td>
                </tr>
            `);
        });

        // 添加回测按钮点击事件
        $('.run-backtest-btn').on('click', function() {
            const gridCount = $(this).data('grid-count');
            const atr_factor = $(this).data('atr-factor');
            runBacktest(gridCount, atr_factor);
        });
    }

    // 添加执行回测的函数
    function runBacktest(gridCount, atr_factor) {
        const etfCode = $('#etf-select').val();
        const months = $('input[name="period-type"]:checked').val();
        
        // 显示遮罩层
        $('body').append(`
            <div class="analysis-overlay">
                <div class="loading-content">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <h5 class="mt-3">正在执行回测，请稍候...</h5>
                </div>
            </div>
        `);

        $.ajax({
            url: '/api/grid_trade/run_backtest',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                etf_code: etfCode,
                months: months,
                grid_count: gridCount,
                atr_factor: atr_factor,
                atr: currentATR
            }),
            success: function(result) {
                showBacktestResult(result)
            },
            error: handleAjaxError,
            complete: function() {
                $('.analysis-overlay').remove();
            }
        });
    }

    // 显示回测结果
    function showBacktestResult(result) {
        backtest = result.best_backtest
        daily_returns = result.benchmark.daily_returns
        // 显示回测结果区域
        $('#backtest-result-section').removeClass('d-none');
        
        // 更新绩效对比表
        updatePerformanceComparison(backtest.evaluation, result.benchmark);
        
        // 更新网格价格列表
        updateGridPriceList(backtest.grids);
        
        // 更新网格交易走势图
        updateGridTradingChart(backtest);
        
        // 更新收益曲线图
        updateReturnsChart(backtest, daily_returns);
        
        // 更新交易记录
        updateTradesTable(backtest.trades);
    }

    // 更新绩效对比表
    function updatePerformanceComparison(strategy, benchmark) {
        const tbody = $('#performance-comparison-table tbody');
        tbody.empty();

        const metrics = [
            { key: 'total_return', name: '总收益率', format: 'percent' },
            { key: 'annual_return', name: '年化收益率', format: 'percent' },
            { key: 'max_drawdown', name: '最大回撤', format: 'percent', reverse: true }, // reverse: 越小越好
            { key: 'sharpe_ratio', name: '夏普比率', format: 'number' },
            { key: 'capital_utilization', name: '资金利用率', format: 'percent' },
            { key: 'trade_count', name: '交易次数', format: 'integer' }
        ];

        metrics.forEach(metric => {
            let sVal = strategy[metric.key];
            let bVal = benchmark[metric.key];
            
            // 处理特殊情况
            if (metric.key === 'trade_count' && bVal === undefined) bVal = 1;
            if (metric.key === 'capital_utilization' && bVal === undefined) bVal = 1.0;

            let diff = sVal - bVal;
            let diffClass = '';
            
            // 判定好坏颜色
            if (metric.reverse) {
                // 对于回撤，数值越小越好。如果 sVal < bVal (diff < 0)，则是好的（绿色）
                if (diff < 0) diffClass = 'text-success fw-bold';
                else if (diff > 0) diffClass = 'text-danger fw-bold';
            } else {
                // 对于收益，数值越大越好
                if (diff > 0) diffClass = 'text-success fw-bold';
                else if (diff < 0) diffClass = 'text-danger fw-bold';
            }
            
            // 格式化数值
            let sText, bText, dText;
            if (metric.format === 'percent') {
                sText = (sVal * 100).toFixed(2) + '%';
                bText = (bVal * 100).toFixed(2) + '%';
                dText = (diff * 100).toFixed(2) + '%';
                if (diff > 0) dText = '+' + dText;
            } else if (metric.format === 'integer') {
                sText = parseInt(sVal);
                bText = parseInt(bVal);
                dText = parseInt(diff);
                if (diff > 0) dText = '+' + dText;
            } else {
                sText = sVal.toFixed(2);
                bText = bVal.toFixed(2);
                dText = diff.toFixed(2);
                if (diff > 0) dText = '+' + dText;
            }

            tbody.append(`
                <tr>
                    <td>${metric.name}</td>
                    <td>${sText}</td>
                    <td>${bText}</td>
                    <td class="${diffClass}">${dText}</td>
                </tr>
            `);
        });
    }

    // 更新网格价格列表
    function updateGridPriceList(grids) {
        const container = $('#grid-price-list');
        container.empty();
        
        // 对网格按价格从高到低排序
        const sortedGrids = [...grids].sort((a, b) => b.price - a.price);
        
        sortedGrids.forEach((grid, index) => {
            // 计算收益率
            const profitRate = (grid.profit / (grid.price * grid.position) * 100).toFixed(2);
            
            container.append(`
                <div class="col-md-3 col-sm-4 mb-2">
                    <div class="card ${index === Math.floor(grids.length/2)-1 ? 'border-primary' : ''}">
                        <div class="card-body p-2 text-center">
                            <div class="small text-muted">网格 ${index+1}</div>
                            <div class="fw-bold">${grid.price.toFixed(3)}</div>
                            <div class="small text-success">
                                <i class="bi bi-box-arrow-in-right"></i> ${grid.position}
                            </div>
                            <div class="small ${grid.profit > 0 ? 'text-success' : 'text-danger'}">
                                <i class="bi ${grid.profit > 0 ? 'bi-graph-up-arrow' : 'bi-graph-down-arrow'}"></i>
                                ${grid.profit.toFixed(2)} (${profitRate}%)
                            </div>
                            <div class="small text-muted">
                                ${index === 0 ? '上限' : 
                                  index === grids.length-1 ? '下限' : 
                                  `±${grid.grid_percent.toFixed(2)}%`}
                            </div>
                        </div>
                    </div>
                </div>
            `);
        });
    }

    // 添加新函数：更新收益曲线图
    function updateReturnsChart(backtest, daily_returns) {
        const chartContainer = document.getElementById('returns-chart');
        
        // 销毁旧的图表实例
        const existingChart = echarts.getInstanceByDom(chartContainer);
        if (existingChart) {
            existingChart.dispose();
        }
        
        // 创建新的图表实例
        const returnsChart = echarts.init(chartContainer);
        
        // 计算网格间距参考线
        const gridCount = backtest.grids.length;  // 获取网格数量
        const gridLines = [];
        
        // 计算基准网格的位置（中间网格）
        const baseGridIndex = Math.floor(gridCount / 2);
        const baseGrid = backtest.grids[baseGridIndex];
        
        // 遍历所有网格生成参考线
        backtest.grids.forEach((grid, index) => {
            // 计算相对于基准网格的收益率
            const returnRate = ((grid.price - baseGrid.price) / baseGrid.price) * 100;
            
            gridLines.push({
                yAxis: returnRate,
                lineStyle: {
                    type: 'dashed',
                    color: '#800080',
                    width: 1,
                    opacity: 0.4
                },
                label: {
                    show: true,
                    position: 'right',
                    formatter: `${returnRate.toFixed(2)}%`
                }
            });
        });
        
        const option = {
            title: {
                text: ''
            },
            tooltip: {
                trigger: 'axis',
                formatter: function(params) {
                    let result = params[0].axisValue + '<br/>';
                    params.forEach(param => {
                        result += param.marker + param.seriesName + ': ' + 
                                 param.value.toFixed(2) + '%<br/>';
                    });
                    return result;
                }
            },
            legend: {
                data: ['网格策略', 'Buy&Hold策略']
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '3%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                data: backtest.all_dates,
                axisLabel: {
                    formatter: function(value) {
                        return value.substring(0, 10);
                    }
                }
            },
            yAxis: {
                type: 'value',
                name: '收益率(%)',
                axisLabel: {
                    formatter: '{value}%'
                },
                splitLine: {
                    show: false  // 隐藏默认网格线
                }
            },
            series: [
                {
                    name: '网格策略',
                    type: 'line',
                    data: backtest.all_returns,
                    lineStyle: {
                        width: 2,
                        color: '#5470c6'
                    },
                    markLine: {
                        silent: true,
                        data: gridLines
                    }
                },
                {
                    name: 'Buy&Hold策略',
                    type: 'line',
                    data: daily_returns,
                    lineStyle: {
                        width: 2,
                        color: '#91cc75'
                    }
                }
            ]
        };
        
        returnsChart.setOption(option);
        
        // 添加窗口大小变化监听
        window.addEventListener('resize', function() {
            returnsChart.resize();
        });
    }

    // 更新交易记录表格
    function updateTradesTable(trades) {
        const tbody = $('#trades-table tbody');
        tbody.empty();
        
        trades.forEach(trade => {
            const tradeValue = trade.price * Math.abs(trade.amount);
            const rowClass = trade.direction === 'buy' ? 'table-success' : 'table-danger';
            
            tbody.append(`
                <tr class="${rowClass}">
                    <td>${trade.timestamp}</td>
                    <td>${trade.direction === 'buy' ? '买入' : '卖出'}</td>
                    <td style="text-align: right;">${trade.price.toFixed(3)}</td>
                    <td style="text-align: right;">${trade.amount.toLocaleString('en-US')}</td>
                    <td style="text-align: right;">${tradeValue.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td style="text-align: right;">${trade.current_position.toLocaleString('en-US')}</td>
                    <td style="text-align: right;">${trade.position_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td style="text-align: right;">${trade.cash.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    <td style="text-align: right;">${trade.total_value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                </tr>
            `);
        });
    }

    // 更新网格交易走势图
    function updateGridTradingChart(backTestResult) {
        // 从交易记录中提取日期和价格数据
        if (!backTestResult || !backTestResult.trades || !backTestResult.trades.length) {
            console.error('回测数据不完整:', backTestResult);
            return;
        }

        // 按时间排序交易记录
        const sortedTrades = [...backTestResult.trades].sort((a, b) => 
            new Date(a.timestamp) - new Date(b.timestamp)
        );

        // 提取日期和价格数据
        // backTestResult.dates = sortedTrades.map(trade => trade.timestamp);
        // backTestResult.prices = sortedTrades.map(trade => trade.price);
        backTestResult.dates = backTestResult.all_dates;
        backTestResult.prices = backTestResult.all_prices;

        // 获取图表容器
        const chartContainer = document.getElementById('grid-trading-chart');
        
        // 销毁旧的图表实例
        const existingChart = echarts.getInstanceByDom(chartContainer);
        if (existingChart) {
            existingChart.dispose();
        }
        
        // 创建新的图表实例
        const gridChart = echarts.init(chartContainer);
        
        // 构建网格线数据
        const gridLines = (backTestResult.grids || []).map(grid => ({
            price: grid.price,
            data: new Array(backTestResult.dates.length).fill(grid.price)
        }));
        
        // 构建交易点数据
        const trades = backTestResult.trades || [];
        const buyPoints = trades
            .filter(trade => trade.direction === 'buy')
            .map(trade => ([
                trade.timestamp,
                trade.price,
                '买入'
            ]));
        
        const sellPoints = trades
            .filter(trade => trade.direction === 'sell')
            .map(trade => ([
                trade.timestamp,
                trade.price,
                '卖出'
            ]));
        
        const option = {
            title: {
                text: ''
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'cross'
                },
                formatter: function(params) {
                    let result = params[0].axisValue + '<br/>';
                    params.forEach(param => {
                        if (param.seriesName === '价格') {
                            result += param.marker + param.seriesName + ': ' + param.data.toFixed(3) + '<br/>';
                        } else if (['买入点', '卖出点'].includes(param.seriesName) && param.data) {
                            result += param.marker + param.data[2] + ': ' + param.data[1].toFixed(3) + '<br/>';
                        }
                    });
                    return result;
                }
            },
            legend: {
                data: ['价格', '买入点', '卖出点'],
                selected: {
                    '价格': true,
                    '买入点': true,
                    '卖出点': true
                }
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '3%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                data: backTestResult.dates,
                axisLabel: {
                    formatter: function(value) {
                        return value.substring(0, 10);
                    }
                }
            },
            yAxis: {
                    type: 'value',
                    scale: true,
                    splitLine: {
                        show: true
                    }
                },
            dataZoom: [
                {
                    type: 'inside',
                    start: 0,
                    end: 100
                },
                {
                    show: true,
                    type: 'slider',
                    bottom: 10
                }
            ],
            series: [
                {
                    name: '价格',
                    type: 'line',
                    data: backTestResult.prices,  // 添加价格数据
                    lineStyle: {
                        width: 2,
                        color: '#5470c6'  // 蓝色价格线
                    },
                    z: 3  // 确保价格线在最上层
                },
                {
                    name: '买入点',
                    type: 'scatter',
                    data: buyPoints,
                    symbol: 'circle',
                    symbolSize: 8,
                    itemStyle: {
                        color: '#91cc75',  // 绿色买点
                        opacity: 1
                    },
                    z: 4
                },
                {
                    name: '卖出点',
                    type: 'scatter',
                    data: sellPoints,
                    symbol: 'circle',
                    symbolSize: 8,
                    itemStyle: {
                        color: '#ee6666',  // 红色卖点
                        opacity: 1
                    },
                    z: 4
                },
                ...(gridLines.map(line => ({
                    name: `网格线 ${line.price.toFixed(3)}`,
                    type: 'line',
                    data: new Array(backTestResult.dates.length).fill(line.price),
                    lineStyle: {
                        type: 'dashed',
                        width: 1,
                        color: '#800080'  // 紫色网格线
                    },
                    symbol: 'none',
                    z: 2
                })))
            ]
        };
        
        gridChart.setOption(option);
        
        // 修改网格线和交易点的显示控制
        document.getElementById('show-grid-lines').addEventListener('change', function(e) {
            const isVisible = e.target.checked;
            const newOption = {
                series: option.series.map((series, index) => {
                    if (index > 2) {  // 网格线系列
                        return {
                            ...series,
                            lineStyle: {
                                ...series.lineStyle,
                                opacity: isVisible ? 1 : 0
                            }
                        };
                    }
                    return series;
                })
            };
            gridChart.setOption(newOption);
        });
        
        document.getElementById('show-trade-points').addEventListener('change', function(e) {
            const isVisible = e.target.checked;
            const newOption = {
                series: option.series.map((series, index) => {
                    if (index === 1 || index === 2) {  // 买卖点系列
                        return {
                            ...series,
                            symbolSize: isVisible ? 8 : 0
                        };
                    }
                    return series;
                })
            };
            gridChart.setOption(newOption);
        });
    }

    loadEtfList()
    
    // 初始化
    initCharts();

    initializeEventListeners()
});