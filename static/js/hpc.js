let currentStrategyId = null;
let strategies = [];
let pendingInstructions = null; // Store for execution

$(document).ready(function() {
    loadStrategies();
    loadCategories(); // Load category config
    
    // Tab switching refresh
    $('#tab-mapping').on('shown.bs.tab', function() {
        if(currentStrategyId) loadHoldings();
    });
    
    $('#tab-analysis').on('shown.bs.tab', function() {
        if(currentStrategyId) loadAnalysis();
    });
    
    $('#strategySelect').change(function() {
        currentStrategyId = $(this).val();
        const strat = strategies.find(s => s.id == currentStrategyId);
        if (strat) {
            $('#localEquity').val(strat.current_equity);
        }
        loadHoldings(); 
    });
});

// --- Category Config ---
let allCategories = [];

function loadCategories() {
    $.get('/api/hpc/categories', function(res) {
        allCategories = res;
        const list = $('#categoryList');
        list.empty();
        
        res.forEach(c => {
            list.append(`
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    ${c.name}
                    <button class="btn btn-sm text-danger border-0" onclick="deleteCategory(${c.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </li>
            `);
        });
        
        // Also update datalist if modal is open (optional)
    });
}

function addCategory() {
    const name = $('#newCatName').val().trim();
    if (!name) return;
    
    $.ajax({
        url: '/api/hpc/category',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ name }),
        success: function() {
            $('#newCatName').val('');
            loadCategories();
        },
        error: function(err) {
            alert(err.responseJSON.message);
        }
    });
}

function deleteCategory(cid) {
    if (!confirm('确定删除此分类吗？')) return;
    $.ajax({
        url: `/api/hpc/category/${cid}`,
        type: 'DELETE',
        success: function() {
            loadCategories();
        }
    });
}

function populateCat2Options() {
    const dl = $('#cat2Options');
    dl.empty();
    allCategories.forEach(c => {
        dl.append(`<option value="${c.name}">`);
    });
}

// --- Strategy Management ---
function loadStrategies() {
    $.get('/api/hpc/strategies', function(res) {
        strategies = res;
        const sel = $('#strategySelect');
        sel.empty();
        
        if (res.length === 0) {
            sel.append('<option value="">请新建策略</option>');
            showNewStrategyModal();
        } else {
            res.forEach(s => {
                sel.append(`<option value="${s.id}">${s.name}</option>`);
            });
            // Select first by default
            if (!currentStrategyId) currentStrategyId = res[0].id;
            sel.val(currentStrategyId);
            $('#localEquity').val(res[0].current_equity);
            
            // Auto-load holdings if tab is visible or just to be safe
            if ($('#pane-mapping').is(':visible') || $('#tab-mapping').hasClass('active')) {
                loadHoldings();
            }
        }
    });
}

function showNewStrategyModal() {
    new bootstrap.Modal(document.getElementById('newStrategyModal')).show();
}

function createStrategy() {
    const name = $('#newStrategyName').val();
    const equity = $('#newStrategyEquity').val();
    
    $.ajax({
        url: '/api/hpc/strategy',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ name, equity }),
        success: function() {
            $('#newStrategyModal').modal('hide');
            loadStrategies();
        }
    });
}

function updateEquity() {
    if (!currentStrategyId) return;
    const equity = $('#localEquity').val();
    
    $.ajax({
        url: `/api/hpc/strategy/${currentStrategyId}/equity`,
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ equity }),
        success: function() {
            alert('权益已更新');
            // Update local cache
            const s = strategies.find(s => s.id == currentStrategyId);
            if(s) s.current_equity = equity;
        }
    });
}

// --- Initialization ---
function initByMarkdown() {
    if (!currentStrategyId) return alert('请先选择策略');
    const md = $('#initMarkdown').val();
    
    $.ajax({
        url: '/api/hpc/init_by_markdown',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            strategy_id: currentStrategyId,
            markdown: md
        }),
        success: function(res) {
            alert(res.message);
            // Switch to mapping tab
            $('#tab-mapping').click();
        },
        error: function(err) {
            alert('Error: ' + err.responseJSON.message);
        }
    });
}

// --- Mapping ---
let currentSort = { col: null, asc: true };

