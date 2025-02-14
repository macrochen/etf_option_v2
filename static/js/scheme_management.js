// 方案管理相关功能
$(document).ready(function() {
    // 初始化保存方案复选框事件
    initSaveSchemeCheckbox();
    
    // 初始化方案管理模态框事件
    initSchemeModal();
    
    // 加载方案列表
    loadSchemeList();
});

// 初始化保存方案复选框
function initSaveSchemeCheckbox() {
    $('#saveScheme').change(function() {
        const schemeNameGroup = $('#schemeNameGroup');
        if ($(this).is(':checked')) {
            schemeNameGroup.removeClass('d-none');
            generateSchemeName();
        } else {
            schemeNameGroup.addClass('d-none');
        }
    });
}

// 生成默认方案名称
function generateSchemeName() {
    const etfCode = $('#etf_code').val();
    const startDate = $('#start_date').val()?.replace(/-/g, '');
    const endDate = $('#end_date').val()?.replace(/-/g, '');
    
    // 获取Delta值列表
    const deltas = [];
    ['put_sell_delta', 'put_buy_delta', 'call_sell_delta', 'call_buy_delta'].forEach(id => {
        const value = $(`#${id}`).val();
        if (value) deltas.push(value);
    });
    const deltaList = deltas.join(',');
    
    // 严格按照文档格式生成方案名称
    let name = etfCode || '方案';
    if (deltaList) name += `_${deltaList}`;
    if (startDate) name += `_${startDate}`;
    if (endDate) name += `_${endDate}`;
    
    $('#schemeName').val(name);
}


// 初始化方案管理模态框
function initSchemeModal() {
    $('#schemeModal').on('show.bs.modal', function() {
        loadSchemeList();
    });
}

// 加载方案列表
function loadSchemeList() {
    $.ajax({
        url: '/api/schemes',
        method: 'GET',
        success: function(response) {
            renderSchemeList(response.schemes);
        },
        error: function(xhr, status, error) {
            showError('加载方案列表失败: ' + error);
        }
    });
}

// 渲染方案列表
function renderSchemeList(schemes) {
    const tbody = $('#schemeList');
    tbody.empty();
    
    schemes.forEach(scheme => {
        const row = $('<tr>');
        row.append($('<td>').text(scheme.name));
        row.append($('<td>').text(formatDateTime(scheme.created_at)));
        row.append($('<td>').text(formatDateTime(scheme.updated_at)));
        
        const actions = $('<td>').html(`
            <button class="btn btn-sm btn-outline-primary me-1" 
                    title="显示回测结果" 
                    onclick="loadScheme('${scheme.id}')">
                <i class="fas fa-chart-line"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger me-1" 
                    title="删除方案" 
                    onclick="deleteScheme('${scheme.id}')">
                <i class="fas fa-trash"></i>
            </button>
            <button class="btn btn-sm btn-outline-secondary" 
                    title="重命名方案" 
                    onclick="renameScheme('${scheme.id}')">
                <i class="fas fa-edit"></i>
            </button>
        `);
        
        row.append(actions);
        tbody.append(row);
    });
}

// 格式化日期时间
function formatDateTime(dateStr) {
    return new Date(dateStr).toLocaleString('zh-CN');
}

// 加载方案
function loadScheme(schemeId) {
    $.ajax({
        url: `/api/schemes/${schemeId}`,
        method: 'GET',
        success: function(response) {
            // 填充表单参数
            fillBacktestForm(response.params);
            
            // 直接显示保存的回测结果
            if (response.backtest_results) {
                $('#results').show();
                displayResults(response.backtest_results);
            } else {
                showError('未找到保存的回测结果');
            }
            
            // 关闭模态框
            $('#schemeModal').modal('hide');
        },
        error: function(xhr, status, error) {
            showError('加载方案失败: ' + error);
        }
    });
}

// 删除方案
function deleteScheme(schemeId) {
    if (!confirm('确定要删除这个方案吗？')) return;
    
    $.ajax({
        url: `/api/schemes/${schemeId}`,
        method: 'DELETE',
        success: function() {
            loadSchemeList();
        },
        error: function(xhr, status, error) {
            showError('删除方案失败: ' + error);
        }
    });
}

// 重命名方案
function renameScheme(schemeId) {
    const newName = prompt('请输入新的方案名称:');
    if (!newName) return;
    
    $.ajax({
        url: `/api/schemes/${schemeId}`,
        method: 'PATCH',
        contentType: 'application/json',
        data: JSON.stringify({ name: newName }),
        success: function() {
            loadSchemeList();
        },
        error: function(xhr, status, error) {
            showError('重命名方案失败: ' + error);
        }
    });
}
