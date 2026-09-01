import sqlite3
from datetime import datetime

DB_PATH = "hazop_final.db"

def get_db_connection():
    """ایجاد اتصال جدید به دیتابیس"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """ایجاد همه جداول مورد نیاز"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول پیش‌بینی‌ها
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL, pressure REAL, flow_rate REAL, level REAL,
            risk_level INTEGER, confidence REAL, root_cause TEXT, created_at TEXT
        )
    ''')
    
    # جدول هشدارها
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            risk_level INTEGER, message TEXT, sent_email BOOLEAN, created_at TEXT
        )
    ''')
    
    # جدول کاربران
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, password TEXT
        )
    ''')
    
    # جدول دسته‌بندی ریسک (برای سوال 1 استاد)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS risk_categories (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            parent_id INTEGER DEFAULT 0,
            min_threshold REAL,
            max_threshold REAL
        )
    ''')
    
    # جدول تنظیمات آستانه (Set Points) برای سوال 3
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS risk_thresholds (
            param_name TEXT PRIMARY KEY,
            low_min REAL, low_max REAL,
            medium_min REAL, medium_max REAL,
            high_min REAL, high_max REAL
        )
    ''')
    
    # درج کاربر پیش‌فرض
    cursor.execute("INSERT OR IGNORE INTO users VALUES ('admin', 'admin123')")
    
    # درج تنظیمات پیش‌فرض آستانه
    cursor.execute("INSERT OR IGNORE INTO risk_thresholds VALUES ('temperature', 0, 170, 170, 190, 190, 300)")
    cursor.execute("INSERT OR IGNORE INTO risk_thresholds VALUES ('pressure', 0, 6.0, 6.0, 7.5, 7.5, 20)")
    cursor.execute("INSERT OR IGNORE INTO risk_thresholds VALUES ('flow_rate', 0, 200, 200, 250, 250, 500)")
    
    # درج دسته‌بندی‌های اولیه ریسک (برای سوال 1)
    cursor.execute("INSERT OR IGNORE INTO risk_categories (id, name, parent_id, min_threshold, max_threshold) VALUES (1, 'آتش‌سوزی', 0, 150, 300)")
    cursor.execute("INSERT OR IGNORE INTO risk_categories (id, name, parent_id, min_threshold, max_threshold) VALUES (2, 'انفجار', 0, 180, 350)")
    cursor.execute("INSERT OR IGNORE INTO risk_categories (id, name, parent_id, min_threshold, max_threshold) VALUES (3, 'نشت مواد', 0, 160, 280)")
    cursor.execute("INSERT OR IGNORE INTO risk_categories (id, name, parent_id, min_threshold, max_threshold) VALUES (4, 'خرابی تجهیزات', 0, 170, 310)")
    
    conn.commit()
    conn.close()
    print("✅ دیتابیس مقداردهی اولیه شد")

def save_prediction(data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO predictions (temperature, pressure, flow_rate, level, risk_level, confidence, root_cause, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data['temperature'], data['pressure'], data['flow_rate'], data['level'], 
          data['risk_level'], data['confidence'], data['root_cause'], datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_thresholds():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT param_name, low_max, medium_max, high_min FROM risk_thresholds")
    rows = cursor.fetchall()
    conn.close()
    return {row['param_name']: {'low_max': row['low_max'], 'medium_max': row['medium_max'], 'high_min': row['high_min']} for row in rows}

def update_threshold(param_name, low_max, medium_max, high_min):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE risk_thresholds SET low_max=?, medium_max=?, high_min=? WHERE param_name=?", 
                   (low_max, medium_max, high_min, param_name))
    conn.commit()
    conn.close()

def get_risk_categories():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, parent_id, min_threshold, max_threshold FROM risk_categories")
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r['id'], 'name': r['name'], 'parent_id': r['parent_id'], 'min_threshold': r['min_threshold'], 'max_threshold': r['max_threshold']} for r in rows]