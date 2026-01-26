from flask import Blueprint, jsonify, request, render_template
from db.hpc_db import HPCDatabase
import logging

hpc_bp = Blueprint('hpc', __name__)
db = HPCDatabase()

@hpc_bp.route('/hpc')
def hpc_index():
    return render_template('hpc.html')

@hpc_bp.route('/api/hpc/strategies', methods=['GET'])
def get_strategies():
    return jsonify(db.get_all_strategies())

# --- Category Config API ---
@hpc_bp.route('/api/hpc/categories', methods=['GET'])
def get_categories():
    return jsonify(db.get_categories())

@hpc_bp.route('/api/hpc/category', methods=['POST'])
def add_category():
    name = request.json.get('name')
    if not name: return jsonify({'message': 'Name required'}), 400
    if db.add_category(name):
        return jsonify({'status': 'success'})
    else:
        return jsonify({'message': 'Category already exists'}), 400

@hpc_bp.route('/api/hpc/category/<int:cid>', methods=['DELETE'])
def delete_category(cid):
    db.delete_category(cid)
    return jsonify({'status': 'success'})
# ---------------------------

@hpc_bp.route('/api/hpc/strategy', methods=['POST'])
def create_strategy():
    data = request.json
    name = data.get('name')
    equity = data.get('equity', 0)
    url = data.get('url', '')
    
    if not name:
        return jsonify({'message': 'Strategy name is required'}), 400
        
    sid = db.create_strategy(name, equity, url)
    return jsonify({'id': sid, 'status': 'success'})

@hpc_bp.route('/api/hpc/strategy/<int:sid>/equity', methods=['POST'])
def update_equity(sid):
    data = request.json
    equity = data.get('equity')
    db.update_strategy_equity(sid, equity)
    return jsonify({'status': 'success'})

@hpc_bp.route('/api/hpc/holdings/<int:sid>', methods=['GET'])
def get_holdings(sid):
    # Get virtual holdings
    holdings = db.get_virtual_holdings(sid)
    
    # Enrich with mappings
    result = []
    for h in holdings:
        mappings = db.get_mappings(sid, h['target_code'])
        h['mappings'] = mappings
        # Check mapping status
        total_ratio = sum([float(m['allocation_ratio']) for m in mappings])
        h['mapping_status'] = 'OK' if abs(total_ratio - 1.0) < 0.01 else 'Incomplete'
        result.append(h)
        
    return jsonify(result)

@hpc_bp.route('/api/hpc/init_by_markdown', methods=['POST'])
def init_by_markdown():
    """
    接收 Markdown 文本，解析并初始化虚拟持仓。
    Expected JSON: { "strategy_id": 1, "markdown": "| Name | Code | Shares | ..." }
    """
    data = request.json
    sid = data.get('strategy_id')
    md_text = data.get('markdown', '')
    
    if not sid or not md_text:
        return jsonify({'message': 'Missing strategy_id or markdown content'}), 400

    # Simple Markdown Parsing Logic (Robust)
    lines = [l.strip() for l in md_text.split('\n') if l.strip() and '|' in l]
    if len(lines) < 2:
        return jsonify({'message': 'Invalid markdown table'}), 400
        
    # 1. Parse Header
    header_line = lines[0].strip('|').split('|')
    headers = [h.strip().lower() for h in header_line]
    logging.info(f"HPC Init Headers: {headers}")
    
    # Map headers
    idx_map = {}
    for i, h in enumerate(headers):
        if 'code' in h or '代码' in h: idx_map['code'] = i
        elif 'name' in h or '名称' in h: idx_map['name'] = i
        elif 'share' in h or '份额' in h or '数量' in h: idx_map['shares'] = i
        elif 'nav' in h or '净值' in h or 'price' in h: idx_map['nav'] = i
        elif 'amount' in h or '市值' in h or '金额' in h: idx_map['amount'] = i
        elif 'type' in h or '类型' in h or '分类' in h or '类别' in h: idx_map['type'] = i
        elif 'weight' in h or '占比' in h: idx_map['weight'] = i
        elif 'cat2' in h or '二级' in h or '子类' in h or '细分' in h: idx_map['cat2'] = i
        
    logging.info(f"HPC Init Map: {idx_map}")

    if 'code' not in idx_map:
        return jsonify({'message': 'Column "Code" not found'}), 400

    count = 0
    for i in range(1, len(lines)):
        if '---' in lines[i]: continue
        parts = lines[i].strip('|').split('|')
        parts = [p.strip() for p in parts]
        
        # Log first data row for debugging
        if count == 0: logging.info(f"HPC First Row Parts: {parts}")
        
        if len(parts) < len(headers): 
            logging.warning(f"Skipping incomplete line {i}: {parts}")
            continue 
        
        try:
            code = parts[idx_map['code']]
            name = parts[idx_map.get('name', idx_map['code'])] 
            
            # Determine shares
            shares = 0
            nav = 1.0
            type_val = ''
            cat2_val = ''
            weight = 0
            
            if 'nav' in idx_map:
                nav = float(parts[idx_map['nav']].replace(',',''))
                
            if 'shares' in idx_map:
                shares = float(parts[idx_map['shares']].replace(',',''))
            elif 'amount' in idx_map and 'nav' in idx_map:
                amt = float(parts[idx_map['amount']].replace(',',''))
                shares = amt / nav if nav else 0
                
            if 'type' in idx_map: type_val = parts[idx_map['type']]
            if 'cat2' in idx_map: cat2_val = parts[idx_map['cat2']]
                
            if 'weight' in idx_map:
                w_str = parts[idx_map['weight']].replace('%','').replace(',','')
                weight = float(w_str) / 100 if w_str else 0
            
            # Upsert DB
            db.upsert_virtual_holding(sid, code, name, shares, nav, 'MANUAL', type_val, weight, cat2_val)
            count += 1
            
        except Exception as e:
            logging.error(f"Error parsing line {i}: {e}")
            continue

    return jsonify({'message': f'Successfully initialized {count} positions', 'count': count})

