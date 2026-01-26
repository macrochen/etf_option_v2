import sqlite3
import logging
from db.config import HPC_DB

class HPCDatabase:
    def __init__(self):
        self.db_path = HPC_DB
        self.init_tables()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_tables(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 1. 策略实例表 (Strategy Instance)
        # 用于管理不同的跟投计划，如 "长赢计划", "螺丝钉" 等
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hpc_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,           -- 策略名称
                source_url TEXT,              -- 目标组合URL (用于爬虫)
                current_equity DECIMAL(18, 4) DEFAULT 0, -- 本地跟投总权益 (计算基数)
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 2. 虚拟基准持仓表 (Virtual Target Positions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hpc_virtual_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER,          
                target_code TEXT NOT NULL,    
                target_name TEXT,             
                target_type TEXT,             -- 资产类型 (一级)
                target_category_2 TEXT,       -- [New] 二级分类
                weight DECIMAL(5, 4),         
                base_shares DECIMAL(18, 4) DEFAULT 0, 
                latest_nav DECIMAL(10, 4) DEFAULT 1,  
                source_type TEXT DEFAULT 'MANUAL',    
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(strategy_id) REFERENCES hpc_strategies(id)
            )
        ''')
        
        # Migration: Add columns if not exist
        try: cursor.execute("ALTER TABLE hpc_virtual_holdings ADD COLUMN target_type TEXT")
        except: pass
        try: cursor.execute("ALTER TABLE hpc_virtual_holdings ADD COLUMN weight DECIMAL(5, 4)")
        except: pass
        try: cursor.execute("ALTER TABLE hpc_virtual_holdings ADD COLUMN target_category_2 TEXT")
        except: pass

        # 3. 资产映射规则表 (Asset Mappings)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hpc_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER,
                target_code TEXT,             
                
                local_code TEXT,              
                local_name TEXT,              
                local_type TEXT,              
                allocation_ratio DECIMAL(5, 4) DEFAULT 1.0, 
                
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY(strategy_id) REFERENCES hpc_strategies(id)
            )
        ''')

        # 4. 二级分类配置表 (Category Config)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hpc_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_order INTEGER DEFAULT 0
            )
        ''')
        
        # Pre-seed defaults if empty
        if cursor.execute("SELECT count(*) FROM hpc_categories").fetchone()[0] == 0:
            defaults = ['宽基', '行业', '红利', '策略', '债券', '现金', '海外', '商品']
            for i, d in enumerate(defaults):
                cursor.execute("INSERT INTO hpc_categories (name, display_order) VALUES (?, ?)", (d, i))

        conn.commit()
        conn.close()
        logging.info("HPC tables initialized.")

    # --- Category CRUD ---
    def get_categories(self):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM hpc_categories ORDER BY display_order, id").fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def add_category(self, name):
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO hpc_categories (name) VALUES (?)", (name,))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def delete_category(self, cid):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM hpc_categories WHERE id=?", (cid,))
        conn.commit()
        conn.close()

    # --- Strategy CRUD ---
    def create_strategy(self, name, equity, url=""):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO hpc_strategies (name, current_equity, source_url) VALUES (?, ?, ?)", 
                       (name, equity, url))
        sid = cursor.lastrowid
        conn.commit()
        conn.close()
        return sid

    def get_all_strategies(self):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM hpc_strategies ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_strategy(self, sid):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM hpc_strategies WHERE id=?", (sid,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_strategy_equity(self, sid, equity):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE hpc_strategies SET current_equity = ? WHERE id = ?", (equity, sid))
        conn.commit()
        conn.close()

    # --- Virtual Holdings CRUD ---
    def upsert_virtual_holding(self, strategy_id, code, name, shares, nav, source='MANUAL', type='', weight=0, cat2=''):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check if exists
        exist = cursor.execute("SELECT id FROM hpc_virtual_holdings WHERE strategy_id=? AND target_code=?", (strategy_id, code)).fetchone()
        
        if exist:
            cursor.execute('''
                UPDATE hpc_virtual_holdings 
                SET target_name=?, base_shares=?, latest_nav=?, source_type=?, target_type=?, weight=?, target_category_2=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            ''', (name, shares, nav, source, type, weight, cat2, exist[0]))
        else:
            cursor.execute('''
                INSERT INTO hpc_virtual_holdings (strategy_id, target_code, target_name, base_shares, latest_nav, source_type, target_type, weight, target_category_2)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (strategy_id, code, name, shares, nav, source, type, weight, cat2))
            
        conn.commit()
        conn.close()

    def update_virtual_holding_cat2(self, strategy_id, target_code, cat2):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE hpc_virtual_holdings SET target_category_2 = ? WHERE strategy_id=? AND target_code=?", 
                       (cat2, strategy_id, target_code))
        conn.commit()
        conn.close()

    def get_virtual_holdings(self, strategy_id):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM hpc_virtual_holdings WHERE strategy_id=?", (strategy_id,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # --- Mappings CRUD ---
    def get_mappings(self, strategy_id, target_code):
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM hpc_mappings WHERE strategy_id=? AND target_code=?", (strategy_id, target_code)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def save_mapping(self, strategy_id, target_code, mappings):
        # mappings is a list of dicts: [{local_code, local_type, ratio, ...}]
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Strategy: Delete old mappings for this target, insert new ones (Full replace)
        cursor.execute("DELETE FROM hpc_mappings WHERE strategy_id=? AND target_code=?", (strategy_id, target_code))
        
        for m in mappings:
            cursor.execute('''
                INSERT INTO hpc_mappings (strategy_id, target_code, local_code, local_name, local_type, allocation_ratio)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (strategy_id, target_code, m['local_code'], m.get('local_name',''), m['local_type'], m['ratio']))
            
        conn.commit()
        conn.close()
