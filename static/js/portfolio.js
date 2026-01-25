// Global State
let portfolioData = null;
let currentChartType = 'category_1';
let myChart = null;
let trendChart = null; 
let allAccounts = [];
let currentSort = { field: 'update_time', asc: false }; 
let currentFilters = {}; 
let isSensitiveHidden = true;

// Utility Functions
function formatCurrency(num) {
    return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(num);
}

function formatNumber(num) {
    return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(num);
}

function determineAssetType(cat1, symbol) {
    if (cat1 === '现金类') return 'cash';
    if (cat1 === '权益类' || cat1 === '固收类' || cat1 === '商品类') {
        if (symbol.startsWith('1') || symbol.startsWith('5')) return 'etf';
        if (symbol.length === 6 && (symbol.startsWith('6') || symbol.startsWith('0') || symbol.startsWith('3') || symbol.startsWith('8') || symbol.startsWith('4'))) return 'stock';
        return 'fund';
    }
    return 'other';
}

// UI Toggles
function toggleSensitivity() {
    isSensitiveHidden = !isSensitiveHidden;
    const btn = $('#toggleSensitiveBtn');
    if (isSensitiveHidden) {
        btn.html('<i class="fas fa-eye-slash"></i>');
    } else {
        btn.html('<i class="fas fa-eye"></i>');
    }
    updateDashboard();
}

function toggleBatchDeleteBtn() {
    const count = $('.asset-select:checked').length;
    const btn = $('#btnBatchDelete');
    if (count > 0) {
        btn.show().html('<i class="fas fa-trash"></i> 批量删除 (' + count + ')');
    } else {
        btn.hide();
    }
}

// Charting
function initChart() {
    const chartDom = document.getElementById('portfolioChart');
    if (chartDom) {
        myChart = echarts.init(chartDom);
    }
    const trendDom = document.getElementById('trendChart');
    if (trendDom) {
        trendChart = echarts.init(trendDom);
    }
    
    window.addEventListener('resize', function() {
        if (myChart) myChart.resize();
        if (trendChart) trendChart.resize();
    });
}

function updateChart() {
    if (!portfolioData || !myChart) return; 
    
    let data = [];
    let title = '';
    
    switch(currentChartType) {
        case 'category_1':
            data = portfolioData.summary.by_category_1;
            title = '按一级分类';
            break;
        case 'category_2':
            data = portfolioData.summary.by_category_2;
            title = '按二级分类';
            break;
        case 'account':
            data = portfolioData.summary.by_account;
            title = '按账户分布';
            break;
        case 'asset_type':
            data = portfolioData.summary.by_asset_type;
            title = '按资产形态';
            break;
    }
    
    const option = {
        title: { text: title, left: 'center' },
        tooltip: {
            trigger: 'item',
            formatter: function(params) {
                return params.name + '<br/>市值: <b>¥' + params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) + '</b> (' + params.percent + '%)';
            }
        },
        legend: { orient: 'vertical', left: 'left' },
        series: [
            {
                name: '资产分布',
                type: 'pie',
                radius: ['40%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
                label: { show: false, position: 'center' },
                emphasis: {
                    label: {
                        show: true,
                        fontSize: 20,
                        fontWeight: 'bold',
                        formatter: function(params) {
                            return params.name + '\n¥' + params.value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                        }
                    }
                },
                labelLine: { show: false },
                data: data
            }
        ]
    };
    
    myChart.setOption(option);
}

function switchChart(type) {
    currentChartType = type;
    $('.btn-group .btn').removeClass('active');
    $(`.btn-group .btn[onclick="switchChart('${type}')"]`).addClass('active');
    updateChart();
}

function updateTrendChart() {
    if (!portfolioData || !portfolioData.history || !trendChart) return; 
    
    const dates = portfolioData.history.map(h => h.week);
    const assets = portfolioData.history.map(h => h.total_assets);
    const costs = portfolioData.history.map(h => h.total_cost);
    
    const option = {
        tooltip: {
            trigger: 'axis',
            formatter: function(params) {
                let res = params[0].name + '<br/>';
                params.forEach(item => {
                    res += item.marker + item.seriesName + ': ' + formatCurrency(item.value) + '<br/>';
                });
                return res;
            }
        },
        legend: { data: ['总资产', '总本金'], bottom: 0 },
        grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: dates },
        yAxis: { 
            type: 'value',
            axisLabel: { formatter: function(value) { return (value / 10000).toFixed(0) + '万'; } }
        },
        series: [
            {
                name: '总资产',
                type: 'line',
                data: assets,
                smooth: true,
                areaStyle: { opacity: 0.1 },
                itemStyle: { color: '#0d6efd' }
            },
            {
                name: '总本金',
                type: 'line',
                data: costs,
                smooth: true,
                itemStyle: { color: '#0dcaf0' },
                lineStyle: { type: 'dashed' }
            }
        ]
    };
    
    trendChart.setOption(option);
}

