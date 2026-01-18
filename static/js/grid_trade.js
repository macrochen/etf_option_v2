$(document).ready(function() {
    let currentStrategy = null; // 存储当前生成的策略数据

    // 1. 初始化页面
    loadEtfList();
    
    // 2. 加载 ETF 列表
    function loadEtfList(selectedCode = null) {
        $.get('/api/grid_trade/etf_list', function(data) {
            const $select = $('#etf-select');
            $select.empty().append('<option value="">-- 请选择或输入 --</option>');
            data.forEach(etf => {
                const selected = (selectedCode === etf.code) ? 'selected' : '';
                // 确保 etf 对象包含 start_date 和 end_date
                $select.append(`<option value="${etf.code}" ${selected} data-start="${etf.start_date}" data-end="${etf.end_date}">${etf.code} - ${etf.name}</option>`);
            });
            // 如果传入了代码，确保 input 也同步
            if (selectedCode) {
                $('#etf-code-input').val(selectedCode);
                updateDateRangeDisplay(); // 更新显示
            }
        });
    }

    // 3. 监听 ETF 选择变化
    $('#etf-select').on('change', function() {
        const val = $(this).val();
        if(val) $('#etf-code-input').val(val);
        updateDateRangeDisplay();
    });
    
    function updateDateRangeDisplay() {
        const $opt = $('#etf-select option:selected');
        const start = $opt.data('start');
        const end = $opt.data('end');
        if (start && end) {
            $('#data-range-display').text(`${start} ~ ${end}`).addClass('text-success');
            // 设置输入框的 min/max 属性
            $('#custom-start-date').attr('min', start).attr('max', end);
            $('#custom-end-date').attr('min', start).attr('max', end);
            
            // 默认设置结束时间为数据结束时间
            if (!$('#custom-end-date').val()) {
                $('#custom-end-date').val(end);
            }
        } else {
            $('#data-range-display').text('请先选择标的').removeClass('text-success');
        }
    }
    
    // 日期输入验证 (静默修正)
    $('#custom-start-date, #custom-end-date').on('change', function() {
        const $opt = $('#etf-select option:selected');
        const minDate = $opt.data('start');
        const maxDate = $opt.data('end');
        
        if (!minDate || !maxDate) return;
        
        const val = $(this).val();
        if (!val) return;

        if (val < minDate) {
            $(this).val(minDate);
        } else if (val > maxDate) {
            $(this).val(maxDate);
        }
    });
    
    // 快捷日期选择
    $('.quick-date-btn').on('click', function() {
        const years = $(this).data('years');
        const mode = $(this).data('mode');
        const fmt = d => d.toISOString().split('T')[0];
        
        // 获取当前数据的边界
        const $opt = $('#etf-select option:selected');
        const minDataDate = $opt.data('start');
        const maxDataDate = $opt.data('end');
        
        if (mode === 'backward') {
            // 以结束日为基准，向前推 Start
            let endDateStr = $('#custom-end-date').val();
            if (!endDateStr) endDateStr = maxDataDate;
            if (!endDateStr) endDateStr = new Date().toISOString().split('T')[0];
            
            $('#custom-end-date').val(endDateStr);
            
            const endDate = new Date(endDateStr);
            let startDate = new Date(endDate);
            
            if (years === 'ytd') {
                startDate = new Date(endDate.getFullYear(), 0, 1);
            } else {
                const y = parseInt(years);
                startDate.setFullYear(endDate.getFullYear() - y);
            }
            
            // 边界检查
            let startDateStr = fmt(startDate);
            if (minDataDate && startDateStr < minDataDate) {
                startDateStr = minDataDate;
            }
            $('#custom-start-date').val(startDateStr).change(); // 触发 change 以便执行可能存在的其他逻辑
            
        } else {
            // 以开始日为基准，向后推 End
            let startDateStr = $('#custom-start-date').val();
            if (!startDateStr) startDateStr = minDataDate;
            if (!startDateStr) {
                alert('请先指定开始日期');
                return;
            }
            
            $('#custom-start-date').val(startDateStr);
            
            const startDate = new Date(startDateStr);
            let endDate = new Date(startDate);
            
            const y = parseInt(years);
            endDate.setFullYear(startDate.getFullYear() + y);
            
            // 边界检查
            let endDateStr = fmt(endDate);
            if (maxDataDate && endDateStr > maxDataDate) {
                endDateStr = maxDataDate;
            }
            
            $('#custom-end-date').val(endDateStr).change();
        }
    });

    // 4. 加载数据按钮
    $('#load-etf-btn').on('click', function() {
        const code = $('#etf-code-input').val().trim();
        if (!code) {
            alert('请输入 ETF 代码');
            return;
        }
        
        const $btn = $(this);
        const $status = $('#data-status');
        
        $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> 下载中...');
        $status.text('正在从 AKShare 获取最近5年数据...');
        
        $.ajax({
            url: '/api/grid_trade/load_etf',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ etf_code: code }),
            success: function(res) {
                $status.text('数据已就绪 ✓').addClass('text-success').removeClass('text-muted text-danger');
                loadEtfList(code); // 核心修正：刷新列表并选中当前代码
            },
            error: function(xhr) {
                $status.text('下载失败: ' + (xhr.responseJSON?.error || '未知错误')).addClass('text-danger');
            },
            complete: function() {
                $btn.prop('disabled', false).html('<i class="bi bi-cloud-download"></i> 加载数据');
            }
        });
    });

    // 5. 生成策略按钮 (主逻辑)
    $('#smart-grid-form').on('submit', function(e) {
        e.preventDefault();
        
        const formData = {
            symbol: $('#etf-code-input').val().trim(),
            total_capital: parseFloat($('#total-capital').val()),
            base_position_ratio: parseFloat($('#base-pos-ratio').val()),
            cash_reserve_ratio: parseFloat($('#cash-reserve-ratio').val()) || 0.0,
            pe_percentile: parseFloat($('#pe-percentile').val()),
            pb_percentile: parseFloat($('#pb-percentile').val()),
            force_mode: $('#force-mode').val() || null,
            custom_start_date: $('#custom-start-date').val(),
            custom_end_date: $('#custom-end-date').val()
        };

        if (!formData.symbol) {
            alert('请先指定 ETF 代码');
            return;
        }

        $('#loading-overlay').removeClass('d-none').addClass('d-flex');
        
        $.ajax({
            url: '/api/grid_trade/smart_generate',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(formData),
            success: function(res) {
                currentStrategy = res;
                $('#result-section').removeClass('d-none'); 
                
                // 给浏览器一点时间完成布局渲染
                setTimeout(() => {
                    renderResults(res);
                    // 滚动到结果区
                    $('html, body').animate({
                        scrollTop: $("#result-section").offset().top - 70
                    }, 500);
                }, 100);
            },
            error: function(xhr) {
                alert('生成失败: ' + (xhr.responseJSON?.error || '未知错误'));
            },
            complete: function() {
                $('#loading-overlay').addClass('d-none').removeClass('d-flex');
            }
        });
    });

    // 6. 渲染结果
    function renderResults(data) {
        const strat = data.strategy;
        const bt = data.backtest.summary;
        const scores = strat.scores;
        
        // --- 波动率评分卡片 ---
        if (scores) {
            $('#res-score-total').text(scores.total);
            $('#res-score-beta').text(scores.beta.toFixed(2));
            $('#res-score-amp').text(scores.amplitude.toFixed(2) + '%');
            $('#score-badge').text(scores.total + ' / 100');
            
            // 进度条颜色
            const $prog = $('#score-progress');
            $prog.css('width', scores.total + '%');
            if (scores.total >= 80) $prog.removeClass().addClass('progress-bar bg-success');
            else if (scores.total >= 60) $prog.removeClass().addClass('progress-bar bg-info');
            else $prog.removeClass().addClass('progress-bar bg-warning');
        }
        
        // --- 策略卡片 ---
        // 模式
        const modeMap = {
            'Accumulate': '潜伏积累 (Accumulate)',
            'Neutral': '标准震荡 (Neutral)',
            'Trend': '趋势跟随 (Trend)'
        };
        const modeColor = {
            'Accumulate': 'text-success', // 绿吸
            'Neutral': 'text-primary',
            'Trend': 'text-danger'        // 红涨
        };
        
        $('#res-mode').text(modeMap[strat.mode] || strat.mode)
                      .removeClass().addClass('fw-bold ' + (modeColor[strat.mode] || 'text-dark'));
                      
        // 区间
        $('#res-range').html(`${strat.price_range[0].toFixed(3)} ~ ${strat.price_range[1].toFixed(3)}`);
        
        // 网格数
        $('#res-count').text(strat.grid_count + ' 格');

        // 步长
        $('#res-step').html(`${strat.step.percent}% <small class="text-muted">(${strat.step.price})</small>`);
        
        // 单格 (仅展示数量)
        const pg = strat.per_grid;
        const volHtml = pg.buy_vol === pg.sell_vol ? 
            `${pg.buy_vol} 股` : 
            `<span class="text-success">B:${pg.buy_vol}</span> / <span class="text-purple">S:${pg.sell_vol}</span>`;
        $('#res-per-grid').html(volHtml);
        
        // 说明
        $('#res-desc').html(`<i class="bi bi-info-circle"></i> ${strat.description}`);
        
        // --- 填充绩效仪表盘 (整合版) ---
        const $dashboard = $('#performance-dashboard tbody');
        $dashboard.empty();
        
        // 定义指标配置
        const metrics = [
            { id: 'total_return', name: '总收益率', unit: '%', benchmark: 'benchmark_total_return', reverse: false },
            { id: 'annualized_return', name: '年化收益', unit: '%', benchmark: 'benchmark_annualized_return', reverse: false },
            { id: 'max_drawdown', name: '最大回撤', unit: '%', benchmark: 'benchmark_max_drawdown', reverse: true },
            { id: 'sharpe_ratio', name: '夏普比率', unit: '', benchmark: 'benchmark_sharpe_ratio', reverse: false },
            { id: 'grid_profit', name: '网格利润 (已实现)', unit: '', prefix: '¥', benchmark: null },
            { id: 'trade_count', name: '交易次数', unit: '', benchmark: null, isInt: true },
            { id: 'buy_count', name: '买入次数', unit: '', benchmark: null, isInt: true },
            { id: 'sell_count', name: '卖出次数', unit: '', benchmark: null, isInt: true },
            { id: 'capital_utilization', name: '资金利用率', unit: '%', benchmark: null },
            { id: 'break_rate', name: '破网率', unit: '%', benchmark: null },
            { id: 'missed_trades', name: '无效触网 (Missed)', unit: '次', benchmark: null, isInt: true }
        ];
        
        metrics.forEach(m => {
            let sVal = bt[m.id];
            let bVal = m.benchmark ? bt[m.benchmark] : null;
            
            // 格式化数值
            const fmt = (val, unit, prefix='', isInt=false) => {
                if (val === null || val === undefined) return '-';
                return prefix + (isInt ? Math.round(val) : val.toFixed(2)) + unit;
            };
            
            let sText = fmt(sVal, m.unit, m.prefix, m.isInt);
            let bText = bVal !== null ? fmt(bVal, m.unit, m.prefix, m.isInt) : '<span class="text-muted">-</span>';
            
            // 计算差异与评价
            let diffHtml = '<span class="text-muted">-</span>';
            if (bVal !== null) {
                let diff = sVal - bVal;
                let isGood = m.reverse ? (diff < 0) : (diff > 0);
                let colorClass = isGood ? 'text-success' : 'text-danger';
                let icon = isGood ? '<i class="bi bi-hand-thumbs-up-fill"></i>' : '';
                let sign = diff > 0 ? '+' : '';
                
                diffHtml = `<span class="${colorClass} fw-bold">${sign}${diff.toFixed(2)}${m.unit} ${icon}</span>`;
            }
            
            // 针对特有指标的特殊样式
            if (m.id === 'grid_profit') sText = `<span class="text-success fw-bold">${sText}</span>`;
            if (m.id === 'max_drawdown') sText = `<span class="text-danger">${sText}</span>`;

            $dashboard.append(`
                <tr>
                    <td class="bg-light fw-bold text-start ps-4">${m.name}</td>
                    <td class="fs-6">${sText}</td>
                    <td>${bText}</td>
                    <td>${diffHtml}</td>
                </tr>
            `);
        });

        // --- 填充回测参数详情 ---
        if (data.backtest.parameters) {
            const p = data.backtest.parameters;
            const bpg = p.per_grid;
            const bVolHtml = bpg.buy_vol === bpg.sell_vol ? 
                `${bpg.buy_vol}股` : 
                `<span class="text-success">B:${bpg.buy_vol}</span> / <span class="text-purple" style="color:#aa00ff">S:${bpg.sell_vol}</span>`;
            
            $('#bt-param-range').html(`${p.price_range[0].toFixed(3)} ~ ${p.price_range[1].toFixed(3)}`);
            $('#bt-param-count').text(p.grid_count + ' 格');
            $('#bt-param-step').html(`${p.step.percent}% <small class="text-muted">(${p.step.price})</small>`);
            $('#bt-param-per-grid').html(bVolHtml);
        }

        // --- 绘制权益曲线 ---
        const equityChart = renderEquityChart(data.backtest.curve);
        
        // 监听折叠展开事件，展开后重新调整图表尺寸
        $('#equityCollapse').on('shown.bs.collapse', function () {
            if (equityChart) equityChart.resize();
        });
        
        // --- 绘制价格与网格图 (带交易点) ---
        // 注意：这里使用的是回测时生成的网格线 (backtest_grid_lines)，而非当前建议网格线
        renderPriceChart(data.backtest.curve, data.backtest.backtest_grid_lines, data.backtest.trades);
        
        // --- 填充交易记录表 ---
        renderTradeTable(data.backtest.trades);
    }

    function renderPriceChart(curveData, gridLines, trades) {
        const chartDom = document.getElementById('price-chart');
        const myChart = echarts.init(chartDom);
        
        const dates = curveData.map(d => d.date);
        
        // ECharts K线数据格式: [Open, Close, Lowest, Highest]
        const kLineData = curveData.map(d => [d.open, d.price, d.low, d.high]);
        
        // 布林带数据
        const bollUpper = curveData.map(d => d.boll_upper);
        const bollMid = curveData.map(d => d.boll_mid);
        const bollLower = curveData.map(d => d.boll_lower);
        
        // 交易点数据 (需处理日期后缀以便 ECharts 对齐)
        const cleanDate = (d) => d.split(' ')[0]; // 移除 (底仓)/(网格) 后缀
        
        const buyPoints = trades.filter(t => t.type === 'BUY').map(t => [cleanDate(t.date), t.price, t.volume]);
        const sellPoints = trades.filter(t => t.type === 'SELL').map(t => [cleanDate(t.date), t.price, t.volume]);
        
        // 构造网格线 MarkLine 数据
        const markLineData = gridLines.map(line => {
            return {
                yAxis: line.price,
                lineStyle: {
                    type: 'solid',
                    color: '#666', // 调深灰色
                    width: 1,
                    opacity: 0.6 // 增加透明度
                },
                label: {
                    formatter: line.price.toFixed(3),
                    position: 'end',
                    color: '#333'
                }
            };
        });

        // 标记上下限颜色
        if (markLineData.length > 0) {
            markLineData[0].lineStyle.color = '#f44336'; // 鲜红
            markLineData[0].lineStyle.width = 2.5; // 加宽
            markLineData[0].lineStyle.opacity = 1.0;
            
            markLineData[markLineData.length - 1].lineStyle.color = '#4caf50'; // 鲜绿
            markLineData[markLineData.length - 1].lineStyle.width = 2.5; // 加宽
            markLineData[markLineData.length - 1].lineStyle.opacity = 1.0;
        }

        const option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' }
            },
            legend: {
                data: ['K线', 'MA20', '布林上轨', '布林下轨', '买入', '卖出']
            },
            grid: { left: '3%', right: '5%', bottom: '10%', top: '10%', containLabel: true },
            dataZoom: [
                { type: 'inside', start: 0, end: 100 },
                { type: 'slider', show: true, bottom: 0 }
            ],
            xAxis: {
                type: 'category',
                boundaryGap: true,
                data: dates
            },
            yAxis: {
                type: 'value',
                scale: true // 不从0开始
            },
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: kLineData,
                    itemStyle: {
                        color: '#d9534f', // 阳线红
                        color0: '#5cb85c', // 阴线绿
                        borderColor: '#d9534f',
                        borderColor0: '#5cb85c'
                    },
                    markLine: {
                        symbol: ['none', 'none'],
                        data: markLineData,
                        silent: true // 鼠标悬停不触发
                    }
                },
                {
                    name: 'MA20',
                    type: 'line',
                    data: bollMid,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1.5, color: '#ff9800', opacity: 0.9 }
                },
                {
                    name: '布林上轨',
                    type: 'line',
                    data: bollUpper,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1.5, type: 'dashed', color: '#00bcd4', opacity: 0.8 }
                },
                {
                    name: '布林下轨',
                    type: 'line',
                    data: bollLower,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1.5, type: 'dashed', color: '#00bcd4', opacity: 0.8 }
                },
                {
                    name: '买入',
                    type: 'scatter',
                    data: buyPoints,
                    symbol: 'triangle',
                    symbolSize: 6, 
                    itemStyle: { color: '#2962ff' }, // 改为宝蓝色
                    markPoint: {
                        symbol: 'circle',
                        symbolSize: 15, 
                        label: {
                            color: '#fff', // 白色文字
                            fontSize: 10,
                            offset: [0, 0]
                        },
                        data: buyPoints.map(p => ({
                            coord: [p[0], p[1]],
                            value: 'B',
                            symbolOffset: [0, '50%'], 
                            itemStyle: { color: '#2962ff' } // 宝蓝色背景
                        }))
                    }
                },
                {
                    name: '卖出',
                    type: 'scatter',
                    data: sellPoints,
                    symbol: 'triangle',
                    symbolRotate: 180,
                    symbolSize: 6,
                    itemStyle: { color: '#aa00ff' }, // 改为深紫色
                    markPoint: {
                        symbol: 'circle',
                        symbolSize: 15,
                        label: {
                            color: '#fff', // 白色文字
                            fontSize: 10,
                            offset: [0, 0]
                        },
                        data: sellPoints.map(p => ({
                            coord: [p[0], p[1]],
                            value: 'S',
                            symbolOffset: [0, '-50%'],
                            itemStyle: { color: '#aa00ff' } // 深紫色背景
                        }))
                    }
                }
            ]
        };
        
        myChart.setOption(option);
        setTimeout(() => { myChart.resize(); }, 0);
        window.addEventListener('resize', () => myChart.resize());
    }

    function renderTradeTable(trades) {
        const $tbody = $('#trade-history-table tbody');
        $tbody.empty();
        
        if (!trades || trades.length === 0) {
            $tbody.html('<tr><td colspan="9" class="text-center text-muted">暂无交易记录</td></tr>');
            return;
        }
        
        // 按时间顺序正序显示
        trades.forEach(t => {
            const isBuy = t.type === 'BUY';
            const color = isBuy ? 'text-danger' : 'text-success'; // A股红涨绿跌习惯：买入红，卖出绿(落袋)
            const typeText = isBuy ? '买入' : '卖出';
            
            $tbody.append(`
                <tr>
                    <td>${t.date}</td>
                    <td class="${color} fw-bold">${typeText}</td>
                    <td>${t.price.toFixed(3)}</td>
                    <td>${t.volume}</td>
                    <td>${t.amount.toFixed(2)}</td>
                    <td>${t.current_position}</td>
                    <td>${t.position_value.toFixed(2)}</td>
                    <td>${t.cash.toFixed(2)}</td>
                    <td>${t.total_value.toFixed(2)}</td>
                </tr>
            `);
        });
    }

    function renderEquityChart(curveData) {
        const chartDom = document.getElementById('equity-chart');
        let myChart = echarts.getInstanceByDom(chartDom);
        if (myChart) myChart.dispose();
        
        myChart = echarts.init(chartDom);
        
        const dates = curveData.map(d => d.date);
        const equities = curveData.map(d => d.equity);
        const benchmarkEquities = curveData.map(d => d.benchmark_equity);
        
        const option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' }
            },
            legend: {
                data: ['策略净值', '基准净值 (Buy & Hold)']
            },
            grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
            xAxis: {
                type: 'category',
                boundaryGap: false,
                data: dates
            },
            yAxis: {
                type: 'value',
                scale: true // 不从0开始
            },
            series: [
                {
                    name: '策略净值',
                    type: 'line',
                    data: equities,
                    smooth: true,
                    lineStyle: { width: 3, color: '#d9534f' }, // 加粗
                    symbol: 'none', // 去掉点，使线条更平滑
                    areaStyle: {
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            { offset: 0, color: 'rgba(217, 83, 79, 0.3)' },
                            { offset: 1, color: 'rgba(217, 83, 79, 0.05)' }
                        ])
                    }
                },
                {
                    name: '基准净值 (Buy & Hold)',
                    type: 'line',
                    data: benchmarkEquities,
                    smooth: true,
                    lineStyle: { width: 3, type: 'dashed', color: '#888' }, // 加粗虚线
                    symbol: 'none'
                }
            ]
        };
        
        myChart.setOption(option);
        // 显式触发一次 resize 以适应容器
        setTimeout(() => { myChart.resize(); }, 0);
        window.onresize = function() { myChart.resize(); };
        return myChart;
    }

});
