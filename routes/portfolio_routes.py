from flask import Blueprint, render_template, request, jsonify
from db.portfolio_db import PortfolioDatabase
from services.price_service import PriceService
from services.ocr_service import OCRService
import logging

portfolio_bp = Blueprint('portfolio', __name__)
db = PortfolioDatabase()

@portfolio_bp.route('/portfolio')
def index():
    """渲染资产全景页面"""
    return render_template('portfolio.html')

@portfolio_bp.route('/api/portfolio/upload_screenshot', methods=['POST'])
def upload_screenshot():
    """处理截图上传与OCR解析"""
    if 'file' not in request.files:
        return jsonify({'message': 'No file part', 'status': 'error'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file', 'status': 'error'}), 400
        
    try:
        image_bytes = file.read()
        results = OCRService.parse_screenshot(image_bytes)
        return jsonify({'status': 'success', 'data': results})
    except Exception as e:
        return jsonify({'message': str(e), 'status': 'error'}), 500

@portfolio_bp.route('/api/portfolio/data')
def get_portfolio_data():
    """获取全量资产数据（含实时市值和分类汇总）"""
    assets = db.get_all_assets()
    
    # 1. 获取最新价格
    prices = PriceService.get_batch_prices(assets)
    
    # 2. 计算各项指标
    total_assets = 0
    total_cost = 0
    asset_list = []
    
    for asset in assets:
        current_price = prices.get(asset['symbol'], 0)
        quantity = asset['quantity']
        cost_price = asset['cost_price']
        
        market_value = quantity * current_price
        cost_value = quantity * cost_price
        pnl = market_value - cost_value
        pnl_percent = (pnl / cost_value * 100) if cost_value else 0
        
        total_assets += market_value
        total_cost += cost_value
        
        asset_info = asset.copy()
        asset_info.update({
            'current_price': current_price,
            'market_value': market_value,
            'pnl': pnl,
            'pnl_percent': pnl_percent
        })
        asset_list.append(asset_info)
        
    total_pnl = total_assets - total_cost
    
    # 3. 构建多维汇总数据
    summary = {
        'total_assets': total_assets,
        'total_cost': total_cost,
        'total_pnl': total_pnl,
        'by_category_1': _group_by(asset_list, 'category_1'),
        'by_category_2': _group_by(asset_list, 'category_2'),
        'by_account': _group_by(asset_list, 'account_name'),
        'by_asset_type': _group_by(asset_list, 'asset_type')
    }
    
    return jsonify({
        'summary': summary,
        'assets': asset_list
    })

def _group_by(assets, key):
    """按指定key分组汇总市值"""
    groups = {}
    for asset in assets:
        k = asset.get(key) or '未分类'
        groups[k] = groups.get(k, 0) + asset['market_value']
    
    # 转换为列表格式供前端ECharts使用
    return [{'name': k, 'value': v} for k, v in groups.items()]

@portfolio_bp.route('/api/portfolio/asset', methods=['POST'])
def add_or_update_asset():
    """新增或修改资产"""
    try:
        data = request.json
        if 'id' in data and data['id']:
            # Update
            success = db.update_asset(data['id'], data)
            msg = "Updated successfully" if success else "Update failed"
        else:
            # Create
            new_id = db.add_asset(data)
            msg = "Created successfully"
            
        return jsonify({'message': msg, 'status': 'success'})
    except Exception as e:
        logging.error(f"Save asset error: {e}")
        return jsonify({'message': str(e), 'status': 'error'}), 500

@portfolio_bp.route('/api/portfolio/asset/<int:asset_id>', methods=['DELETE'])
def delete_asset(asset_id):
    """删除资产"""
    try:
        success = db.delete_asset(asset_id)
        if success:
            return jsonify({'message': 'Deleted successfully', 'status': 'success'})
        else:
            return jsonify({'message': 'Delete failed', 'status': 'error'}), 400
    except Exception as e:
        return jsonify({'message': str(e), 'status': 'error'}), 500

# Account Management APIs
@portfolio_bp.route('/api/portfolio/accounts', methods=['GET'])
def get_accounts():
    """获取所有账户"""
    return jsonify(db.get_all_accounts())

@portfolio_bp.route('/api/portfolio/account', methods=['POST'])
def add_or_update_account():
    """新增或修改账户"""
    try:
        data = request.json
        if 'id' in data and data['id']:
            # Update
            success = db.update_account(data['id'], data['name'], data.get('type'), data.get('description'))
            msg = "Updated successfully" if success else "Update failed"
        else:
            # Create
            db.add_account(data['name'], data.get('type'), data.get('description'))
            msg = "Created successfully"
            
        return jsonify({'message': msg, 'status': 'success'})
    except Exception as e:
        logging.error(f"Save account error: {e}")
        return jsonify({'message': str(e), 'status': 'error'}), 500

@portfolio_bp.route('/api/portfolio/account/<int:account_id>', methods=['DELETE'])
def delete_account(account_id):
    """删除账户"""
    try:
        success = db.delete_account(account_id)
        if success:
            return jsonify({'message': 'Deleted successfully', 'status': 'success'})
        else:
            return jsonify({'message': 'Delete failed', 'status': 'error'}), 400
    except Exception as e:
        return jsonify({'message': str(e), 'status': 'error'}), 500