function loadHoldings() {
    console.log("Loading holdings for strategy:", currentStrategyId);
    if (!currentStrategyId) return;
    
    $.get(`/api/hpc/holdings/${currentStrategyId}`, function(res) {
        console.log("Holdings loaded:", res.length);
        let data = res;
        
        // Sorting
        if (currentSort.col) {
            data.sort((a, b) => {
                let valA = a[currentSort.col];
                let valB = b[currentSort.col];
                
                // Handle numbers
                if (currentSort.col === 'weight' || currentSort.col === 'base_shares') {
                    valA = parseFloat(valA || 0);
                    valB = parseFloat(valB || 0);
                } else {
                    valA = (valA || '').toString().toLowerCase();
                    valB = (valB || '').toString().toLowerCase();
                }
                
                if (valA < valB) return currentSort.asc ? -1 : 1;
                if (valA > valB) return currentSort.asc ? 1 : -1;
                return 0;
            });
        }
        
        const tbody = $('#mappingTable tbody');
        tbody.empty();
        
        data.forEach(h => {
            try {
                const mappingsHtml = (h.mappings || []).map(m => 
                    `<span class="badge bg-secondary me-1">${m.local_code} (${m.allocation_ratio})</span>`
                ).join('');
                
                const statusClass = h.mapping_status === 'OK' ? 'text-success' : 'text-danger';
                const weightPct = h.weight ? (parseFloat(h.weight) * 100).toFixed(2) + '%' : '-';
                
                                tbody.append(`
                
                                    <tr>
                
                                        <td>
                
                                            <div class="fw-bold">${h.target_name}</div>
                
                                            <small class="text-muted">${h.target_code}</small>
                
                                        </td>
                
                                        <td>${h.target_type || '-'}
                
                                        </td>
                
                                        <td class="editable-cell" ondblclick="makeCat2Editable(this, '${h.target_code}')" data-val="${h.target_category_2 || ''}" style="cursor:pointer" title="双击编辑">
                
                                            ${h.target_category_2 || '-'} <i class="fas fa-pen small text-muted ms-1" style="font-size:0.7em; opacity:0.5"></i>
                
                                        </td>
                
                                        <td>${weightPct}
                
                                        </td>
                
                                        <td>
                
                                            <div>${parseFloat(h.base_shares).toFixed(2)} 份</div>
                
                                            <small class="text-muted">净值: ${h.latest_nav}</small>
                
                                        </td>
                
                                        <td>${mappingsHtml || '<span class="text-muted">-</span>'}
                
                                        </td>
                
                                        <td class="${statusClass}">${h.mapping_status}
                
                                        </td>
                
                                        <td>
                
                                            <button class="btn btn-sm btn-outline-primary" onclick='editMapping(${JSON.stringify(h)})'>配置</button>
                
                                        </td>
                
                                    </tr>
                
                                `);
                
                            } catch (e) {
                
                                console.error("Render error for row:", h, e);
                
                            }
                
                        });
                
                    });
                
                }
                
                
                
                function makeCat2Editable(td, code) {
                
                    const currentVal = $(td).data('val');
                
                    
                
                    // Create select
                
                    let options = '<option value="">-</option>';
                
                    allCategories.forEach(c => {
                
                        const selected = c.name === currentVal ? 'selected' : '';
                
                        options += `<option value="${c.name}" ${selected}>${c.name}</option>`;
                
                    });
                
                    
                
                    const html = `
                
                        <select class="form-select form-select-sm" onblur="saveCat2Inline(this, '${code}')" onchange="this.blur()">
                
                            ${options}
                
                        </select>
                
                    `;
                
                    
                
                    $(td).html(html);
                
                    $(td).find('select').focus();
                
                    $(td).removeAttr('ondblclick'); // Prevent re-trigger
                
                }
                
                
                
                function saveCat2Inline(select, code) {
                
                    const newVal = $(select).val();
                
                    const td = $(select).parent();
                
                    
                
                    // Save to DB
                
                    $.ajax({
                
                        url: '/api/hpc/holding/cat2',
                
                        type: 'POST',
                
                        contentType: 'application/json',
                
                        data: JSON.stringify({
                
                            strategy_id: currentStrategyId,
                
                            target_code: code,
                
                            cat2: newVal
                
                        }),
                
                        success: function() {
                
                            // Re-render cell text
                
                            td.text(newVal || '-');
                
                            td.data('val', newVal);
                
                            // Restore double click
                
                            td.attr('ondblclick', `makeCat2Editable(this, '${code}')`);
                
                            td.append(' <i class="fas fa-pen small text-muted ms-1" style="font-size:0.7em; opacity:0.5"></i>');
                
                        },
                
                        error: function(err) {
                
                            alert('保存失败: ' + err.responseJSON.message);
                
                            loadHoldings(); // Revert on error
                
                        }
                
                    });
                
                }
                
                
                
                function sortMappingTable(col) {
    if (currentSort.col === col) {
        currentSort.asc = !currentSort.asc;
    } else {
        currentSort.col = col;
        currentSort.asc = true;
    }
    
    // 更新 UI 图标标识
    $('#mappingTable thead th i').removeClass('fa-sort-up fa-sort-down').addClass('fa-sort');
    const header = $(`#mappingTable thead th[onclick*="'${col}'"]`);
    if (header.length) {
        header.find('i').removeClass('fa-sort').addClass(currentSort.asc ? 'fa-sort-up' : 'fa-sort-down');
    }

    loadHoldings(); 
}

