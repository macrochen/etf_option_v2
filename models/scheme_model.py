import sqlite3
from datetime import datetime
import json

class SchemeModel:
    @staticmethod
    def check_scheme_exists(name):
        """检查方案是否已存在"""
        with sqlite3.connect('data/schemes.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM schemes WHERE name = ?', (name,))
            return cursor.fetchone() is not None

    @staticmethod
    def save_scheme(data):
        """保存方案"""
        with sqlite3.connect('data/schemes.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS schemes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    params TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            cursor.execute('''
                INSERT INTO schemes (name, params, created_at)
                VALUES (?, ?, ?)
            ''', (data['name'], json.dumps(data['params']), data['created_at']))
            conn.commit() 