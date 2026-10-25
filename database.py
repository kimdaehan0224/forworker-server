# ─── database.py ──────────────────────────────────────────────
# SQLite DB 연결 및 CRUD 함수 모음이에요.
# 테이블 3개: missions(미션 목록), cache(API 응답 캐시), mission_completion(완료 기록)
# main.py에서 import해서 사용해요.

import sqlite3
import os
import json
import random
from datetime import datetime, timedelta, date

# DB 파일 경로: 환경변수 DB_PATH 우선, 없으면 같은 폴더의 forworker.db 사용
# Railway 배포 시 환경변수로 경로 지정 가능
DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(__file__), 'forworker.db'))

# ─── DB 연결 ─────────────────────────────────────────────────
# row_factory = sqlite3.Row → 결과를 dict처럼 row['컬럼명']으로 접근 가능
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ─── DB 초기화 ────────────────────────────────────────────────
# 서버 시작 시 한 번 호출 (main.py startup 이벤트)
# 테이블이 없으면 생성, missions가 비어있으면 기본 데이터 10개 삽입
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # 미션 목록 테이블 (id, 제목, 설명, 카테고리, 생성일)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # API 응답 캐시 테이블 (key, value(JSON), 만료시간)
    # 분리수거 168시간, 복지/미션 24시간 TTL
    cur.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    ''')

    # 미션 완료 기록 테이블 (device_id + mission_id 조합으로 식별)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS mission_completion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            mission_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (mission_id) REFERENCES missions(id)
        )
    ''')

    # missions 테이블이 비어있을 때만 기본 미션 10개 삽입
    cur.execute('SELECT COUNT(*) FROM missions')
    if cur.fetchone()[0] == 0:
        default_missions = [
            ('분리수거 실천', '오늘 분리수거를 올바르게 해보세요. 플라스틱, 종이, 캔을 분류하여 배출해요.', '환경'),
            ('한국어 인사 배우기', '오늘 한국 이웃에게 한국어로 인사해보세요. \"안녕하세요!\"', '문화'),
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

# 캐시 읽기: key로 조회, 만료 안 됐으면 JSON 파싱해서 반환 / 없거나 만료면 None
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

# 캐시 쓰기: key-value 저장, hours 후 만료
# INSERT OR REPLACE → 같은 key면 덮어씀
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

# 전체 미션 목록 조회 (id 순 정렬)
def get_missions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM missions ORDER BY id')
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows

# 특정 기기가 완료한 미션 ID 목록 반환
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
    """날짜 기반 시드로 매일 3개 고정 미션 반환 (날짜 바뀌면 자동 교체)

    오늘 날짜(YYYYMMDD)를 random 시드로 사용해서
    같은 날에 접속하면 항상 동일한 3개 미션이 나옴.
    날짜가 바뀌면 자동으로 새 미션 3개로 교체됨.
    """
    missions = get_missions()
    completed = get_completed_missions(device_id)

    # 날짜를 시드로 → 같은 날은 항상 같은 3개
    today = date.today().isoformat()
    random.seed(int(today.replace("-", "")))
    daily = random.sample(missions, min(3, len(missions)))
    random.seed()  # 다른 곳에 영향 안 주도록 시드 초기화

    # 각 미션에 완료 여부 추가
    for m in daily:
        m["completed"] = m["id"] in completed
    return daily

# 미션 완료 처리: 이미 완료한 미션이면 False, 새로 완료하면 True 반환
def complete_mission(device_id: str, mission_id: int):
    conn = get_conn()
    cur = conn.cursor()
    # 중복 완료 방지: 이미 기록 있으면 False 반환
    cur.execute(
        'SELECT id FROM mission_completion WHERE device_id = ? AND mission_id = ?',
        (device_id, mission_id)
    )
    if cur.fetchone():
        conn.close()
        return False
    # 완료 기록 INSERT
    conn.execute(
        'INSERT INTO mission_completion (device_id, mission_id) VALUES (?, ?)',
        (device_id, mission_id)
    )
    conn.commit()
    conn.close()
    return True

# 미션 완료 취소: mission_completion 테이블에서 해당 기록 DELETE
def cancel_mission(device_id: str, mission_id: int):
    """완료된 미션을 취소하여 mission_completion 테이블에서 삭제"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'DELETE FROM mission_completion WHERE device_id = ? AND mission_id = ?',
        (device_id, mission_id)
    )
    conn.commit()
    conn.close()
    return {"success": True, "message": "미션이 취소되었습니다."}