function editMapping(holding) {
    $('#mappingTargetTitle').text(`${holding.target_name} (${holding.target_code})`);
    $('#mappingTargetCode').val(holding.target_code);
    
    // Populate datalist
    populateCat2Options();
    
    // Pre-fill Cat2 input
    $('#targetCat2Input').val(holding.target_category_2 || '');
    
    const tbody = $('#mappingEditTable tbody');
    tbody.empty();
    
    // Add existing rows or default row
    const rows = holding.mappings.length > 0 ? holding.mappings : [{local_code: '', local_type: 'ETF', local_name: '', allocation_ratio: 1.0}];
    
    rows.forEach(m => addMappingRow(m));
    
    new bootstrap.Modal(document.getElementById('mappingModal')).show();
}

function addMappingRow(data = null) {
    const code = data ? data.local_code : '';
    const name = data ? data.local_name : '';
    const ratio = data ? data.allocation_ratio : '';
    
    const row = `
        <tr>
            <td><input type="text" class="form-control form-control-sm local-code" value="${code}" placeholder="如 510300"></td>
            <td>
                <select class="form-select form-select-sm local-type">
                    <option value="ETF">ETF</option>
                    <option value="OTC">场外</option>
                    <option value="STOCK">股票</option>
                </select>
            </td>
            <td><input type="text" class="form-control form-control-sm local-name" value="${name}"></td>
            <td><input type="number" class="form-control form-control-sm local-ratio" value="${ratio}" step="0.1"></td>
            <td><button class="btn btn-close" onclick="$(this).closest('tr').remove()"></button></td>
        </tr>
    `;
    $('#mappingEditTable tbody').append(row);
    
    if (data) {
        $('#mappingEditTable tbody tr:last .local-type').val(data.local_type);
    }
}

function saveMapping() {
    // 1. Save Category 2
    const cat2 = $('#targetCat2Input').val();
    const targetCode = $('#mappingTargetCode').val();
    
    $.ajax({
        url: '/api/hpc/holding/cat2',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            strategy_id: currentStrategyId,
            target_code: targetCode,
            cat2: cat2
        })
    });

    // 2. Save Mappings
    const mappings = [];
    let totalRatio = 0;
    
    $('#mappingEditTable tbody tr').each(function() {
        const row = $(this);
        const ratio = parseFloat(row.find('.local-ratio').val()) || 0;
        totalRatio += ratio;
        
        mappings.push({
            local_code: row.find('.local-code').val(),
            local_type: row.find('.local-type').val(),
            local_name: row.find('.local-name').val(),
            ratio: ratio
        });
    });
    
    if (Math.abs(totalRatio - 1.0) > 0.01) {
        if (!confirm(`当前总比例为 ${totalRatio}，不等于 1.0。确定要保存吗？`)) return;
    }
    
    $.ajax({
        url: '/api/hpc/mapping',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            strategy_id: currentStrategyId,
            target_code: targetCode,
            mappings: mappings
        }),
        success: function() {
            $('#mappingModal').modal('hide');
            loadHoldings();
        }
    });
}

// --- Rebalance Engine ---
function calculateRebalance() {
    const text = $('#rebalanceInput').val();
    if (!text) return alert('请输入指令');
    
    const lines = text.split('\n').filter(l => l.trim());
    const instructions = [];
    
    // Parse instructions (Simple pipe or space separation)
    // Format: Code | Action | Value | Unit
    lines.forEach(l => {
        const parts = l.replace(/\|/g, ' ').split(/\s+/);
        if (parts.length >= 3) {
            // Very simple heuristic parser
            // Assume: Code Action Value [Unit]
            let unit = 'SHARE';
            if (parts[3] && (parts[3].includes('金') || parts[3].includes('元'))) unit = 'AMOUNT';
            
            let action = 'BUY';
            if (parts[1].includes('卖')) action = 'SELL';
            
            instructions.push({
                code: parts[0],
                action: action,
                value: parts[2],
                unit: unit
            });
        }
    });
    
    if (instructions.length === 0) return alert('无法解析指令');
    
    $.ajax({
        url: '/api/hpc/calculate',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            strategy_id: currentStrategyId,
            instructions: instructions
        }),
        success: function(res) {
            renderRebalanceResult(res, instructions);
        },
        error: function(err) {
            alert(err.responseJSON.message);
        }
    });
}

