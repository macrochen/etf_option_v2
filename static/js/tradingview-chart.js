// TradingView 图表管理器
class TradingViewChart {
    constructor() {
        // Wait for DOM to be ready before initializing
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.initModal());
        } else {
            this.initModal();
        }
    }

    initModal() {
        const modalHtml = `
        <div class="modal fade" id="tradingview-modal" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog" style="max-width: 95vw; margin: 10px auto;">
                <div class="modal-content" style="height: 95vh;">
                    <div class="modal-header py-2">
                        <h5 class="modal-title"></h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body p-0">
                        <div id="tradingview-container" style="height: calc(95vh - 45px);"></div>
                    </div>
                </div>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        this.modal = new bootstrap.Modal(document.getElementById('tradingview-modal'));
    }

    showChart(symbol, options = []) {
        const modalTitle = document.querySelector('#tradingview-modal .modal-title');
        modalTitle.textContent = `${symbol} 股票图表`;
        
        const container = document.getElementById('tradingview-container');
        container.innerHTML = '';

        new TradingView.widget({
            "width": "100%",
            "height": "100%",
            "symbol": `${this.getExchangePrefix(symbol)}:${symbol}`,
            "interval": "D",
            "timezone": "Asia/Shanghai",
            "theme": "light",
            "style": "1",
            "locale": "zh_CN",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "container_id": "tradingview-container",
            "save_image": false,
            "hide_top_toolbar": false,
            "studies": [
                "MASimple@tv-basicstudies",
                "Volume@tv-basicstudies"
            ],
            "overrides": {
                "mainSeriesProperties.style": 1,
                "mainSeriesProperties.candleStyle.upColor": "#26a69a",
                "mainSeriesProperties.candleStyle.downColor": "#ef5350",
                "mainSeriesProperties.candleStyle.drawWick": true,
                "mainSeriesProperties.candleStyle.drawBorder": true,
                "mainSeriesProperties.candleStyle.borderColor": "#378658",
                "mainSeriesProperties.candleStyle.borderUpColor": "#26a69a",
                "mainSeriesProperties.candleStyle.borderDownColor": "#ef5350",
                "mainSeriesProperties.candleStyle.wickUpColor": "#26a69a",
                "mainSeriesProperties.candleStyle.wickDownColor": "#ef5350"
            },
            "loading_screen": { backgroundColor: "#ffffff" },
            "custom_css_url": "https://s3.tradingview.com/chart.css",
            "library_path": "https://s3.tradingview.com/charting_library/",
            "charts_storage_url": "https://saveload.tradingview.com",
            "client_id": "tradingview.com",
            "user_id": "public_user",
            "auto_save_delay": 5
        });

        // 延长等待时间以确保图表完全加载
        setTimeout(() => {
            this.modal.show();
        }, 1000);
    }

    getExchangePrefix(symbol) {
        if (/^\d{5}$/.test(symbol)) {
            return 'HK';  // 港股
        }
        
        // 纳斯达克常见特征：
        // 1. 4个字母或更少（AAPL, META, MSFT, AMZN等）
        // 2. 以 'Z', 'Q', 'X' 结尾的股票代码
        if (/^[A-Z]{1,4}$/.test(symbol) || /[ZQX]$/.test(symbol)) {
            return 'NASDAQ';
        }
        
        // 纽交所常见特征：
        // 1. 通常是3个字母或更少（IBM, GE等）
        // 2. 可能包含点号（BRK.A, BRK.B等）
        return 'NYSE';
    }
}

// Create global instance only after DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.tradingViewChart = new TradingViewChart();
    });
} else {
    window.tradingViewChart = new TradingViewChart();
}