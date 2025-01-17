
// 显示错误信息
function showError(message, error = null) {
    clearError();

    // 打印详细的错误堆栈
    if (error) {
        console.error('Error details:', {
            message: message,
            error: error,
            stack: error.stack,
            timestamp: new Date().toISOString()
        });
    }

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

// 将updateTable函数从index.html移到这里
function updateTable(tableId, data, allowHtml = false) {
    try {
        console.log(`Updating table ${tableId} with data:`, data);  // 调试日志
        const table = $(`#${tableId}`);
        const tbody = table.find('tbody');
        tbody.empty();
        
        // 如果数据为空，直接返回
        if (!data) {
            console.error(`No data provided for table ${tableId}`);
            return;
        }
        
        // 处理数据格式
        let tableData;
        if (data.data && Array.isArray(data.data)) {
            // 如果数据是{headers, data}格式
            tableData = data.data;
        } else if (Array.isArray(data)) {
            // 如果数据直接是数组
            tableData = data;
        } else {
            console.error(`Invalid data format for table ${tableId}:`, data);
            return;
        }
        
        // 生成表格行
        tableData.forEach(row => {
            if (!Array.isArray(row)) {
                console.error(`Invalid row data for table ${tableId}:`, row);
                return;
            }
            
            const tr = $('<tr>');
            row.forEach(cell => {
                const td = $('<td>');
                if (allowHtml) {
                    td.html(cell || '');
                } else {
                    td.text(cell || '');
                }
                tr.append(td);
            });
            tbody.append(tr);
        });
        
        console.log(`Table ${tableId} updated successfully`);  // 成功日志
    } catch (error) {
        console.error(`Error updating table ${tableId}:`, error);
    }
}

// 显示回测结果
function displayResults(response) {
    try {
        console.log('开始处理回测结果:', response);
        
        if (!response) {
            throw new Error('回测结果为空');
        }
        
        // 显示结果区域
        $('#results').show();
        
        // 更新表格数据
        if (response.strategy_comparison) {
            updateTable('strategy-comparison', response.strategy_comparison);
        }
        
        if (response.trade_summary) {
            updateTable('trade-summary', response.trade_summary);
        }
        
        if (response.trade_records) {
            updateTable('trade-records', response.trade_records);  // 直接传递整个对象
        }
        
        if (response.daily_pnl) {
            updateTable('daily-pnl', response.daily_pnl, true);  // 允许HTML内容
        }
        
        // 渲染图表
        if (response.plots) {
            if (response.plots.performance) {
                Plotly.newPlot('performance-plot', 
                    JSON.parse(response.plots.performance).data,
                    JSON.parse(response.plots.performance).layout
                );
            }
            
            if (response.plots.drawdown) {
                Plotly.newPlot('drawdown-plot',
                    JSON.parse(response.plots.drawdown).data,
                    JSON.parse(response.plots.drawdown).layout
                );
            }
            
            if (response.plots.pnl_distribution) {
                Plotly.newPlot('pnl-distribution-plot',
                    JSON.parse(response.plots.pnl_distribution).data,
                    JSON.parse(response.plots.pnl_distribution).layout
                );
            }
        }
        
        console.log('回测结果显示完成');
    } catch (error) {
        console.error('显示回测结果时出错:', {
            error: error,
            stack: error.stack,
            timestamp: new Date().toISOString(),
            responseData: response
        });
        showError('显示回测结果时出错: ' + error.message, error);
    }
}