function renderRebalanceResult(results, originalInstructions) {
    const container = $('#rebalanceResult');
    container.empty();
    
    if (results.length === 0) {
        container.html('<div class="text-muted">无操作建议</div>');
        return;
    }
    
    let html = '<ul class="list-group text-start">';
    
    results.forEach(r => {
        if (r.error) {
            html += `<li class="list-group-item list-group-item-warning">
                <i class="fas fa-exclamation-triangle"></i> 
                目标资产 <b>${r.code}</b>: ${r.error} (请先在“持仓与映射”中添加此资产)
            </li>`;
            return;
        }
        
        const ratioPct = (r.change_ratio * 100).toFixed(4) + '%';
        html += `<li class="list-group-item bg-light">
            <strong>${r.target_code}</strong> 变动: <span class="badge bg-info">${ratioPct}</span>
        </li>`;
        
        r.local_actions.forEach(act => {
            const color = act.suggested_action === 'BUY' ? 'text-danger' : 'text-success';
            const icon = act.suggested_action === 'BUY' ? 'fa-arrow-up' : 'fa-arrow-down';
            
            html += `<li class="list-group-item ps-5">
                <i class="fas ${icon} ${color}"></i> 
                <span class="${color} fw-bold">${act.suggested_action === 'BUY' ? '买入' : '卖出'}</span> 
                ${act.local_name} (${act.local_code}) 
                <span class="float-end fw-bold">¥ ${formatNumber(act.suggested_amount)}</span>
            </li>`;
        });
    });
    
    html += '</ul>';
    container.html(html);
    
    // Show Execute Button
    $('#rebalanceFooter').show();
    pendingInstructions = originalInstructions; // Save for execution
}

function confirmExecute() {
    if (!pendingInstructions) return;
    if (!confirm('确认已在本地账户完成上述操作？\n系统将同步更新虚拟持仓基准。')) return;
    
    $.ajax({
        url: '/api/hpc/execute',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            strategy_id: currentStrategyId,
            instructions: pendingInstructions
        }),
        success: function(res) {
            alert(res.message);
            $('#rebalanceResult').empty().text('操作已完成，基准已更新。');
            $('#rebalanceFooter').hide();
            pendingInstructions = null;
            $('#rebalanceInput').val(''); // Clear input
        }
    });
}

function formatNumber(num) {
    return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(num);
}

// --- Analysis Chart ---
let chartInstance = null;

function loadAnalysis() {
    if (!currentStrategyId) return;
    
    $.get(`/api/hpc/holdings/${currentStrategyId}`, function(res) {
        const typeMap = {};
        const cat2Map = {};
        
        res.forEach(h => {
            const val = parseFloat(h.base_shares) * parseFloat(h.latest_nav);
            if (val <= 0) return;
            
            const type = h.target_type || '其他';
            const cat2 = h.target_category_2 || '未分类';
            
            typeMap[type] = (typeMap[type] || 0) + val;
            
            if (!cat2Map[type]) cat2Map[type] = {};
            cat2Map[type][cat2] = (cat2Map[type][cat2] || 0) + val;
        });
        
        // 1. 定义内层类型的排序优先级
        const typePriority = { '股票类': 1, '债券类': 2, '商品类': 3, '现金类': 4, '其他': 5 };
        
        const innerData = Object.keys(typeMap).map(k => ({ 
            value: typeMap[k], 
            name: k,
            priority: typePriority[k] || 99
        })).sort((a, b) => a.priority - b.priority || b.value - a.value);
        
        // 2. 构造外层数据，确保顺序与内层完全对应
        const outerData = [];
        innerData.forEach(typeObj => {
            const typeName = typeObj.name;
            const subCats = cat2Map[typeName];
            
            // 在同一类型内部，按数值降序排列
            const sortedSubCats = Object.keys(subCats).map(k => ({
                value: subCats[k],
                name: k
            })).sort((a, b) => b.value - a.value);
            
            sortedSubCats.forEach(sc => {
                outerData.push(sc);
            });
        });
        
        renderChart(innerData, outerData);
    });
}

function renderChart(innerData, outerData) {
    if (!chartInstance) {
        const dom = document.getElementById('hpcChart');
        if (dom) chartInstance = echarts.init(dom);
    }
    
    if (!chartInstance) return;
    
    const option = {
        tooltip: {
            trigger: 'item',
            formatter: function(params) {
                return `${params.seriesName} <br/>${params.name}: <b>${formatNumber(params.value)}</b> (${params.percent}%)`;
            }
        },
        legend: {
            top: '5%',
            left: 'center'
        },
        series: [
            {
                name: '资产类型',
                type: 'pie',
                selectedMode: 'single',
                radius: [0, '40%'],
                label: {
                    position: 'inner',
                    fontSize: 12,
                    formatter: '{b}\n{d}%'
                },
                labelLine: {
                    show: false
                },
                data: innerData
            },
            {
                name: '二级分类',
                type: 'pie',
                radius: ['40%', '70%'],
                labelLine: {
                    length: 20
                },
                label: {
                    formatter: '{b}: {d}%'
                },
                data: outerData
            }
        ]
    };
    
    chartInstance.setOption(option);
    
    window.addEventListener('resize', function() {
        chartInstance.resize();
    });
}