@hpc_bp.route('/api/hpc/holding/cat2', methods=['POST'])
def update_holding_cat2():
    data = request.json
    sid = data.get('strategy_id')
    code = data.get('target_code')
    cat2 = data.get('cat2')
    
    db.update_virtual_holding_cat2(sid, code, cat2)
    return jsonify({'status': 'success'})

@hpc_bp.route('/api/hpc/mapping', methods=['POST'])
def save_mapping():
    data = request.json
    sid = data.get('strategy_id')
    target = data.get('target_code')
    mappings = data.get('mappings') # List
    
    db.save_mapping(sid, target, mappings)
    return jsonify({'status': 'success'})

@hpc_bp.route('/api/hpc/calculate', methods=['POST'])
def calculate_rebalance():
    """
    核心：接收调仓指令，计算本地操作。
    Input: {
        "strategy_id": 1,
        "instructions": [
            {"code": "000905", "action": "BUY", "value": 1000, "unit": "AMOUNT"},  # 买入1000元
            {"code": "510300", "action": "SELL", "value": 500, "unit": "SHARE"}    # 卖出500份
        ]
    }
    """
    data = request.json
    sid = data.get('strategy_id')
    instructions = data.get('instructions', [])
    
    # 1. Get Strategy Info
    strategy = db.get_strategy(sid)
    local_equity = strategy['current_equity']
    
    if not local_equity:
        return jsonify({'message': 'Please set Local Equity first'}), 400
        
    results = []
    
    for instr in instructions:
        code = instr['code']
        action = instr['action'] # BUY / SELL
        value = float(instr['value'])
        unit = instr['unit'] # AMOUNT / SHARE
        
        # 2. Get Base Info
        # We need the virtual holding to get base_shares (denominator)
        # But wait, db.get_virtual_holdings returns a list. We need exact match.
        # Let's add a helper in db or filter here.
        # For simplicity, we query DB directly here or assume memory loaded.
        # Let's optimize DB later.
        
        conn = db.get_connection()
        cursor = conn.cursor()
        base = cursor.execute("SELECT base_shares, latest_nav FROM hpc_virtual_holdings WHERE strategy_id=? AND target_code=?", (sid, code)).fetchone()
        conn.close()
        
        if not base:
            results.append({'code': code, 'error': 'New Position Detected', 'is_new': True})
            continue
            
        base_shares = base[0]
        latest_nav = base[1]
        
        # 3. Calculate Ratio
        change_ratio = 0
        
        if unit == 'SHARE':
            # Case 1: Change by Shares
            # Ratio = Delta_Shares / Base_Shares
            if base_shares == 0: change_ratio = 0 # Prevent div by zero
            else:
                delta = value if action == 'BUY' else -value
                change_ratio = delta / base_shares
                
        elif unit == 'AMOUNT':
            # Case 2: Change by Amount
            # Ratio = (Amount / NAV) / Base_Shares
            if base_shares == 0 or latest_nav == 0: change_ratio = 0
            else:
                delta_amt = value if action == 'BUY' else -value
                estimated_shares = delta_amt / latest_nav
                change_ratio = estimated_shares / base_shares
        
        # 4. Apply Mappings
        mappings = db.get_mappings(sid, code)
        local_actions = []
        
        for m in mappings:
            ratio = m['allocation_ratio']
            local_delta_amt = local_equity * change_ratio * ratio
            
            local_actions.append({
                'local_code': m['local_code'],
                'local_name': m['local_name'],
                'type': m['local_type'],
                'suggested_action': 'BUY' if local_delta_amt > 0 else 'SELL',
                'suggested_amount': abs(local_delta_amt)
            })
            
        results.append({
            'target_code': code,
            'change_ratio': change_ratio,
            'local_actions': local_actions
        })
        
    return jsonify(results)

@hpc_bp.route('/api/hpc/execute', methods=['POST'])
def execute_rebalance():
    """
    闭环：确认执行，更新基准。
    Input: Same as calculate
    """
    data = request.json
    sid = data.get('strategy_id')
    instructions = data.get('instructions', [])
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    updated_count = 0
    
    for instr in instructions:
        code = instr['code']
        action = instr['action']
        value = float(instr['value'])
        unit = instr['unit']
        
        # Calculate Delta Shares
        delta_shares = 0
        
        # Query current nav/shares
        row = cursor.execute("SELECT base_shares, latest_nav FROM hpc_virtual_holdings WHERE strategy_id=? AND target_code=?", (sid, code)).fetchone()
        
        if not row: continue # Should handle new position separately
        
        base_shares, nav = row
        
        if unit == 'SHARE':
            delta_shares = value
        elif unit == 'AMOUNT':
            delta_shares = value / nav if nav else 0
            
        if action == 'SELL':
            delta_shares = -delta_shares
            
        # Update DB
        new_shares = base_shares + delta_shares
        cursor.execute("UPDATE hpc_virtual_holdings SET base_shares = ? WHERE strategy_id=? AND target_code=?", 
                       (new_shares, sid, code))
        updated_count += 1
        
    conn.commit()
    conn.close()
    
    return jsonify({'message': f'Updated {updated_count} virtual positions'})