// Data Handling
function refreshData() {
    $.get('/api/portfolio/data', function(res) {
        portfolioData = res;
        updateDashboard();
        sortAndRenderTable();
        updateChart();
        updateTrendChart();
        updateTopMovers();
        updateDatalists();
    }).fail(function(err) {
        console.error("Load data failed", err);
        $('#totalAssets, #totalPnL, #totalCost').text('加载失败');
    });
}

function refreshPrices() {
    const btn = $('#btnRefreshPrices');
    const originalContent = btn.html();
    btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> 更新中...');
    
    $.ajax({
        url: '/api/portfolio/refresh_prices',
        type: 'POST',
        success: function(res) {
            alert(`行情更新完成！\n成功更新了 ${res.updated_count} 个资产的价格。`);
            refreshData(); 
        },
        error: function(err) {
            alert('更新失败: ' + (err.responseJSON ? err.responseJSON.message : err.statusText));
        },
        complete: function() {
            btn.prop('disabled', false).html(originalContent);
        }
    });
}

function updateDashboard() {
    if (!portfolioData) return; 
    const sum = portfolioData.summary;
    
    if (isSensitiveHidden) {
        $('#totalAssets').text('******');
        $('#totalCost').text('******');
        $('#totalPnL').text('******');
    } else {
        $('#totalAssets').text(formatCurrency(sum.total_assets));
        $('#totalCost').text(formatCurrency(sum.total_cost));
        $('#totalPnL').text(formatCurrency(sum.total_pnl));
    }
    
    const pnlClass = sum.total_pnl >= 0 ? 'bg-danger' : 'bg-success';
    $('#totalPnL').parent().parent().removeClass('bg-success bg-danger').addClass(pnlClass);
}

function updateTopMovers() {
    if (!portfolioData || !portfolioData.assets) return; 
    
    const sorted = [...portfolioData.assets]
        .filter(a => a.pnl_percent < 999999)
        .sort((a, b) => b.pnl_percent - a.pnl_percent);
    
    const top3 = sorted.slice(0, 3);
    const bottom3 = sorted.slice(-3).reverse();
    
    const list = $('#topMoversList');
    list.empty();
    
    const createItem = (asset, type) => `
        <li class="list-group-item d-flex justify-content-between align-items-center">
            <div>
                <span class="badge ${type === 'win' ? 'bg-danger' : 'bg-success'} rounded-pill me-2">
                    ${type === 'win' ? 'Top' : 'Low'}
                </span>
                <small>${asset.name || asset.symbol}</small>
            </div>
            <span class="${type === 'win' ? 'text-danger' : 'text-success'} fw-bold">
                ${asset.pnl_percent.toFixed(2)}%
            </span>
        </li>
    `;
    
    top3.forEach(a => list.append(createItem(a, 'win')));
    bottom3.forEach(a => list.append(createItem(a, 'loss')));
}

function updateDatalists() {
    if (!portfolioData) return; 
    
    const defaultCat2 = [
        '宽基', '行业', '红利', '策略', 'QDII', '个股', '科技', '消费', '医药', '金融', '新能源',
        '利率债', '信用债', '可转债', '理财',
        '黄金', '原油', 'REITs', '豆粕',
        '货币', '存款'
    ];
    const cat2s = new Set(defaultCat2);
    
    portfolioData.assets.forEach(a => {
        if (a.category_2) cat2s.add(a.category_2);
    });
    
    const list = $('#cat2List');
    list.empty();
    cat2s.forEach(val => {
        list.append(`<option value="${val}">`);
    });
}

