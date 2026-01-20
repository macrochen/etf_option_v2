$(document).ready(function() {
    let equityChart = null;
    let heatmapChart = null;
    let currentHeatmapData = null; // Store data for switching metrics

    // 初始化 Bootstrap Tooltips (即指即显)
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
      return new bootstrap.Tooltip(tooltipTriggerEl)
    })

    // 1. 初始化 ETF 列表
    loadEtfList();

    // 监听开始日期变化，自动填充推荐区间
    $('#start-date').on('change', function() {
        const symbol = $('#symbol').val();
        const date = $(this).val();
        if (symbol && date) {
            fetchPriceInfo(symbol, date);
        }
    });

    // 加载 ETF 列表
    function loadEtfList(selectedCode = null) {
        $.get('/api/grid_trade/etf_list', function(data) {
            const $select = $('#etf-select');
            $select.empty().append('<option value="">-- 请选择或输入 --</option>');
            data.forEach(etf => {
                const selected = (selectedCode === etf.code) ? 'selected' : '';
                $select.append(`<option value="${etf.code}" ${selected} data-start="${etf.start_date}" data-end="${etf.end_date}">${etf.code} - ${etf.name}</option>`);
            });
            if (selectedCode) {
                $('#symbol').val(selectedCode);
            } else {
                // 默认选中 510300 如果在列表里
                if ($('#symbol').val()) {
                    $select.val($('#symbol').val());
                }
            }
            
            // 初始触发一次价格获取 (如果有默认值)
            if ($('#symbol').val()) {
                autoFillDateRange();
                const sym = $('#symbol').val();
                if ($('#start-date').val()) {
                    fetchPriceInfo(sym, $('#start-date').val());
                }
                // fetchShannonScore(sym); // 移除自动检测
            }
        });
    }

    function autoFillDateRange() {
        const $opt = $('#etf-select option:selected');
        const startFull = $opt.data('start');
        const endFull = $opt.data('end');
        
        if (startFull && endFull) {
            const start = startFull.split(' ')[0];
            const end = endFull.split(' ')[0];
            
            // 显示数据范围
            $('#data-status').text(`本地数据可用范围: ${start} ~ ${end}`).addClass('text-success').removeClass('text-danger text-muted');

            $('#start-date').attr('min', start).attr('max', end);
            $('#end-date').attr('min', start).attr('max', end);
            
            if (!$('#start-date').val()) $('#start-date').val(start);
            if (!$('#end-date').val()) $('#end-date').val(end);
            
            if ($('#start-date').val() < start) $('#start-date').val(start);
            if ($('#end-date').val() > end) $('#end-date').val(end);
        } else {
             // 如果没数据或没选中
             const val = $('#etf-select').val();
             if (val) {
                 $('#data-status').text('该标的暂无本地数据，请点击右侧下载按钮').addClass('text-muted').removeClass('text-success text-danger');
             } else {
                 $('#data-status').text('').removeClass();
             }
        }
    }

    function fetchPriceInfo(symbol, date) {
        $.get(`/api/shannon/price_info?symbol=${symbol}&date=${date}`, function(res) {
            if (res.success) {
                $('#lower-limit').val(res.rec_lower);
                $('#upper-limit').val(res.rec_upper);
                
                // 渲染估值状态
                if (res.valuation) {
                    const v = res.valuation;
                    const isDefault = v.status.includes('默认');
                    const color = v.status.includes('低估') ? 'success' : (v.status.includes('高估') ? 'danger' : 'primary');
                    const bgClass = isDefault ? 'bg-light text-muted' : `bg-${color} bg-opacity-10 text-${color}`;
                    
                    const $container = $('#valuation-status-container');
                    $container.empty();
                    
                    const $box = $('<div class="rounded p-2 mt-2 mb-0 small border"></div>');
                    
                    if (isDefault) {
                        $box.addClass('bg-light text-muted')
                            .html(`<i class="bi bi-exclamation-circle"></i> ${v.status} (将使用默认宽区间)`);
                    } else {
                        $box.addClass(`border-${color} ${bgClass}`)
                            .html(`
                                <div class="d-flex justify-content-between">
                                    <span><i class="bi bi-graph-up"></i> ${v.index_name || '跟踪指数'}</span>
                                    <strong>${v.status}</strong>
                                </div>
                                <div class="mt-1">
                                    ${v.metric}: <b>${v.current_val}</b> (分位: ${v.percentile}%)
                                </div>
                                <div class="progress mt-1" style="height: 4px;">
                                    <div class="progress-bar bg-${color}" style="width: ${v.percentile}%"></div>
                                </div>
                            `);
                    }
                    $container.append($box);
                }
            }
        }).fail(function() {
            console.log('无法获取基准价格 (可能是本地无数据)');
        });
    }

    // 监听 ETF 选择变化
    $('#etf-select').on('change', function() {
        const val = $(this).val();
        if(val) {
            $('#symbol').val(val);
            autoFillDateRange();
            const date = $('#start-date').val();
            if (date) fetchPriceInfo(val, date);
            // 自动触发移除，改为手动
            // fetchShannonScore(val);
        }
    });
    
    // 新增：监听输入框手动输入，实时联动下拉框
    $('#symbol').on('input', function() {
        const code = $(this).val().trim();
        const $select = $('#etf-select');
        const $matchedOpt = $select.find(`option[value="${code}"]`);
        
        if ($matchedOpt.length > 0) {
            $select.val(code);
            autoFillDateRange();
            
            const date = $('#start-date').val();
            if (date) fetchPriceInfo(code, date);
        }
    });
    
    // 手动输入代码失去焦点时
    $('#symbol').on('blur', function() {
        // 保持原逻辑为空，或者移除该事件监听
    });

    // 监听检测按钮
    $('#btn-check-score').on('click', function() {
        const symbol = $('#symbol').val();
        if (!symbol) {
            alert('请先输入或选择 ETF 代码');
            return;
        }
        fetchShannonScore(symbol);
    });

    function fetchShannonScore(symbol) {
        // 确保面板展开
        const $panel = $('#scoreCardBody');
        if (!$panel.hasClass('show')) {
            new bootstrap.Collapse($panel[0], { show: true });
        }

        // 重置 UI
        const $btn = $('#btn-check-score');
        $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> 检测中...');
        
        $('#total-score').text('-').removeClass().addClass('display-4 fw-bold mb-0');
        $('#score-verdict').text('计算中...').removeClass().addClass('text-muted mt-2');
        $('#score-badge').text('检测中...').removeClass().addClass('badge bg-secondary');
        
        $.get(`/api/shannon/score?symbol=${symbol}`, function(res) {
            // 更新分数
            const score = res.total_score;
            const colorClass = 'text-' + res.color;
            const badgeClass = 'bg-' + res.color;
            
            // 处理评语中的特赦标记
            let verdictHtml = res.verdict;
            if (res.is_bull_exemption) {
                const tip = "触发牛市特赦条款：因短期热度极高(>85)，系统自动调低了安全权重。属于高风险趋势交易。";
                // 将文字 [趋势特赦] 替换为带图标的红标签
                const tag = ` <span class="badge bg-danger ms-1" data-bs-toggle="tooltip" title="${tip}" style="cursor: help;"><i class="bi bi-fire"></i> 趋势特赦</span>`;
                verdictHtml = res.verdict.replace('[趋势特赦]', tag);
            }
            
            $('#total-score').text(score).removeClass().addClass(`display-4 fw-bold mb-0 ${colorClass}`);
            $('#score-verdict').html(verdictHtml).removeClass().addClass(colorClass + ' mt-2');
            $('#score-badge').text(res.verdict.split(' ')[0]).removeClass().addClass(`badge ${badgeClass}`);
            
            // 重新初始化新产生的 Tooltip
            setTimeout(() => {
                $('#score-verdict [data-bs-toggle="tooltip"]').each(function() {
                    new bootstrap.Tooltip(this, { container: 'body' });
                });
            }, 100);
            
            // 渲染雷达图
            renderRadarChart(res);
        })
        .fail(function() {
            $('#score-verdict').text('数据不足或无数据');
            $('#score-badge').text('失败').removeClass().addClass('badge bg-danger');
        })
        .always(function() {
            $btn.prop('disabled', false).html('<i class="bi bi-heart-pulse"></i> 重新检测');
        });
    }
    
    function renderRadarChart(res) {
        const dom = document.getElementById('radar-chart');
        let myChart = echarts.getInstanceByDom(dom);
        if (myChart) myChart.dispose();
        myChart = echarts.init(dom);
        
        const option = {
            tooltip: {
                trigger: 'item'
            },
            radar: {
                indicator: [
                    { name: '长期基因\n(震荡体质)', max: 100 },
                    { name: '中期安全\n(估值位置)', max: 100 },
                    { name: '短期热度\n(成交机会)', max: 100 }
                ],
                center: ['50%', '50%'],
                radius: '65%',
                splitNumber: 4,
                axisName: { color: '#666' }
            },
            series: [{
                name: '香农评分维度',
                type: 'radar',
                data: [{
                    value: [
                        res.details.long_term_gene,
                        res.details.mid_term_safety,
                        res.details.short_term_heat
                    ],
                    name: '维度得分'
                }],
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(13, 110, 253, 0.5)' },
                        { offset: 1, color: 'rgba(13, 110, 253, 0.1)' }
                    ])
                },
                itemStyle: { color: '#0d6efd' },
                lineStyle: { width: 2 }
            }]
        };
        myChart.setOption(option);
    }

    // 加载数据按钮
    $('#load-data-btn').on('click', function() {
        const code = $('#symbol').val().trim();
        if (!code) {
            alert('请输入 ETF 代码');
            return;
        }
        
        const $btn = $(this);
        const $status = $('#data-status');
        
        $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> 下载中...');
        $status.text('正在从 AKShare 获取分钟数据 (请耐心等待)...').removeClass('text-success text-danger').addClass('text-muted');
        
        $.ajax({
            url: '/api/shannon/download_data',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ symbol: code }),
            success: function(res) {
                if (res.success) {
                    const info = res.info;
                    $status.text(`下载成功! 本地数据: ${info.start} ~ ${info.end} (共 ${info.count} 条)`).addClass('text-success').removeClass('text-muted');
                    
                    // 刷新 ETF 列表并选中当前代码
                    loadEtfList(code);
                    
                    // 自动设置时间范围
                    if (info.start && info.end) {
                        $('#start-date').val(info.start.split(' ')[0]);
                        $('#end-date').val(info.end.split(' ')[0]);
                        // 触发一次推荐值更新
                        fetchPriceInfo(code, info.start.split(' ')[0]);
                    }
                } else {
                    $status.text('下载失败: ' + res.error).addClass('text-danger');
                }
            },
            error: function(xhr) {
                const err = xhr.responseJSON?.error || '未知错误';
                $status.text('请求失败: ' + err).addClass('text-danger');
            },
            complete: function() {
                $btn.prop('disabled', false).html('<i class="bi bi-cloud-download"></i> 加载分钟数据');
            }
        });
    });

    // 设置默认日期
    const today = new Date().toISOString().split('T')[0];
    if (!$('#end-date').val()) {
        $('#end-date').val(today);
    }

    // 1. 运行回测
    $('#shannon-form').on('submit', function(e) {
        e.preventDefault();
        
        const data = {
            symbol: $('#symbol').val().trim(),
            start_date: $('#start-date').val(),
            end_date: $('#end-date').val(),
            initial_capital: parseFloat($('#initial-capital').val()),
            faith_ratio: parseFloat($('#faith-ratio').val()),
            grid_ratio: parseFloat($('#grid-ratio').val()),
            pos_per_grid: parseFloat($('#pos-per-grid').val()),
            grid_density: parseFloat($('#grid-density').val()) / 100,
            sell_gap: parseFloat($('#sell-gap').val()) / 100,
            lower_limit: parseFloat($('#lower-limit').val()) || 0.0,
            upper_limit: parseFloat($('#upper-limit').val()) || 999.0
        };

        showLoading('正在执行高精度回测...');
        
        $.ajax({
            url: '/api/shannon/backtest',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(res) {
                renderBacktestResults(res);
                $('#metrics-card').removeClass('d-none');
                // Dashboard 布局，自动滚动到结果区
                document.getElementById('shannon-result-section').scrollIntoView({ behavior: 'smooth' });
            },
            error: function(xhr) {
                console.error("Backtest failed. Status:", xhr.status);
                console.error("Response Text:", xhr.responseText);
                if (xhr.responseJSON) {
                    console.error("Error Detail:", xhr.responseJSON.error);
                }
                hideLoading();
                // 在界面上显示个简单的提示而非弹窗
                $('#data-status').text('回测执行失败，具体错误请查看浏览器控制台 (F12)').addClass('text-danger');
            },
            complete: function() {
                hideLoading();
            }
        });
    });

    // 2. 生成热力图
    $('#btn-heatmap').on('click', function() {
        const data = {
            symbol: $('#symbol').val().trim(),
            start_date: $('#start-date').val(),
            end_date: $('#end-date').val(),
            initial_capital: parseFloat($('#initial-capital').val()),
            faith_ratio: parseFloat($('#faith-ratio').val()),
            grid_ratio: parseFloat($('#grid-ratio').val()),
            pos_per_grid: parseFloat($('#pos-per-grid').val()),
            lower_limit: parseFloat($('#lower-limit').val()) || 0.0,
            upper_limit: parseFloat($('#upper-limit').val()) || 999.0
        };

        showLoading('正在生成参数热力图 (100+ 回测并行)...');
        
        $.ajax({
            url: '/api/shannon/heatmap',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(res) {
                currentHeatmapData = res;
                
                // 显示结果区域容器
                $('#shannon-result-section').removeClass('d-none');
                
                // 直接渲染热力图
                renderHeatmap();
                
                // 滚动到热力图
                document.getElementById('heatmap-chart').scrollIntoView({ behavior: 'smooth' });
            },
            error: function(xhr) {
                console.error("Heatmap failed. Status:", xhr.status);
                console.error("Response Text:", xhr.responseText);
                hideLoading();
                $('#data-status').text('热力图生成失败，请查看控制台').addClass('text-danger');
            },
            complete: function() {
                hideLoading();
            }
        });
    });

    // 监听指标切换
    $('input[name="hm-metric"]').on('change', function() {
        if (currentHeatmapData) {
            renderHeatmap();
        }
    });

    function renderBacktestResults(res) {
        // 显示结果区
        $('#shannon-result-section').removeClass('d-none');
        
        // 1. 更新核心指标
        const m = res.metrics;
        console.log("Backtest Metrics:", m); // Debug: Check if fields exist
        
        $('#metric-return').text(m.total_return + '%');
        $('#metric-return').removeClass().addClass('fw-bold ' + (m.total_return >= 0 ? 'text-danger' : 'text-success')); 
        $('#bench-return').text(`基准: ${m.bench_return}%`);
        
        $('#metric-drawdown').text(m.max_drawdown + '%');
        // 回撤优化展示
        let ddBadge = '';
        let ddRed = parseFloat(m.dd_reduction);
        if (!isNaN(ddRed)) {
            if (ddRed > 0) {
                ddBadge = `<span class="badge bg-success ms-1" title="比买入持有少跌 ${ddRed}%"><i class="bi bi-shield-check"></i> 降 ${ddRed}%</span>`;
            } else {
                ddBadge = `<span class="badge bg-danger ms-1">增 ${Math.abs(ddRed)}%</span>`;
            }
        }
        $('#bench-drawdown').html(`基准: ${m.bench_max_drawdown}% ${ddBadge}`);
        
        // 卡玛比率展示
        $('#metric-calmar').text(m.calmar_ratio);
        let calmarBadge = '';
        let calImp = parseFloat(m.calmar_imp);
        if (!isNaN(calImp) && calImp > 0) {
            calmarBadge = `<span class="badge bg-success ms-1" title="回撤性价比提升 ${calImp}%">↑ ${calImp}%</span>`;
        }
        $('#bench-calmar').html(`基准: ${m.bench_calmar} ${calmarBadge}`);

        $('#metric-sharpe').text(m.sharpe_ratio);
        // 夏普提升展示
        let sharpeBadge = '';
        let shImp = parseFloat(m.sharpe_imp);
        if (!isNaN(shImp) && shImp > 0) {
            sharpeBadge = `<span class="badge bg-info text-dark ms-1" title="波动性价比提升 ${shImp}%">↑ ${shImp}%</span>`;
        }
        $('#bench-sharpe').html(`基准: ${m.bench_sharpe} ${sharpeBadge}`);
        
        $('#metric-cagr').text(m.annualized_return + '%');
        $('#metric-cagr').removeClass().addClass('text-end fw-bold ' + (m.annualized_return >= 0 ? 'text-danger' : 'text-success'));

        $('#metric-underwater').text(m.max_underwater_days + ' 天');
        $('#metric-utilization').text(m.avg_utilization + '%');
        
        // 压力测试指标
        $('#metric-max-util').text(m.max_utilization + '%');
        $('#metric-min-cash').text('¥' + Math.round(m.min_cash).toLocaleString());
        
        // 濒死预警
        if (m.max_utilization > 95) {
            $('#metric-max-util').addClass('text-danger');
            $('#util-warning').html('<i class="bi bi-exclamation-triangle-fill text-danger" title="警告：资金链濒临断裂！"></i>');
        } else {
            $('#metric-max-util').removeClass('text-danger');
            $('#util-warning').empty();
        }
        
        $('#metric-trades').text(m.trade_count);

        // 2. 绘制小收益曲线
        renderEquityChart(res.daily_curve);
        
        // 3. 绘制大复盘 K线图
        // 后端返回的是 daily_curve (含 open/close/high/low/equity)
        renderPriceChart(res);

        // 4. 填充交易明细
        const $tbody = $('#trades-table tbody');
        const $thead = $('#trades-table thead tr');
        
        // 更新表头
        $thead.html(`
            <th>时间 (分钟)</th>
            <th>方向</th>
            <th>成交价格</th>
            <th>数量</th>
            <th>持仓数量</th>
            <th>剩余现金</th>
            <th>账户总额</th>
        `);
        
        $tbody.empty();
        
        if (res.trades.length === 0) {
            $tbody.html('<tr><td colspan="7" class="text-muted">无交易记录</td></tr>');
        } else {
            // 正序显示 (时间由远到近)
            const tradesToShow = res.trades; 
            const limit = 2000;
            
            tradesToShow.slice(0, limit).forEach(t => {
                const isBuy = t.type.includes('BUY');
                const color = isBuy ? 'text-danger' : 'text-success'; // A股色
                
                $tbody.append(`
                    <tr>
                        <td>${formatTs(t.timestamp)}</td>
                        <td class="${color} fw-bold">${t.type}</td>
                        <td>${t.price.toFixed(3)}</td>
                        <td>${t.volume}</td>
                        <td>${t.total_shares.toLocaleString()}</td>
                        <td>${Math.round(t.cash).toLocaleString()}</td>
                        <td>${Math.round(t.total_equity).toLocaleString()}</td>
                    </tr>
                `);
            });
            if (tradesToShow.length > limit) {
                $tbody.append(`<tr><td colspan="7" class="text-muted">... 仅展示前 ${limit} 条记录，共 ${tradesToShow.length} 条 ...</td></tr>`);
            }
        }
    }

    function renderEquityChart(curveData) {
        const dom = document.getElementById('equity-chart');
        let myChart = echarts.getInstanceByDom(dom);
        if (myChart) myChart.dispose();
        myChart = echarts.init(dom);

        const dates = curveData.map(d => d.date);
        const equities = curveData.map(d => d.equity);
        const benchmarks = curveData.map(d => d.benchmark);

        const option = {
            title: { text: '收益曲线对比', left: 'center', textStyle: { fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            legend: { data: ['策略净值', '买入持有'], bottom: 0 },
            grid: { top: 40, left: 50, right: 30, bottom: 30 },
            xAxis: { type: 'category', data: dates },
            yAxis: { type: 'value', scale: true },
            series: [
                {
                    name: '策略净值',
                    type: 'line',
                    data: equities,
                    smooth: true,
                    lineStyle: { width: 2, color: '#0d6efd' },
                    showSymbol: false
                },
                {
                    name: '买入持有',
                    type: 'line',
                    data: benchmarks,
                    smooth: true,
                    lineStyle: { type: 'dashed', color: '#6c757d' },
                    showSymbol: false
                }
            ]
        };
        myChart.setOption(option);
    }

    function renderPriceChart(res) {
        const dom = document.getElementById('price-chart');
        let myChart = echarts.getInstanceByDom(dom);
        if (myChart) myChart.dispose();
        myChart = echarts.init(dom);
        
        const dates = res.daily_curve.map(d => d.date);
        const kData = res.daily_curve.map(d => [d.open, d.close, d.low, d.high]);
        const ma250 = res.daily_curve.map(d => (d.ma250 && d.ma250 > 0.001) ? d.ma250 : null);
        
        // 动态计算 Y 轴范围 (避免 0 把图压扁) -> 移除，改用 ECharts 自动缩放
        // 前提：确保 kData 里没有 0
        
        // 加上止损/止盈线 (MarkLine Data)
        const markLineData = [];
        const lowLimit = parseFloat($('#lower-limit').val());
        const upLimit = parseFloat($('#upper-limit').val());
        // 只有当非默认值时才画线
        if (lowLimit > 0.01) {
            markLineData.push({ yAxis: lowLimit, lineStyle: { color: '#ff4d4f', type: 'dashed' }, label: { formatter: '止损' } });
        }
        if (upLimit < 200.0) {
            markLineData.push({ yAxis: upLimit, lineStyle: { color: '#52c41a', type: 'dashed' }, label: { formatter: '清仓' } });
        }

        const buyPoints = [];
        const sellPoints = [];
        
        res.trades.forEach(t => {
            const dateStr = formatTs(t.timestamp).split(' ')[0];
            const isBuy = t.type.includes('BUY');
            if (isBuy) buyPoints.push([dateStr, t.price]);
            else sellPoints.push([dateStr, t.price]);
        });

        const option = {
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' }
            },
            legend: { 
                data: ['日K线', 'MA250 (年线)', '买入点', '卖出点'],
                top: 10
            },
            grid: { left: '3%', right: '3%', bottom: '15%' },
            xAxis: { type: 'category', data: dates, scale: true },
            yAxis: { 
                type: 'value', 
                scale: true // 自动缩放
            },
            dataZoom: [{ type: 'inside' }, { type: 'slider' }],
            series: [
                {
                    name: '日K线',
                    type: 'candlestick',
                    data: kData,
                    itemStyle: {
                        color: '#ef5350', // 阳线红
                        color0: '#26a69a', // 阴线绿
                        borderColor: '#ef5350',
                        borderColor0: '#26a69a'
                    },
                    markLine: {
                        symbol: ['none', 'none'],
                        data: markLineData
                    }
                },
                {
                    name: 'MA250 (年线)',
                    type: 'line',
                    data: ma250,
                    smooth: true,
                    showSymbol: false,
                    lineStyle: { width: 2, color: '#9c27b0', opacity: 0.8 } // 紫色年线
                },
                {
                    name: '买入点',
                    type: 'scatter',
                    data: buyPoints,
                    symbol: 'circle',
                    symbolSize: 15,
                    itemStyle: { color: '#2f54eb' }, // 宝蓝色
                    label: {
                        show: true,
                        formatter: 'B',
                        color: '#fff',
                        fontWeight: 'bold',
                        fontSize: 10
                    }
                },
                {
                    name: '卖出点',
                    type: 'scatter',
                    data: sellPoints,
                    symbol: 'circle',
                    symbolSize: 15,
                    itemStyle: { color: '#fa8c16' }, // 橙色
                    label: {
                        show: true,
                        formatter: 'S',
                        color: '#fff',
                        fontWeight: 'bold',
                        fontSize: 10
                    }
                }
            ]
        };
        myChart.setOption(option);
    }

    function renderHeatmap() {
        if (!currentHeatmapData) return;
        
        // 强制延迟以等待容器可见/布局完成
        setTimeout(() => {
            const res = currentHeatmapData;
            const metricKey = $('input[name="hm-metric"]:checked').val();
            const metricName = {
                'value': '夏普比率',
                'calmar': '卡玛比率',
                'ret': '总收益率'
            }[metricKey];

            const dom = document.getElementById('heatmap-chart');
            // 移除 clientWidth 检查，相信 setTimeout
            // if (dom.clientWidth === 0) return; 

            if (heatmapChart) heatmapChart.dispose();
            heatmapChart = echarts.init(dom);

            // ... (数据处理逻辑不变)
            let minVal = Infinity;
            let maxVal = -Infinity;
            const points = [];
            res.data.forEach((row, i) => {
                row.forEach((p, j) => {
                    const val = p[metricKey];
                    if (val !== null && val !== undefined && !isNaN(val)) {
                        if (val < minVal) minVal = val;
                        if (val > maxVal) maxVal = val;
                    }
                    points.push([j, i, val]);
                });
            });
            if (minVal === Infinity) { minVal = 0; maxVal = 1; }
            if (minVal === maxVal) { maxVal += 0.1; minVal -= 0.1; }

            // 寻找当前参数的位置 (You Are Here)
            const currentDensity = parseFloat($('#grid-density').val());
            const currentGap = parseFloat($('#sell-gap').val());
            
            let currentXIndex = -1;
            let currentYIndex = -1;
            
            // 简单的最近邻查找
            // x_axis: ["0.5%", "1.0%", ...]
            let minDiffX = Infinity;
            res.x_axis.forEach((label, idx) => {
                const val = parseFloat(label);
                const diff = Math.abs(val - currentGap);
                if (diff < minDiffX) {
                    minDiffX = diff;
                    currentXIndex = idx;
                }
            });
            
            let minDiffY = Infinity;
            res.y_axis.forEach((label, idx) => {
                const val = parseFloat(label);
                const diff = Math.abs(val - currentDensity);
                if (diff < minDiffY) {
                    minDiffY = diff;
                    currentYIndex = idx;
                }
            });
            
            const markData = [];
            // 只有当误差在合理范围内才显示标记 (比如 0.25 之内)
            if (currentXIndex !== -1 && currentYIndex !== -1 && minDiffX < 0.25 && minDiffY < 0.25) {
                // 获取该点的值用于 label
                // 需要遍历 points 找对应的值? 或者直接不显示值，只显示标记
                markData.push([currentXIndex, currentYIndex]);
            }
    
            const option = {
                title: { text: `参数热力图 (${metricName})`, left: 'center' },
                tooltip: { 
                    position: 'top',
                    formatter: function (params) {
                        if (params.seriesType === 'scatter') {
                            return `当前设置<br/>网格密度: ${currentDensity}%<br/>止盈间距: ${currentGap}%`;
                        }
                        const xIndex = params.data[0];
                        const yIndex = params.data[1];
                        const val = params.data[2];
                        const xLabel = res.x_axis[xIndex]; // Sell Gap
                        const yLabel = res.y_axis[yIndex]; // Grid Density
                        return `
                            <div><b>参数组合详情</b></div>
                            <div>网格密度: ${yLabel}</div>
                            <div>止盈间距: ${xLabel}</div>
                            <div>${metricName}: <b>${val}</b></div>
                        `;
                    }
                },
                grid: { height: '70%', top: '15%' },
                xAxis: {
                    type: 'category',
                    data: res.x_axis,
                    splitArea: { show: true },
                    name: 'Sell Gap'
                },
                yAxis: {
                    type: 'category',
                    data: res.y_axis,
                    splitArea: { show: true },
                    name: 'Grid Density'
                },
                visualMap: {
                    min: minVal,
                    max: maxVal,
                    calculable: true,
                    orient: 'horizontal',
                    left: 'center',
                    bottom: '5%',
                    precision: 2,
                    seriesIndex: [0], // 关键：只控制热力图，不控制散点图
                    inRange: {
                        color: ['#ff4d4f', '#fadb14', '#52c41a']
                    }
                },
                series: [
                    {
                        name: metricName,
                        type: 'heatmap',
                        data: points,
                        label: { show: true, formatter: (p) => p.data[2] },
                        emphasis: {
                            itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0, 0, 0, 0.5)' }
                        }
                    },
                    {
                        name: '当前参数',
                        type: 'scatter',
                        data: (currentXIndex !== -1 && currentYIndex !== -1 && minDiffX < 0.25 && minDiffY < 0.25) ? [[currentXIndex, currentYIndex]] : [],
                        symbol: 'star',
                        symbolSize: 20,
                        itemStyle: {
                            color: '#2f54eb', // 深蓝色
                            shadowBlur: 5,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        },
                        label: {
                            show: false
                        },
                        z: 10 // 确保在最上层
                    }
                ]
            };
            heatmapChart.setOption(option);
            heatmapChart.resize(); // 显式 resize
            
            // 监听点击事件：回填参数
            heatmapChart.off('click'); // 防止重复绑定
            heatmapChart.on('click', function (params) {
                if (params.seriesType === 'heatmap') {
                    const xIndex = params.data[0];
                    const yIndex = params.data[1];
                    const gapStr = res.x_axis[xIndex].replace('%', '');
                    const denStr = res.y_axis[yIndex].replace('%', '');
                    
                    $('#sell-gap').val(gapStr);
                    $('#grid-density').val(denStr);
                    
                    // 视觉反馈：闪烁输入框
                    $('#sell-gap, #grid-density').addClass('bg-warning bg-opacity-25');
                    setTimeout(() => {
                        $('#sell-gap, #grid-density').removeClass('bg-warning bg-opacity-25');
                    }, 500);
                    
                    // 立即重绘热力图，更新五角星位置
                    renderHeatmap();
                }
            });
        }, 100);
    }

    function formatTs(ts) {
        // ts: YYYYMMDDHHMM
        if (ts.length < 12) return ts;
        return `${ts.substring(0,4)}-${ts.substring(4,6)}-${ts.substring(6,8)} ${ts.substring(8,10)}:${ts.substring(10,12)}`;
    }

    function showLoading(text) {
        $('#loading-text').text(text);
        $('#loading-overlay').removeClass('d-none').addClass('d-flex');
    }

    function hideLoading() {
        $('#loading-overlay').addClass('d-none').removeClass('d-flex');
    }
});