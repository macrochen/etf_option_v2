from ..database import Database

def upgrade(db: Database):
    """创建方案管理表"""
    db.execute('''
        CREATE TABLE IF NOT EXISTS backtest_schemes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE,
            params TEXT NOT NULL,
            results TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    ''')

def downgrade(db: Database):
    """删除方案管理表"""
    db.execute('DROP TABLE IF EXISTS backtest_schemes') 