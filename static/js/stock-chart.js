class StockChart {
    constructor() {
        this.initModal();
    }

    initModal() {
        const modalHtml = `
        <div class="modal fade" id="stock-chart-modal" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-resizable" style="max-width: 80vw; margin: 20px auto;">
                <div class="modal-content" style="height: 80vh;">
                    <div class="modal-header py-2">
                        <h5 class="modal-title"></h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body p-0">
                        <div id="stock-chart-container" style="height: calc(80vh - 45px);"></div>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // 初始化可调整大小功能
        const dialog = document.querySelector('#stock-chart-modal .modal-dialog');
        // $(dialog).resizable({
        //     handles: 'n, e, s, w, ne, se, sw, nw',
        //     minWidth: 300,
        //     minHeight: 200,
        //     resize: (event, ui) => {
        //         const container = ui.element.find('#stock-chart-container');
        //         container.css('height', ui.size.height - 45);
        //     }
        // });
        // $(dialog).draggable();
        
        // 确保在设置 this.modal 之前 Bootstrap 已加载
        if (typeof bootstrap !== 'undefined') {
            this.modal = new bootstrap.Modal(document.getElementById('stock-chart-modal'));
        } else {
            console.error('Bootstrap is not loaded');
        }
    }

    showChart(symbol, options = [], button) {
        const modalTitle = document.querySelector('#stock-chart-modal .modal-title');
        modalTitle.textContent = `${symbol} 股票走势图`;

        // 先清空图表容器
        const container = document.getElementById('stock-chart-container');
        container.innerHTML = `
            <div class="d-flex justify-content-center align-items-center h-100">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
            </div>`;

        // 先显示模态框
        this.modal.show();

        // 获取当前行的价格输入框
        const row = button.closest('tr');
        const priceCell = row.querySelector('td:nth-child(3)'); // 价格在第3列
        const priceInput = priceCell.querySelector('input');
        
        let currentPrice = null;
        if (priceInput) {
            currentPrice = parseFloat(priceInput.value);
        }

        // 获取价格数据
        const url = `/api/price_range/${symbol}${currentPrice ? `?current_price=${currentPrice}` : ''}`;
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                // 清空加载动画
                container.innerHTML = '';
                
                const chartData = data.dates.map((date, index) => [
                    new Date(date).getTime(),
                    data.closes[index]
                ]);

                // 创建期权行权价系列
                const strikeSeries = options.map(opt => ({
                    name: `${opt.put_call} ${opt.strike}`,
                    type: 'line',
                    data: [
                        [chartData[0][0], opt.strike],
                        [chartData[chartData.length - 1][0], opt.strike]
                    ],
                    color: opt.put_call === 'CALL' ? '#00FF00' : '#FF0000',  // 更鲜艳的颜色
                    dashStyle: 'Solid',  // 改为实线
                    lineWidth: 2,  // 加粗线条
                    marker: { enabled: false },
                    showInLegend: true,  // 在图例中显示
                    enableMouseTracking: false  // 禁用鼠标跟踪，避免与主图表交互冲突
                }));

                // 创建图表
                Highcharts.chart('stock-chart-container', {
                    title: {
                        text: null
                    },
                    chart: {
                        type: 'line',
                        zoomType: 'xy',
                        panning: true,
                        panKey: 'shift',
                        events: {
                            load: function() {
                                const chart = this;
                                const container = chart.container;

                                function handleMouseMove(e) {
                                    const rect = container.getBoundingClientRect();
                                    const x = e.clientX - rect.left;
                                    const y = e.clientY - rect.top;

                                    // 确保鼠标在绘图区域内
                                    if (x >= chart.plotLeft && x <= chart.plotLeft + chart.plotWidth &&
                                        y >= chart.plotTop && y <= chart.plotTop + chart.plotHeight) {
                                        
                                        const yValue = chart.yAxis[0].toValue(y - chart.plotTop);

                                        // 创建或更新价格标签
                                        if (!chart.priceLabel) {
                                            chart.priceLabel = chart.renderer.label('', 0, 0)
                                                .css({
                                                    fontSize: '12px',
                                                    padding: '5px',
                                                    backgroundColor: 'rgba(255, 255, 255, 0.9)',
                                                    border: '1px solid #888888',
                                                    borderRadius: '3px'
                                                })
                                                .attr({
                                                    zIndex: 101,
                                                    padding: 5
                                                })
                                                .add();
                                        }

                                        // 更新价格标签的位置和内容
                                        chart.priceLabel
                                            .attr({
                                                text: `价格: ${Highcharts.numberFormat(yValue, 2)}`
                                            })
                                            .translate(
                                                chart.plotLeft - 100,  // x位置
                                                y - 10  // y位置
                                            );

                                        // 创建或更新水平线
                                        if (!chart.hLine) {
                                            chart.hLine = chart.renderer.path()
                                                .attr({
                                                    'stroke-width': 1,
                                                    stroke: '#888888',
                                                    zIndex: 100,
                                                    dashstyle: 'solid'
                                                })
                                                .add();
                                        }

                                        chart.hLine.attr({
                                            d: ['M', chart.plotLeft, y, 'L', chart.plotLeft + chart.plotWidth, y]
                                        });

                                        // 显示元素
                                        chart.priceLabel.show();
                                        chart.hLine.show();
                                    }
                                }

                                function handleMouseOut() {
                                    if (chart.priceLabel) {
                                        chart.priceLabel.hide();
                                    }
                                    if (chart.hLine) {
                                        chart.hLine.hide();
                                    }
                                }

                                // 添加事件监听器
                                container.addEventListener('mousemove', handleMouseMove);
                                container.addEventListener('mouseleave', handleMouseOut);
                            }
                        }
                    },
                    tooltip: {
                        enabled: false
                    },
                    series: [
                        {
                            name: symbol,
                            data: chartData,
                            color: '#67B8F7',
                            zIndex: 2,
                            stickyTracking: false
                        },
                        // 添加最新价格线
                        ...(currentPrice ? [{
                            name: '最新价格',
                            type: 'line',
                            data: [
                                [chartData[0][0], currentPrice],
                                [chartData[chartData.length - 1][0], currentPrice]
                            ],
                            color: '#000000',
                            dashStyle: 'Dash',
                            lineWidth: 1,
                            marker: { enabled: false },
                            showInLegend: true,
                            enableMouseTracking: false
                        }] : []),
                        ...strikeSeries
                    ],
                    plotOptions: {
                        series: {
                            animation: false,
                            states: {
                                hover: {
                                    enabled: false
                                },
                                inactive: {
                                    opacity: 1  // 保持不活跃状态时的不透明度
                                }
                            },
                            events: {
                                mouseOver: function() {
                                    if (this.name !== symbol) {  // 只对行权价线处理
                                        this.update({
                                            opacity: 1
                                        }, false);
                                    }
                                },
                                mouseOut: function() {
                                    if (this.name !== symbol) {  // 只对行权价线处理
                                        this.update({
                                            opacity: 1
                                        }, false);
                                    }
                                }
                            }
                        }
                    }
                });
            });

        this.modal.show();
    }
}

// 创建全局实例
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.stockChart = new StockChart();
    });
} else {
    window.stockChart = new StockChart();
}