// Table & Filtering
function sortAndRenderTable() {
    if (!portfolioData || !portfolioData.assets) return; 
    
    let data = portfolioData.assets.filter(item => {
        for (const [col, filterVal] of Object.entries(currentFilters)) {
            if (!filterVal) continue; 
            
            if (col === 'name') {
                const name = (item.name || '').toLowerCase();
                const symbol = (item.symbol || '').toLowerCase();
                if (!name.includes(filterVal) && !symbol.includes(filterVal)) return false;
            } else {
                const val = String(item[col] || '').toLowerCase();
                if (!val.includes(filterVal)) return false;
            }
        }
        return true;
    });
    
    const field = currentSort.field;
    const isAsc = currentSort.asc;
    
    data.sort((a, b) => {
        let valA = a[field];
        let valB = b[field];
        
        if (valA === null || valA === undefined) valA = '';
        if (valB === null || valB === undefined) valB = '';
        
        if (typeof valA === 'string') {
            return isAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return isAsc ? valA - valB : valB - valA;
    });
    
    updateTable(data);
}

function updateTable(data) {
    const tbody = $('#assetTable tbody');
    tbody.empty();
    
    $('#selectAllAssets').prop('checked', false);
    toggleBatchDeleteBtn();
    
    const assets = data || (portfolioData ? portfolioData.assets : []);
    if (!assets || assets.length === 0) {
        tbody.html('<tr><td colspan="11" class="text-center text-muted">无数据</td></tr>');
        return;
    }
    
    assets.forEach(asset => {
        const pnlClass = asset.pnl >= 0 ? 'text-danger' : 'text-success';
        const row = `
            <tr>
                <td><input class="form-check-input asset-select" type="checkbox" value="${asset.id}"></td>
                <td>${asset.account_name}</td>
                <td>
                    <div>${asset.name || '-'}</div>
                    <small class="text-muted">${asset.symbol}</small>
                </td>
                <td>${asset.category_1 || '-'}</td>
                <td>${asset.category_2 || '-'}</td>
                <td>${asset.quantity}</td>
                <td>${formatNumber(asset.cost_price)}</td>
                <td>${formatNumber(asset.current_price)}</td>
                <td>${formatNumber(asset.market_value)}</td>
                <td class="${pnlClass}">
                    <div>${formatNumber(asset.pnl)}</div>
                    <small>(${asset.pnl_percent >= 999999 ? '∞' : asset.pnl_percent.toFixed(2) + '%'})</small>
                </td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick='editAsset(${JSON.stringify(asset)})'>
                        <i class="fas fa-edit"></i>
                    </button>
                </td>
            </tr>
        `;
        tbody.append(row);
    });
}

// Account & Asset Management
function loadAccounts() {
    $.get('/api/portfolio/accounts', function(res) {
        allAccounts = res;
        const tbody = $('#accountTable tbody');
        tbody.empty();
        
        res.forEach(acc => {
            const row = `
                <tr>
                    <td>${acc.name}</td>
                    <td>${acc.type || '-'}</td>
                    <td>${acc.description || '-'}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick='editAccount(${JSON.stringify(acc)})'>
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteAccount(${acc.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
            tbody.append(row);
        });
    });
}

function refreshAccountOptions() {
    $.get('/api/portfolio/accounts', function(res) {
        console.log("Accounts loaded:", res); 
        allAccounts = res;
        
        const filterSelect = $('#filterAccount');
        const filterVal = filterSelect.val();
        filterSelect.empty();
        filterSelect.append('<option value="">全部</option>'); 
        
        if (res && res.length > 0) {
            res.forEach(acc => {
                filterSelect.append(`<option value="${acc.name}">${acc.name}</option>`);
            });
        }
        
        const assetSelect = $('#accountName');
        const batchSelect = $('#batchAccount');
        const currentVal = assetSelect.val();
        const batchVal = batchSelect.val();
        
        assetSelect.empty();
        batchSelect.empty();
        
        if (!res || res.length === 0) {
             assetSelect.append('<option value="">无账户，请先创建</option>');
             batchSelect.append('<option value="">无账户，请先创建</option>');
        } else {
             res.forEach(acc => {
                 assetSelect.append(`<option value="${acc.name}">${acc.name}</option>`);
                 batchSelect.append(`<option value="${acc.name}">${acc.name} (${acc.type || '-'})</option>`);
             });
        }

        if (currentVal) assetSelect.val(currentVal);
        if (batchVal) batchSelect.val(batchVal);
        if (filterVal) filterSelect.val(filterVal);
    });
}

function showAddAccountModal() {
    $('#accountModalTitle').text('新增账户');
    $('#accountId').val('');
    document.getElementById('accountForm').reset();
    $('#accountListModal').modal('hide');
    new bootstrap.Modal(document.getElementById('accountEditModal')).show();
}

function editAccount(acc) {
    $('#accountModalTitle').text('编辑账户');
    $('#accountId').val(acc.id);
    $('#accName').val(acc.name);
    $('#accType').val(acc.type);
    $('#accDesc').val(acc.description);
    
    $('#accountListModal').modal('hide');
    new bootstrap.Modal(document.getElementById('accountEditModal')).show();
}

function saveAccount() {
    const data = {
        id: $('#accountId').val() || null,
        name: $('#accName').val(),
        type: $('#accType').val(),
        description: $('#accDesc').val()
    };
    
    $.ajax({
        url: '/api/portfolio/account',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(res) {
            $('#accountEditModal').modal('hide');
            new bootstrap.Modal(document.getElementById('accountListModal')).show();
            loadAccounts(); 
            refreshAccountOptions(); // Update selects
        },
        error: function(err) {
            alert('保存失败: ' + err.responseJSON.message);
        }
    });
}

function deleteAccount(id) {
    if (confirm('确定要删除这个账户吗？')) {
        $.ajax({
            url: `/api/portfolio/account/${id}`,
            type: 'DELETE',
            success: function() {
                loadAccounts();
                refreshAccountOptions(); // Update selects
            },
            error: function() {
                alert('删除失败');
            }
        });
    }
}

// Asset CRUD
function showAssetModal() {
    // Helper to clear form
    $('#modalTitle').text('新增资产');
    $('#assetId').val('');
    $('#assetType').val('');
    document.getElementById('assetForm').reset();
    $('#currentPrice').val('');
}

function editAsset(asset) {
    $('#modalTitle').text('编辑资产');
    $('#assetId').val(asset.id);
    $('#accountName').val(asset.account_name);
    $('#assetType').val(asset.asset_type);
    $('#category1').val(asset.category_1);
    $('#category2').val(asset.category_2);
    $('#symbol').val(asset.symbol);
    $('#name').val(asset.name);
    $('#quantity').val(asset.quantity);
    $('#costPrice').val(asset.cost_price);
    $('#currentPrice').val(asset.last_price || ''); 
    
    new bootstrap.Modal(document.getElementById('assetModal')).show();
}

function saveAsset() {
    const accountName = $('#accountName').val();
    const symbol = $('#symbol').val().trim();
    const name = $('#name').val().trim();
    const quantity = $('#quantity').val();
    const costPrice = $('#costPrice').val();
    
    if (!accountName) return alert('请选择账户');
    if (!symbol && !name) return alert('请填写代码或名称');
    if (!quantity) return alert('请填写持有数量');
    if (!costPrice) return alert('请填写成本价');

    const cat1 = $('#category1').val();
    
    // Auto-generate symbol 
    let finalSymbol = symbol;
    if (!finalSymbol && name) {
        const hash = name.split('').reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0);
        finalSymbol = 'TG_' + Math.abs(hash).toString(16).toUpperCase();
    }
    
    let aType = $('#assetType').val();
    if (!aType) {
        aType = determineAssetType(cat1, finalSymbol);
    }

    const data = {
        id: $('#assetId').val() || null,
        account_name: accountName,
        asset_type: aType,
        category_1: cat1,
        category_2: $('#category2').val(),
        symbol: finalSymbol,
        name: name,
        quantity: parseFloat(quantity),
        cost_price: parseFloat(costPrice),
        last_price: parseFloat($('#currentPrice').val()) || 0
    };
    
    $.ajax({
        url: '/api/portfolio/asset',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(res) {
            $('#assetModal').modal('hide');
            refreshData();
            document.getElementById('assetForm').reset();
            $('#assetId').val(''); 
        },
        error: function(err) {
            alert('保存失败: ' + err.responseJSON.message);
        }
    });
}

function batchDeleteAssets() {
    const ids = [];
    $('.asset-select:checked').each(function() {
        ids.push($(this).val());
    });
    
    if (ids.length === 0) return; 
    
    if (!confirm(`确定要删除选中的 ${ids.length} 条资产记录吗？此操作不可恢复。`)) return;
    
    const btn = $('#btnBatchDelete');
    btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> 删除中...');
    
    let failed = 0;
    
    const promises = ids.map(id => {
        return new Promise(resolve => {
            $.ajax({
                url: `/api/portfolio/asset/${id}`,
                type: 'DELETE',
                success: () => resolve(true),
                error: () => {
                    failed++;
                    resolve(false);
                }
            });
        });
    });
    
    Promise.all(promises).then(() => {
        btn.prop('disabled', false);
        if (failed > 0) {
            alert(`删除完成。失败: ${failed}`);
        }
        refreshData();
    });
}

// Markdown Import
function appendAssetRow(asset) {
    const index = Date.now() + Math.floor(Math.random() * 1000); 
    const row = `
        <tr id="ocr-row-${index}">
            <td><input type="text" class="form-control form-control-sm asset-name" value="${asset.name || ''}"></td>
            <td><input type="text" class="form-control form-control-sm asset-symbol" value="${asset.symbol || ''}"></td>
            <td><input type="text" class="form-control form-control-sm asset-cat2" value="${asset.cat2 || ''}" placeholder="二级分类" list="cat2List"></td>
            <td><input type="number" class="form-control form-control-sm asset-qty" value="${asset.qty || ''}"></td>
            <td><input type="number" class="form-control form-control-sm asset-cost" value="${asset.cost || ''}"></td>
            <td><input type="number" class="form-control form-control-sm asset-last-price" value="${asset.lastPrice || ''}"></td>
            <td>
                <button class="btn btn-sm btn-outline-danger border-0" onclick="$(this).closest('tr').remove()" title="删除">
                    <i class="fas fa-times"></i>
                </button>
            </td>
        </tr>
    `;
    $('#ocrTable tbody').append(row);
}

function parseMarkdownInput() {
    const text = $('#mdInput').val().trim();
    if (!text) return alert('请粘贴 Markdown 表格内容');
    
    const lines = text.split('\n').filter(line => line.trim() && line.includes('|'));
    if (lines.length < 2) return alert('未识别到有效的 Markdown 表格');
    
    const headerLine = lines[0];
    const headers = headerLine.split('|').map(h => h.trim()).filter(h => h);
    
    const mapping = {};
    headers.forEach((h, index) => {
        if (h.includes('代码') || h.includes('Symbol')) mapping[index] = 'symbol';
        else if (h.includes('名称') || h.includes('Name')) mapping[index] = 'name';
        else if (h.includes('数量') || h.includes('Qty') || h.includes('持仓')) mapping[index] = 'qty';
        else if (h.includes('成本') || h.includes('Cost')) mapping[index] = 'cost';
        else if (h.includes('现价') || h.includes('Price') || h.includes('最新')) mapping[index] = 'lastPrice';
        else if (h.includes('二级') || h.includes('分类') || h.includes('Type')) mapping[index] = 'cat2';
    });
    
    let addedCount = 0;
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        if (line.includes('---')) continue; 
        
        const cleanLine = line.replace(/^\|\|\|$/g, '');
        const values = cleanLine.split('|').map(c => c.trim());
        
        if (values.length < headers.length) continue; 
        
        const asset = {};
        let hasData = false;
        
        Object.keys(mapping).forEach(colIndex => {
            if (values[colIndex]) {
                let val = values[colIndex];
                const field = mapping[colIndex];
                if (['qty', 'cost', 'lastPrice'].includes(field)) {
                    val = val.replace(/[¥$,]/g, '');
                }
                asset[field] = val;
                hasData = true;
            }
        });
        
        if (hasData) {
            if (!asset.symbol && asset.name) {
                const hash = asset.name.split('').reduce((a,b)=>{a=((a<<5)-a)+b.charCodeAt(0);return a&a},0);
                asset.symbol = 'TG_' + Math.abs(hash).toString(16).toUpperCase();
            }
            
            if (asset.symbol) {
                appendAssetRow(asset);
                addedCount++;
            }
        }
    }
    
    if (addedCount > 0) {
        alert(`🎉 成功解析并添加了 ${addedCount} 条资产记录！\n请在下方列表确认无误后，点击“全部导入”按钮保存。`);
        $('#mdInput').val(''); 
        $('#ocrResult').show(); 
        $('#markdownArea').collapse('hide');
    } else {
        alert('未解析到有效数据，请检查 Markdown 格式');
    }
}

function importAllAssets() {
    const rows = $('#ocrTable tbody tr');
    if (rows.length === 0) return alert('列表为空');
    
    const accountName = $('#batchAccount').val(); 
    const cat1 = $('#batchCategory1').val();
    
    if (!accountName) return alert('请先设置【归属账户】');
    
    const assets = [];
    rows.each(function() {
        const row = $(this);
        const symbol = row.find('.asset-symbol').val().trim();
        const cat2 = row.find('.asset-cat2').val().trim();
        const name = row.find('.asset-name').val().trim();
        
        assets.push({
            account_name: accountName,
            category_1: cat1,
            category_2: cat2,
            symbol: symbol,
            name: name,
            quantity: parseFloat(row.find('.asset-qty').val()) || 0,
            cost_price: parseFloat(row.find('.asset-cost').val()) || 0,
            last_price: parseFloat(row.find('.asset-last-price').val()) || 0,
            asset_type: determineAssetType(cat1, symbol)
        });
    });
    
    if (!confirm(`确认导入这 ${assets.length} 条资产到账户 [${accountName}] 吗？`)) return;
    
    const btn = $('button[onclick="importAllAssets()"]');
    const originalText = btn.html();
    btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> 正在导入...');
    
    let successCount = 0;
    let failCount = 0;
    
    assets.reduce((promise, asset) => {
        return promise.then(() => {
            return new Promise((resolve) => {
                $.ajax({
                    url: '/api/portfolio/asset',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify(asset),
                    success: function() { successCount++; resolve(); },
                    error: function() { failCount++; resolve(); }
                });
            });
        });
    }, Promise.resolve()).then(() => {
        btn.prop('disabled', false).html(originalText);
        alert(`导入完成！成功: ${successCount}, 失败: ${failCount}`);
        
        if (successCount > 0) {
            $('#importModal').modal('hide');
            refreshData(); 
            $('#ocrTable tbody').empty();
        }
    });
}

function showLedgerModal() {
    if (!portfolioData || !portfolioData.summary) return alert('请先加载数据');
    
    const accounts = portfolioData.summary.by_account;
    const tbody = $('#ledgerTable tbody');
    tbody.empty();
    
    let totalSynced = 0;
    const sortedAccounts = [...accounts].sort((a, b) => b.value - a.value);
    
    sortedAccounts.forEach(acc => {
        const rawValue = acc.value;
        const syncedValue = Math.floor(rawValue / 100) * 100;
        totalSynced += syncedValue;
        const displayValue = syncedValue.toLocaleString('zh-CN', { maximumFractionDigits: 0 });
        tbody.append(`
            <tr>
                <td>${acc.name}</td>
                <td class="text-end font-monospace fs-5">${displayValue}</td>
            </tr>
        `);
    });
    
    $('#ledgerTotal').text(totalSynced.toLocaleString('zh-CN', { maximumFractionDigits: 0 }));
    new bootstrap.Modal(document.getElementById('ledgerModal')).show();
}

// Initialization
$(document).ready(function() {
    refreshData();
    initChart();
    refreshAccountOptions(); 
    
    $('#assetTable thead th[data-sort]').on('click', function() {
        const field = $(this).data('sort');
        if (currentSort.field === field) {
            currentSort.asc = !currentSort.asc;
        } else {
            currentSort.field = field;
            currentSort.asc = true;
        }
        $('#assetTable thead th i').removeClass('fa-sort-up fa-sort-down').addClass('fa-sort');
        $(this).find('i').removeClass('fa-sort').addClass(currentSort.asc ? 'fa-sort-up' : 'fa-sort-down');
        sortAndRenderTable();
    });
    
    $('.column-filter').on('input change', function() {
        const col = $(this).data('col');
        const val = $(this).val().toLowerCase().trim();
        currentFilters[col] = val;
        sortAndRenderTable();
    });
    
    $('#selectAllAssets').change(function() {
        $('.asset-select').prop('checked', $(this).is(':checked'));
        toggleBatchDeleteBtn();
    });

    $('#assetTable tbody').on('change', '.asset-select', function() {
        const allChecked = $('.asset-select:checked').length === $('.asset-select').length;
        $('#selectAllAssets').prop('checked', allChecked);
        toggleBatchDeleteBtn();
    });
    
    $('#accountListModal').on('show.bs.modal', function () {
        loadAccounts();
    });
    
    $('#assetModal').on('show.bs.modal', function() {
        refreshAccountOptions();
    });

    $('#importModal').on('show.bs.modal', function() {
        refreshAccountOptions();
    });
    
    // Reset form when modal closes (Manual Binding instead of HTML attribute)
    document.getElementById('assetModal').addEventListener('hidden.bs.modal', function () {
        $('#modalTitle').text('新增资产');
        $('#assetId').val('');
        $('#assetType').val('');
        document.getElementById('assetForm').reset();
    });
});
