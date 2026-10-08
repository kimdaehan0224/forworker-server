import sqlite3
import os
import json
import random
from datetime import datetime, timedelta, date

DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'forworker.db'))

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS mission_completion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            mission_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mission_id) REFERENCES missions(id)
        )
    ''')

    cur.execute('SELECT COUNT(*) FROM missions')
    if cur.fetchone()[0] == 0:
        default_missions = [
            ('분리수거 실천', '오늘 분리수거를 올바르게 해보세요. 플라스틱, 종이, 캔을 분류하여 배출해요.', '환경'),
            ('한국어 인사 배우기', '오늘 한국 이웃에게 한국어로 인사해보세요. "안녕하세요!"', '문화'),
            ('대중교통 이용하기', '오늘 버스나 지하철을 이용해보세요. T머니 카드를 사용하면 할인돼요.', '교통'),
            ('복지정책 확인하기', '앱에서 내 지역 복지정책을 하나 확인해보세요.', '복지'),
            ('비닐봉투 대신 장바구니', '오늘 장을 볼 때 비닐봉투 대신 장바구니를 사용해보세요.', '환경'),
            ('긴급전화 번호 외우기', '119(소방/응급), 112(경찰), 1345(외국인지원) 번호를 기억해두세요.', '안전'),
            ('약국 방문해보기', '가까운 약국 위치를 확인하고, 필요하면 간단한 약을 구매해보세요.', '건강'),
            ('퀴즈 1문제 풀기', '앱에서 한국 생활 퀴즈를 1문제 풀어보세요.', '학습'),
            ('이웃에게 인사하기', '오늘 엘리베이터나 복도에서 이웃을 만나면 인사해보세요.', '문화'),
            ('재활용 분리수거함 확인', '우리 아파트/건물의 분리수거함 위치를 확인해보세요.', '환경'),
        ]
        cur.executemany(
            'INSERT INTO missions (title, description, category) VALUES (?, ?, ?)',
            default_missions
        )

    conn.commit()
    conn.close()
    print("DB 초기화 완료")


# ===== 캐시 =====

def get_cache(key: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT value FROM cache WHERE key = ? AND expires_at > ?',
        (key, datetime.now().isoformat())
    )
    row = cur.fetchone()
    conn.close()
    return json.loads(row['value']) if row else None

def set_cache(key: str, value, hours: int = 24):
    conn = get_conn()
    expires_at = (datetime.now() + timedelta(hours=hours)).isoformat()
    conn.execute(
        'INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)',
        (key, json.dumps(value, ensure_ascii=False), expires_at)
    )
    conn.commit()
    conn.close()


# ===== 미션 =====

def get_missions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM missions ORDER BY id')
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows

def get_completed_missions(device_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT mission_id FROM mission_completion WHERE device_id = ?',
        (device_id,)
    )
    ids = [row['mission_id'] for row in cur.fetchall()]
    conn.close()
    return ids

def get_daily_missions(device_id: str):
    """날짜 기반 시드로 매일 3개 고정 미션 반환 (날짜 바뀌면 자동 교체)"""
    missions = get_missions()
    completed = get_completed_missions(device_id)

    # 날짜를 시드로 → 같은 날은 항상 같은 3개
    today = date.today().isoformat()
    random.seed(int(today.replace("-", "")))
    daily = random.sample(missions, min(3, len(missions)))
    random.seed()  # 시드 초기화

    for m in daily:
        m["completed"] = m["id"] in completed
    return daily

def complete_mission(device_id: str, mission_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT id FROM mission_completion WHERE device_id = ? AND mission_id = ?',
        (device_id, mission_id)
    )
    if cur.fetchone():
        conn.close()
        return False
    conn.execute(
        'INSERT INTO mission_completion (device_id, mission_id) VALUES (?, ?)',
        (device_id, mission_id)
    )
    conn.commit()
    conn.close()
    return True
