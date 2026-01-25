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
    """获取全量资产数据（使用数据库缓存价格）"""
    try:
        assets = db.get_all_assets()
        
        # 计算各项指标 (基于缓存的 last_price)
        total_assets = 0
        total_cost = 0
        asset_list = []
        
        for asset in assets:
            current_price = asset.get('last_price', 0) or 0
            quantity = asset.get('quantity', 0) or 0
            cost_price = asset.get('cost_price', 0) or 0
            
            market_value = quantity * current_price
            cost_value = quantity * cost_price
            
            pnl = market_value - cost_value
            
            # 处理负成本或零成本情况
            if cost_value <= 0:
                if pnl > 0:
                    pnl_percent = 999999  # 标识无限大
                else:
                    pnl_percent = 0
            else:
                pnl_percent = (pnl / cost_value * 100)
            
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
        
        # 4. 自动保存本周快照
        try:
            db.add_or_update_snapshot(total_assets, total_pnl, total_cost)
        except Exception as e:
            logging.error(f"Snapshot failed: {e}")
            
        # 5. 获取历史趋势
        history = db.get_snapshots()
        
        return jsonify({
            'summary': summary,
            'assets': asset_list,
            'history': history
        })
    except Exception as e:
        logging.error(f"Get portfolio data error: {e}")
        return jsonify({'message': str(e), 'status': 'error'}), 500

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

@portfolio_bp.route('/api/portfolio/refresh_prices', methods=['POST'])
def refresh_prices():
    """主动更新所有资产的最新价格"""
    try:
        assets = db.get_all_assets()
        if not assets:
            return jsonify({'message': 'No assets to update', 'status': 'success'})
            
        # 1. 批量获取最新价格
        prices = PriceService.get_batch_prices(assets)
        
        updated_count = 0
        
        # 2. 更新数据库
        for asset in assets:
            symbol = asset['symbol']
            if symbol in prices and prices[symbol] > 0:
                # 仅更新价格字段
                new_price = prices[symbol]
                # 保持其他字段不变
                asset_data = {
                    'last_price': new_price
                }
                # 注意：update_asset 会更新 update_time，这正好符合需求
                db.update_asset(asset['id'], asset_data)
                updated_count += 1
                
        return jsonify({
            'message': f'Updated {updated_count} assets', 
            'status': 'success',
            'updated_count': updated_count
        })
    except Exception as e:
        logging.error(f"Refresh prices error: {e}")
        return jsonify({'message': str(e), 'status': 'error'}), 500
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
