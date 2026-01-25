from datetime import datetime
from typing import List, Dict, Optional, Any
from .config import PORTFOLIO_DB
from .database import Database
import logging

class PortfolioDatabase:
    def __init__(self, db_path: str = PORTFOLIO_DB):
        """初始化资产组合数据库"""
        self.db = Database(db_path)
        self._init_table()

    def _init_table(self):
        """初始化资产持仓表"""
        # 资产持仓表
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS asset_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                category_1 TEXT,
                category_2 TEXT,
                symbol TEXT NOT NULL,
                name TEXT,
                quantity REAL DEFAULT 0,
                cost_price REAL DEFAULT 0,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 资产历史快照表 (按周记录)
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,      -- 记录日期 YYYY-MM-DD
                week TEXT NOT NULL UNIQUE, -- 周标识 YYYY-WW (用于去重)
                total_assets REAL,
                total_pnl REAL,
                total_cost REAL,
                update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    def add_or_update_snapshot(self, total_assets: float, total_pnl: float, total_cost: float) -> bool:
        """记录本周资产快照 (如果本周已存在则更新，否则插入)"""
        now = datetime.now()
        date_str = now.strftime('%Y-%m-%d')
        # 获取 ISO 周号 (例如 2026-04)
        year, week, _ = now.isocalendar()
        week_str = f"{year}-{week:02d}"
        
        try:
            # 检查本周是否已有记录
            existing = self.db.fetch_one('SELECT id FROM portfolio_snapshots WHERE week = ?', (week_str,))
            
            if existing:
                # 更新
                self.db.execute('''
                    UPDATE portfolio_snapshots 
                    SET total_assets = ?, total_pnl = ?, total_cost = ?, date = ?, update_time = ?
                    WHERE week = ?
                ''', (total_assets, total_pnl, total_cost, date_str, now.strftime('%Y-%m-%d %H:%M:%S'), week_str))
            else:
                # 插入
                self.db.execute_insert('''
                    INSERT INTO portfolio_snapshots (date, week, total_assets, total_pnl, total_cost, update_time)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (date_str, week_str, total_assets, total_pnl, total_cost, now.strftime('%Y-%m-%d %H:%M:%S')))
            return True
        except Exception as e:
            logging.error(f"Failed to snapshot portfolio: {e}")
            return False

    def get_snapshots(self, limit: int = 52) -> List[Dict[str, Any]]:
        """获取最近的历史快照"""
        sql = 'SELECT * FROM portfolio_snapshots ORDER BY week ASC LIMIT ?'
        # 注意：这里按周升序，方便前端画图
        # 如果 limit 生效，应该先 DESC 再 ASC？
        # 修正：先取最近的 N 条，再排序
        sql = f'''
            SELECT * FROM (
                SELECT * FROM portfolio_snapshots ORDER BY week DESC LIMIT {limit}
            ) ORDER BY week ASC
        '''
        rows = self.db.fetch_all(sql)
        
        snapshots = []
        for row in rows:
            snapshots.append({
                'date': row[1],
                'week': row[2],
                'total_assets': row[3],
                'total_pnl': row[4],
                'total_cost': row[5]
            })
        return snapshots

    def get_all_accounts(self) -> List[Dict[str, Any]]:
        """获取所有账户"""
        sql = 'SELECT * FROM accounts ORDER BY created_at'
        rows = self.db.fetch_all(sql)
        
        accounts = []
        for row in rows:
            accounts.append({
                'id': row[0],
                'name': row[1],
                'type': row[2],
                'description': row[3],
                'created_at': row[4]
            })
        return accounts

    def add_account(self, name: str, type: str = None, description: str = None) -> int:
        """添加新账户"""
        try:
            sql = '''
                INSERT INTO accounts (name, type, description, created_at) 
                VALUES (?, ?, ?, ?)
            '''
            params = (
                name, 
                type, 
                description,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            return self.db.execute_insert(sql, params)
        except Exception as e:
            logging.error(f"Failed to add account {name}: {e}")
            raise

    def update_account(self, account_id: int, name: str, type: str = None, description: str = None) -> bool:
        """更新账户信息"""
        try:
            sql = '''
                UPDATE accounts 
                SET name = ?, type = ?, description = ?
                WHERE id = ?
            '''
            self.db.execute(sql, (name, type, description, account_id))
            return True
        except Exception as e:
            logging.error(f"Failed to update account {account_id}: {e}")
            return False

    def delete_account(self, account_id: int) -> bool:
        """删除账户"""
        try:
            self.db.execute('DELETE FROM accounts WHERE id = ?', (account_id,))
            return True
        except Exception as e:
            logging.error(f"Failed to delete account {account_id}: {e}")
            return False

    def add_asset(self, data: Dict[str, Any]) -> int:
        """添加新资产"""
        sql = '''
            INSERT INTO asset_holdings (
                account_name, asset_type, category_1, category_2, 
                symbol, name, quantity, cost_price, last_price, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            data['account_name'],
            data['asset_type'],
            data.get('category_1'),
            data.get('category_2'),
            data['symbol'],
            data.get('name', ''),
            data.get('quantity', 0),
            data.get('cost_price', 0),
            data.get('last_price', 0),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        )
        return self.db.execute_insert(sql, params)

    def update_asset(self, asset_id: int, data: Dict[str, Any]) -> bool:
        """更新资产信息"""
        fields = []
        values = []
        
        valid_fields = ['account_name', 'asset_type', 'category_1', 'category_2', 
                       'symbol', 'name', 'quantity', 'cost_price', 'last_price']
        
        for field in valid_fields:
            if field in data:
                fields.append(f"{field} = ?")
                values.append(data[field])
                
        if not fields:
            return False
            
        fields.append("update_time = ?")
        values.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        values.append(asset_id)
        
        sql = f'''
            UPDATE asset_holdings 
            SET {', '.join(fields)}
            WHERE id = ?
        '''
        
        try:
            self.db.execute(sql, tuple(values))
            return True
        except Exception as e:
            logging.error(f"Failed to update asset {asset_id}: {e}")
            return False

    def delete_asset(self, asset_id: int) -> bool:
        """删除资产"""
        try:
            self.db.execute('DELETE FROM asset_holdings WHERE id = ?', (asset_id,))
            return True
        except Exception as e:
            logging.error(f"Failed to delete asset {asset_id}: {e}")
            return False

    def get_all_assets(self) -> List[Dict[str, Any]]:
        """获取所有资产记录"""
        sql = 'SELECT * FROM asset_holdings ORDER BY category_1, category_2'
        rows = self.db.fetch_all(sql)
        
        assets = []
        for row in rows:
            assets.append({
                'id': row[0],
                'account_name': row[1],
                'asset_type': row[2],
                'category_1': row[3],
                'category_2': row[4],
                'symbol': row[5],
                'name': row[6],
                'quantity': row[7],
                'cost_price': row[8],
                'update_time': row[9],
                'last_price': row[10] if len(row) > 10 else 0
            })
        return assets

    def get_asset_by_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取资产"""
        sql = 'SELECT * FROM asset_holdings WHERE id = ?'
        row = self.db.fetch_one(sql, (asset_id,))
        
        if row:
            return {
                'id': row[0],
                'account_name': row[1],
                'asset_type': row[2],
                'category_1': row[3],
                'category_2': row[4],
                'symbol': row[5],
                'name': row[6],
                'quantity': row[7],
                'cost_price': row[8],
                'update_time': row[9]
            }
        return None
