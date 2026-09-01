from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from fastapi.responses import StreamingResponse
import io
import pandas as pd
import joblib
import numpy as np
import sqlite3
from datetime import datetime
import asyncio
import socketio
import uvicorn
import re  
import os
import shutil

# ========== تنظیمات اولیه ==========
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ========== امنیت ==========
security = HTTPBasic()

# ========== مدل ==========
model = joblib.load('risk_model_xgb.pkl')
scaler = joblib.load('scaler.pkl')

# ========== Socket.IO ==========
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_app = socketio.ASGIApp(sio, app)

# ========== کلاس‌های مدل ==========
class SensorData(BaseModel):
    temperature: float
    pressure: float
    flow_rate: float
    level: float

class ThresholdUpdate(BaseModel):
    param_name: str
    low_max: float
    medium_max: float
    high_min: float

class HazopScenario(BaseModel):
    scenario_name: str
    node: str
    deviation: str
    cause: str
    consequence: str
    probability: int
    consequence_severity: int
    mitigation: str = ""

# ========== دیتابیس ==========
DB_PATH = "hazop_final.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # ---------- جداول اصلی ----------
    cursor.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temperature REAL, pressure REAL, flow_rate REAL, level REAL,
        risk_level INTEGER, confidence REAL, root_cause TEXT, created_at TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password TEXT,
        fullname TEXT,
        personnel_code TEXT,
        phone TEXT,
        role TEXT DEFAULT 'operator',
        created_at TEXT
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS risk_thresholds (
        param_name TEXT PRIMARY KEY, low_max REAL, medium_max REAL, high_min REAL)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS risk_matrix (
        id INTEGER PRIMARY KEY,
        probability INTEGER, consequence INTEGER,
        risk_level TEXT, risk_score INTEGER, category TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS hazop_scenarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_name TEXT, node TEXT, deviation TEXT, cause TEXT, consequence TEXT,
        probability INTEGER, consequence_severity INTEGER,
        risk_score INTEGER, risk_level TEXT, mitigation TEXT, created_at TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS hazard_tree (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id TEXT UNIQUE, name TEXT, parent_id TEXT,
        guideword TEXT, description TEXT, icon TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS severity_levels (
        level INTEGER PRIMARY KEY,
        name TEXT, human_impact TEXT, financial_impact TEXT, downtime TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS likelihood_levels (
        level INTEGER PRIMARY KEY,
        name TEXT, frequency TEXT, description TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS scenario_thresholds (
        scenario_name TEXT PRIMARY KEY,
        critical_threshold INTEGER, action_required TEXT)''')

    # ---------- حذف داده‌های قبلی (برای بازسازی تمیز) ----------
    cursor.execute("DELETE FROM hazard_tree")
    cursor.execute("DELETE FROM severity_levels")
    cursor.execute("DELETE FROM likelihood_levels")
    cursor.execute("DELETE FROM scenario_thresholds")
    cursor.execute("DELETE FROM risk_matrix")
    cursor.execute("DELETE FROM hazop_scenarios")
    cursor.execute("DELETE FROM risk_thresholds")
    cursor.execute("DELETE FROM users")

    # ---------- کاربران ----------
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('operator', 'op123', 'operator')")

    

    # ========== مدل ثبت‌نام ==========
    class RegisterData(BaseModel):
        fullname: str
        personnel_code: str  # کد ملی 10 رقمی
        phone: str
        username: str
        password: str
        confirm_password: str

    @app.post("/register")
    async def register_user(data: RegisterData):
        # بررسی کد ملی (10 رقم)
        if not re.match(r'^\d{10}$', data.personnel_code):
            raise HTTPException(status_code=400, detail="کد پرسنلی باید 10 رقم باشد")
        
        # بررسی شماره تلفن (11 رقم، شروع با 09)
        if not re.match(r'^09\d{9}$', data.phone):
            raise HTTPException(status_code=400, detail="شماره تلفن باید 11 رقم و با 09 شروع شود")
        
        # بررسی نام کاربری (فقط حروف انگلیسی و اعداد)
        if not re.match(r'^[a-zA-Z0-9_]{4,20}$', data.username):
            raise HTTPException(status_code=400, detail="نام کاربری باید 4-20 حرف انگلیسی یا عدد باشد")
        
        # بررسی رمز عبور (حداقل 6 کاراکتر)
        if len(data.password) < 6:
            raise HTTPException(status_code=400, detail="رمز عبور باید حداقل 6 کاراکتر باشد")
        
        # بررسی تطابق رمزها
        if data.password != data.confirm_password:
            raise HTTPException(status_code=400, detail="رمز عبور با تکرار آن مطابقت ندارد")
        
        conn = get_db()
        cursor = conn.cursor()
        
        # بررسی تکراری نبودن نام کاربری
        cursor.execute("SELECT username FROM users WHERE username = ?", (data.username,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="نام کاربری قبلاً ثبت شده است")
        
        # ذخیره کاربر جدید (با سطح دسترسی operator)
        cursor.execute("INSERT INTO users (username, password, fullname, personnel_code, phone) VALUES (?, ?, ?, ?, ?)",
                    (data.username, data.password, data.fullname, data.personnel_code, data.phone))
        conn.commit()
        conn.close()
        
        return {"message": "ثبت‌نام با موفقیت انجام شد", "username": data.username, "role": "operator"}

    # ---------- آستانه پیش‌فرض ----------
    cursor.execute("INSERT INTO risk_thresholds VALUES ('temperature', 170, 190, 190)")
    cursor.execute("INSERT INTO risk_thresholds VALUES ('pressure', 6.0, 7.5, 7.5)")

    # ---------- ماتریس ۵×۵ ----------
    for p in range(1, 6):
        for c in range(1, 6):
            score = p * c
            if score <= 4:
                risk_level = "Low"
                category = "Acceptable"
            elif score <= 12:
                risk_level = "Medium"
                category = "ALARP"
            else:
                risk_level = "High"
                category = "Unacceptable"
            cursor.execute('''INSERT INTO risk_matrix (probability, consequence, risk_level, risk_score, category)
                              VALUES (?, ?, ?, ?, ?)''', (p, c, risk_level, score, category))

    # ---------- سناریوهای نمونه ----------
    sample_scenarios = [
        ('فشار بیش از حد', 'واحد تقطیر', 'فشار بالا', 'خرابی شیر اطمینان', 'انفجار و آتش‌سوزی', 3, 5, 15, 'High', 'نصب شیر اطمینان اضافی'),
        ('دمای پایین', 'واحد کراکینگ', 'دمای پایین', 'خطا در کنترلر دما', 'کاهش راندمان', 2, 3, 6, 'Medium', 'تنظیم مجدد کنترلر'),
        ('نشت مواد', 'مخازن', 'نشت', 'خوردگی لوله', 'آلودگی محیط زیست', 4, 4, 16, 'High', 'بازرسی دوره‌ای'),
    ]
    for s in sample_scenarios:
        cursor.execute('''INSERT INTO hazop_scenarios
            (scenario_name, node, deviation, cause, consequence, probability, consequence_severity, risk_score, risk_level, mitigation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], s[9], datetime.now().isoformat()))

    # ---------- درخت خطر ----------
    main_cats = [
        ('1.1', 'خطرات فرآیندی (Process Safety)', '0', 'All', 'فشار، دما، سطح، جریان', '⚙️'),
        ('1.2', 'خطرات آتش و انفجار', '0', 'Fire/Explosion', 'نشت گاز، انفجار، آتش', '🔥'),
        ('1.3', 'خطرات سمی و محیط‌زیستی', '0', 'Toxic', 'H2S، نشت نفت، آلودگی', '☠️'),
        ('1.4', 'خطرات مکانیکی و ساختاری', '0', 'Mechanical', 'شکست، خوردگی، فرسایش', '🔧'),
        ('1.5', 'خطرات انسانی و عملیاتی', '0', 'Human', 'خطای اپراتور، عدم مجوز', '👤'),
        ('1.6', 'خطرات سیستم‌های کنترل', '0', 'Control', 'Failure DCS, ESD, SIS', '🎛️'),
    ]
    for cat in main_cats:
        cursor.execute('''INSERT INTO hazard_tree (category_id, name, parent_id, guideword, description, icon)
                          VALUES (?, ?, ?, ?, ?, ?)''', cat)

    sub_11 = [
        ('1.1.1', 'Overpressure / فشار بیش از حد', '1.1', 'High Pressure', 'ترکیدگی تجهیزات تحت فشار', '📈'),
        ('1.1.2', 'Undertemperature / دمای پایین', '1.1', 'Low Temperature', 'تجزیه حرارتی، واکنش ناخواسته', '❄️'),
        ('1.1.3', 'Overfilling / سرریز', '1.1', 'High Level', 'سرریز تانک‌ها', '💧'),
        ('1.1.4', 'Runaway Reaction', '1.1', 'Runaway', 'واکنش کنترل‌نشده', '💥'),
        ('1.1.5', 'Utility Failure', '1.1', 'Utility', 'از دست رفتن برق، بخار، نیتروژن', '⚡'),
    ]
    for sub in sub_11:
        cursor.execute('''INSERT INTO hazard_tree (category_id, name, parent_id, guideword, description, icon)
                          VALUES (?, ?, ?, ?, ?, ?)''', sub)

    sub_12 = [
        ('1.2.1', 'نشت گاز قابل اشتعال (LPG/LNG)', '1.2', 'Gas Leak', 'انفجار VCE', '💨'),
        ('1.2.2', 'انفجار مخزن (BLEVE)', '1.2', 'BLEVE', 'انفجار در مخازن ذخیره', '💣'),
        ('1.2.3', 'آتش سطحی (Pool Fire)', '1.2', 'Pool Fire', 'آتش زیر تجهیزات', '🔥'),
        ('1.2.4', 'Jet Fire', '1.2', 'Jet Fire', 'ناشی از شکست خط فشار بالا', '🔫'),
    ]
    for sub in sub_12:
        cursor.execute('''INSERT INTO hazard_tree (category_id, name, parent_id, guideword, description, icon)
                          VALUES (?, ?, ?, ?, ?, ?)''', sub)

    sub_13 = [
        ('1.3.1', 'انتشار H2S / گازهای سمی', '1.3', 'Toxic Gas', 'سولفید هیدروژن، آمونیاک', '☠️'),
        ('1.3.2', 'نشت نفت و محصولات', '1.3', 'Oil Spill', 'آلودگی خاک و آب', '🛢️'),
        ('1.3.3', 'آلودگی هوا (فلر، فاضلاب)', '1.3', 'Air Pollution', 'انتشار آلاینده‌ها', '🌫️'),
    ]
    for sub in sub_13:
        cursor.execute('''INSERT INTO hazard_tree (category_id, name, parent_id, guideword, description, icon)
                          VALUES (?, ?, ?, ?, ?, ?)''', sub)

    # ---------- Severity ----------
    severity_data = [
        (1, 'جزئی (S1)', 'بدون آسیب انسانی', 'کمتر از 10,000 دلار', 'کمتر از 1 ساعت'),
        (2, 'متوسط (S2)', 'جراحت جزئی / سرپایی', '10,000 - 100,000 دلار', '1-8 ساعت'),
        (3, 'شدید (S3)', 'آسیب جدی / بستری کوتاه', '100,000 - 1,000,000 دلار', '1-3 روز'),
        (4, 'خیلی شدید (S4)', 'یک مورد مرگ احتمالی', '1,000,000 - 5,000,000 دلار', '3-7 روز'),
        (5, 'فاجعه‌بار (S5)', 'چندین مرگ', 'بیشتر از 5,000,000 دلار', 'بیشتر از 7 روز'),
    ]
    for s in severity_data:
        cursor.execute('''INSERT INTO severity_levels (level, name, human_impact, financial_impact, downtime)
                          VALUES (?, ?, ?, ?, ?)''', s)

    # ---------- Likelihood ----------
    likelihood_data = [
        (1, 'بسیار کم (L1)', 'هر 10 سال یکبار', 'تقریباً غیرممکن'),
        (2, 'کم (L2)', 'هر 5 سال یکبار', 'در شرایط خاص محتمل است'),
        (3, 'متوسط (L3)', 'سالانه یکبار', 'ممکن است رخ دهد'),
        (4, 'زیاد (L4)', 'ماهانه یکبار', 'محتمل است رخ دهد'),
        (5, 'بسیار زیاد (L5)', 'هفتگی یکبار', 'به دفعات رخ می‌دهد'),
    ]
    for l in likelihood_data:
        cursor.execute('''INSERT INTO likelihood_levels (level, name, frequency, description)
                          VALUES (?, ?, ?, ?)''', l)

    # ---------- آستانه بحرانی سناریوها ----------
    threshold_data = [
        ('نشت H2S', 16, 'ایمنی سطح بالا: Double containment, H2S detection, escape mask, evacuation plan'),
        ('فشار بیش از حد', 20, 'بررسی شیرهای اطمینان، نصب PSV اضافی'),
        ('نشت مواد سمی', 15, 'سیستم تشخیص نشت، تجهیزات حفاظت فردی'),
    ]
    for t in threshold_data:
        cursor.execute('''INSERT OR IGNORE INTO scenario_thresholds (scenario_name, critical_threshold, action_required)
                          VALUES (?, ?, ?)''', t)

    conn.commit()
    conn.close()
    print("✅ دیتابیس با موفقیت ساخته شد")

def save_prediction(data):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO predictions
        (temperature, pressure, flow_rate, level, risk_level, confidence, root_cause, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['temperature'], data['pressure'], data['flow_rate'], data['level'],
         data['risk_level'], data['confidence'], data['root_cause'], datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_thresholds():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT param_name, low_max, medium_max, high_min FROM risk_thresholds")
    rows = cursor.fetchall()
    conn.close()
    return {row['param_name']: {'low_max': row['low_max'], 'medium_max': row['medium_max'], 'high_min': row['high_min']} for row in rows}

def update_threshold(param_name, low_max, medium_max, high_min):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE risk_thresholds SET low_max=?, medium_max=?, high_min=? WHERE param_name=?", 
                   (low_max, medium_max, high_min, param_name))
    conn.commit()
    conn.close()

# ========== توابع کمکی ==========
def verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (credentials.username, credentials.password))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials.username

def verify_admin(username: str = Depends(verify_auth)):
    if username != 'admin':
        raise HTTPException(status_code=403, detail="فقط ادمین مجاز است")
    return username

def root_cause_analysis(temp, pressure, flow, level, risk_level):
    causes = []
    if risk_level == 2:
        if temp > 190: causes.append("دمای بیش از حد (>190°C)")
        if pressure > 7.5: causes.append("فشار بیش از حد (>7.5 bar)")
    elif risk_level == 1:
        if temp > 170: causes.append("دمای نزدیک به حد خطر")
        if pressure > 6.0: causes.append("فشار نزدیک به حد خطر")
    if not causes:
        causes.append("همه پارامترها در محدوده ایمن")
    return " | ".join(causes)

# ========== API ها ==========
@app.post("/predict")
async def predict(data: SensorData, username: str = Depends(verify_auth)):
    features = np.array([[data.temperature, data.pressure, data.flow_rate, data.level]])
    features_scaled = scaler.transform(features)
    risk_level = int(model.predict(features_scaled)[0])
    confidence = float(np.max(model.predict_proba(features_scaled)[0]))
    root_cause = root_cause_analysis(data.temperature, data.pressure, data.flow_rate, data.level, risk_level)

    save_prediction({
        'temperature': data.temperature, 'pressure': data.pressure,
        'flow_rate': data.flow_rate, 'level': data.level,
        'risk_level': risk_level, 'confidence': confidence, 'root_cause': root_cause
    })

    await sio.emit('new_prediction', {
        'risk_level': risk_level, 'root_cause': root_cause,
        'confidence': confidence, 'timestamp': datetime.now().isoformat()
    })

    return {
        'risk_level': risk_level,
        'risk_color': 'red' if risk_level == 2 else ('orange' if risk_level == 1 else 'green'),
        'confidence': round(confidence, 2),
        'root_cause': root_cause
    }

@app.get("/history")
async def get_history(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT temperature, pressure, flow_rate, level, risk_level, confidence, root_cause, created_at FROM predictions ORDER BY id DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()
    return [{'temperature': r[0], 'pressure': r[1], 'flow_rate': r[2], 'level': r[3],
             'risk_level': r[4], 'confidence': r[5], 'root_cause': r[6], 'created_at': r[7]} for r in rows]

@app.get("/stats")
async def get_stats(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT risk_level, COUNT(*) FROM predictions GROUP BY risk_level")
    stats = dict(cursor.fetchall())
    conn.close()
    return {'low': stats.get(0, 0), 'medium': stats.get(1, 0), 'high': stats.get(2, 0)}

@app.get("/thresholds")
async def get_threshold_settings(username: str = Depends(verify_auth)):
    return get_thresholds()

@app.get("/unit-ranking")
async def get_unit_ranking(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT root_cause, COUNT(*) as count
        FROM predictions
        WHERE risk_level = 2
        GROUP BY root_cause
        ORDER BY count DESC
        LIMIT 5
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{'cause': row['root_cause'][:40] if row['root_cause'] else "نامشخص", 'count': row['count']} for row in rows]

@app.get("/alert-history")
async def get_alert_history(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT risk_level, root_cause, created_at
        FROM predictions
        WHERE risk_level >= 1
        ORDER BY id DESC
        LIMIT 10
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{'risk_level': r[0], 'root_cause': r[1], 'created_at': r[2]} for r in rows]


@app.put("/thresholds")
async def update_threshold_settings(data: ThresholdUpdate, username: str = Depends(verify_admin)):
    update_threshold(data.param_name, data.low_max, data.medium_max, data.high_min)
    return {'message': f'آستانه {data.param_name} بروزرسانی شد'}

@app.get("/risk-matrix")
async def get_risk_matrix(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT probability, consequence, risk_level, risk_score, category FROM risk_matrix ORDER BY probability, consequence")
    rows = cursor.fetchall()
    conn.close()
    matrix = [[None for _ in range(5)] for _ in range(5)]
    for row in rows:
        matrix[row['probability']-1][row['consequence']-1] = {
            'risk_level': row['risk_level'],
            'score': row['risk_score'],
            'category': row['category']
        }
    return {'matrix': matrix, 'levels': ['Acceptable', 'ALARP', 'Unacceptable']}

@app.get("/hazop-scenarios")
async def get_hazop_scenarios(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hazop_scenarios ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/hazop-scenarios")
async def add_hazop_scenario(data: HazopScenario, username: str = Depends(verify_admin)):
    risk_score = data.probability * data.consequence_severity
    if risk_score <= 4:
        risk_level = "Low"
    elif risk_score <= 12:
        risk_level = "Medium"
    else:
        risk_level = "High"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO hazop_scenarios
        (scenario_name, node, deviation, cause, consequence, probability, consequence_severity, risk_score, risk_level, mitigation, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data.scenario_name, data.node, data.deviation, data.cause, data.consequence,
         data.probability, data.consequence_severity, risk_score, risk_level, data.mitigation, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {'message': 'سناریو اضافه شد', 'risk_level': risk_level}

@app.delete("/hazop-scenarios/{scenario_id}")
async def delete_hazop_scenario(scenario_id: int, username: str = Depends(verify_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM hazop_scenarios WHERE id = ?", (scenario_id,))
    conn.commit()
    conn.close()
    return {'message': 'سناریو حذف شد'}

@app.get("/hazard-tree")
async def get_hazard_tree(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT category_id, name, parent_id, guideword, description, icon FROM hazard_tree ORDER BY category_id")
    rows = cursor.fetchall()
    conn.close()
    return [{'id': r[0], 'name': r[1], 'parent': r[2], 'guideword': r[3], 'description': r[4], 'icon': r[5]} for r in rows]

@app.get("/severity-levels")
async def get_severity_levels(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT level, name, human_impact, financial_impact, downtime FROM severity_levels ORDER BY level")
    rows = cursor.fetchall()
    conn.close()
    return [{'level': r[0], 'name': r[1], 'human_impact': r[2], 'financial_impact': r[3], 'downtime': r[4]} for r in rows]

@app.get("/likelihood-levels")
async def get_likelihood_levels(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT level, name, frequency, description FROM likelihood_levels ORDER BY level")
    rows = cursor.fetchall()
    conn.close()
    return [{'level': r[0], 'name': r[1], 'frequency': r[2], 'description': r[3]} for r in rows]

@app.get("/scenario-thresholds")
async def get_scenario_thresholds(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT scenario_name, critical_threshold, action_required FROM scenario_thresholds")
    rows = cursor.fetchall()
    conn.close()
    return [{'scenario_name': r[0], 'critical_threshold': r[1], 'action_required': r[2]} for r in rows]

# ========== مدیریت کاربران (فقط ادمین) ==========
@app.get("/admin/users")
async def get_all_users(username: str = Depends(verify_admin)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username, fullname, personnel_code, phone, role, created_at FROM users ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{'username': r[0], 'fullname': r[1], 'personnel_code': r[2], 'phone': r[3], 'role': r[4], 'created_at': r[5]} for r in rows]

@app.delete("/admin/users/{username}")
async def delete_user(username: str, admin_user: str = Depends(verify_admin)):
    if username == 'admin':
        raise HTTPException(status_code=403, detail="نمی‌توان ادمین اصلی را حذف کرد")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username = ?", (username,))
    conn.commit()
    conn.close()
    return {'message': f'کاربر {username} حذف شد'}

class CreateOperatorData(BaseModel):
    fullname: str
    personnel_code: str
    phone: str
    username: str
    password: str

@app.post("/admin/users")
async def create_operator(data: CreateOperatorData, admin_user: str = Depends(verify_admin)):
    import re
    
    if not re.match(r'^\d{10}$', data.personnel_code):
        raise HTTPException(status_code=400, detail="کد پرسنلی باید 10 رقم باشد")
    if not re.match(r'^09\d{9}$', data.phone):
        raise HTTPException(status_code=400, detail="شماره تلفن باید 11 رقم و با 09 شروع شود")
    if not re.match(r'^[a-zA-Z0-9_]{4,20}$', data.username):
        raise HTTPException(status_code=400, detail="نام کاربری باید 4-20 حرف انگلیسی یا عدد باشد")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="رمز عبور باید حداقل 6 کاراکتر باشد")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT username FROM users WHERE username = ?", (data.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="نام کاربری قبلاً ثبت شده است")
    
    cursor.execute('''INSERT INTO users (username, password, fullname, personnel_code, phone, role, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?)''',
                   (data.username, data.password, data.fullname, data.personnel_code, data.phone, 'operator', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return {"message": "اپراتور با موفقیت اضافه شد", "username": data.username}

# ========== شبیه‌ساز بلادرنگ ==========
async def data_simulator():
    while True:
        await asyncio.sleep(5)
        temp = np.random.normal(175, 25)
        press = np.random.normal(5.5, 1.5)
        flow = np.random.normal(210, 50)
        level = np.random.uniform(30, 70)
        features = np.array([[temp, press, flow, level]])
        features_scaled = scaler.transform(features)
        risk = int(model.predict(features_scaled)[0])
        await sio.emit('sensor_data', {
            'temperature': temp, 'pressure': press,
            'risk_level': risk, 'timestamp': datetime.now().isoformat()
        })

@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(data_simulator())


class RegisterData(BaseModel):
    fullname: str
    personnel_code: str
    phone: str
    username: str
    password: str
    confirm_password: str

@app.post("/register")
async def register_user(data: RegisterData):
    # بررسی کد ملی (10 رقم)
    if not re.match(r'^\d{10}$', data.personnel_code):
        raise HTTPException(status_code=400, detail="کد پرسنلی باید 10 رقم باشد")
    
    # بررسی شماره تلفن (11 رقم، شروع با 09)
    if not re.match(r'^09\d{9}$', data.phone):
        raise HTTPException(status_code=400, detail="شماره تلفن باید 11 رقم و با 09 شروع شود")
    
    # بررسی نام کاربری (فقط حروف انگلیسی و اعداد، 4-20 کاراکتر)
    if not re.match(r'^[a-zA-Z0-9_]{4,20}$', data.username):
        raise HTTPException(status_code=400, detail="نام کاربری باید 4-20 حرف انگلیسی یا عدد باشد")
    
    # بررسی رمز عبور (حداقل 6 کاراکتر)
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="رمز عبور باید حداقل 6 کاراکتر باشد")
    
    # بررسی تطابق رمزها
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="رمز عبور با تکرار آن مطابقت ندارد")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # بررسی تکراری نبودن نام کاربری
    cursor.execute("SELECT username FROM users WHERE username = ?", (data.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="نام کاربری قبلاً ثبت شده است")
    
    # ذخیره کاربر جدید
    cursor.execute('''
        INSERT INTO users (username, password, fullname, personnel_code, phone, role, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (data.username, data.password, data.fullname, data.personnel_code, data.phone, 'operator', datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return {"message": "ثبت‌نام با موفقیت انجام شد", "username": data.username, "role": "operator"}

# ========== خروجی Excel ==========

@app.get("/export-excel")
async def export_excel(username: str = Depends(verify_auth)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM predictions ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        raise HTTPException(status_code=404, detail="داده‌ای برای خروجی وجود ندارد")
    
    data = []
    for row in rows:
        data.append(dict(row))
    df = pd.DataFrame(data)
    
    if 'id' in df.columns:
        df = df.drop('id', axis=1)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Risk History', index=False)
    
    output.seek(0)
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=hazop_history.xlsx"}
    )
#=======پشتیبانی از دیتا بیس ========
@app.get("/backup-db")
async def backup_database(username: str = Depends(verify_admin)):
    import shutil
    from datetime import datetime
    
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="فایل دیتابیس یافت نشد")
    
    backup_name = f"backup_hazop_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    backup_path = os.path.join(os.path.dirname(DB_PATH), backup_name)
    
    shutil.copy2(DB_PATH, backup_path)
    
    return StreamingResponse(
        open(backup_path, "rb"),
        media_type="application/x-sqlite3",
        headers={"Content-Disposition": f"attachment; filename={backup_name}"}
    )

if __name__ == "__main__":
    uvicorn.run(socket_app, host="0.0.0.0", port=8000)