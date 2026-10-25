# ─── main.py ──────────────────────────────────────────────────
# Forworker 백엔드 서버 진입점이에요.
# FastAPI 기반으로 각 기능별 API 엔드포인트를 정의해요.
# Railway에 배포되며 Procfile로 uvicorn main:app 실행.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from database import init_db, get_cache, set_cache, complete_mission, cancel_mission
import asyncio
import os
import httpx
import json
import sqlite3

# .env 파일에서 환경변수 로드 (GEMINI_API_KEY 등)
load_dotenv()

app = FastAPI(title="Forworker API")

# CORS 설정: 모든 출처 허용 (앱 → 서버 요청 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 언어 코드 → 한국어 언어명 매핑 (Gemini 번역 프롬프트에 사용)
LANG_MAP = {'ko': '한국어', 'en': '영어', 'zh': '중국어', 'vi': '베트남어', 'ru': '러시아어'}

# ─── Gemini 번역 함수 ──────────────────────────────────────────
# items(dict 리스트)의 특정 fields를 lang_name 언어로 일괄 번역
# Gemini API 호출 1회로 배열 전체를 번역해서 비용 절감
# candidates 없을 경우 최대 3회 재시도 후 예외 발생
async def gemini_translate(items: list, lang_name: str, fields: list) -> list:
    """items 리스트를 배치로 묶어 Gemini 1번 호출로 번역"""
    api_key = os.getenv('GEMINI_API_KEY', '')
    items_text = json.dumps(items, ensure_ascii=False)
    field_str = ', '.join(fields)

    # 번역 프롬프트: JSON 배열 구조 유지하면서 지정 필드만 번역 요청
    prompt = f"""아래 JSON 배열의 {field_str} 필드를 {lang_name}로 번역해줘.
반드시 동일한 JSON 배열 구조로만 응답해. 다른 텍스트는 절대 포함하지 마.

{items_text}"""

    for attempt in range(3):  # 최대 3회 재시도
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}',
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
        data = res.json()

        # candidates 없으면 재시도 (quota 초과, 안전 필터 등)
        if 'candidates' not in data or not data['candidates']:
            print(f"번역 재시도 {attempt+1}: {data.get('error', {}).get('message', 'candidates 없음')}")
            await asyncio.sleep(2)
            continue

        # 응답 텍스트에서 ```json 마크다운 제거 후 파싱
        text = data['candidates'][0]['content']['parts'][0]['text']
        text = text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(text)

    raise Exception("번역 실패: 3회 재시도 후에도 candidates 없음")


# ─── 서버 시작 이벤트 ─────────────────────────────────────────
# 서버 기동 시 DB 테이블 생성 + 기본 미션 데이터 삽입
@app.on_event("startup")
def startup():
    init_db()

# ─── 헬스체크 ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "Forworker API 서버가 실행 중이에요"}


# ─── 캐시 삭제 ────────────────────────────────────────────────
# key 파라미터 있으면 해당 키 포함된 캐시만 삭제, 없으면 전체 삭제
# 번역이 이상할 때 캐시 날리고 재번역하기 위해 사용
@app.delete("/cache")
def clear_cache(key: str = None):
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    if key:
        conn.execute("DELETE FROM cache WHERE key LIKE ?", (f"%{key}%",))
        msg = f"'{key}' 관련 캐시 삭제 완료"
    else:
        conn.execute("DELETE FROM cache")
        msg = "전체 캐시 삭제 완료"
    conn.commit()
    conn.close()
    return {"success": True, "message": msg}


# ─── 분리수거 정보 ────────────────────────────────────────────
# crawler.py로 시 공식 사이트 크롤링 → 언어별 번역 → 캐시(168시간)
# 캐시 히트 시 크롤링/번역 없이 즉시 반환
@app.get("/recycling/{city}")
async def get_recycling(city: str, language: str = "ko"):
    from crawler import get_recycling_data

    cache_key = f"recycling:{city}:{language}"
    cached = get_cache(cache_key)
    if cached:
        print(f"캐시 히트: {cache_key}")
        return {"city": city, "language": language, "items": cached, "cached": True}

    # 크롤링으로 한국어 원본 데이터 수집
    items = get_recycling_data(city)

    if language == "ko":
        set_cache(cache_key, items, hours=168)
        return {"city": city, "language": language, "items": items}

    # 한국어 외 언어는 Gemini로 번역
    try:
        translated = await gemini_translate(items, LANG_MAP.get(language, '영어'), ['category', 'description'])
        set_cache(cache_key, translated, hours=168)
        return {"city": city, "language": language, "items": translated}
    except Exception as e:
        print(f"번역 오류: {e}")
        # 번역 실패 시 한국어로 폴백
        return {"city": city, "language": "ko", "items": items}


# ─── 복지 정책 ────────────────────────────────────────────────
# 복지로 API 크롤링 → 언어별 번역 → 캐시(24시간)
# 한국어 원본은 별도 캐시 키로 저장해서 언어 추가 시 재크롤링 방지
@app.get("/welfare/{city}")
async def get_welfare(city: str, language: str = "ko"):
    from welfare import fetch_welfare

    cache_key = f"welfare:{city}:{language}"
    cached = get_cache(cache_key)
    if cached:
        print(f"캐시 히트: {cache_key}")
        return {"city": city, "language": language, "items": cached, "cached": True}

    # 한국어 원본 캐시 확인, 없으면 크롤링
    ko_key = f"welfare:{city}:ko"
    items = get_cache(ko_key)
    if not items:
        items = await fetch_welfare(city)
        set_cache(ko_key, items, hours=24)

    if language == "ko":
        return {"city": city, "language": language, "items": items}

    # 한국어 외 언어는 Gemini로 번역
    # link, target 필드는 번역 불필요 → 원본에서 복사
    try:
        lang_name = LANG_MAP.get(language, '영어')
        translated = await gemini_translate(items, lang_name, ['title', 'description'])
        for i, item in enumerate(translated):
            item['link'] = items[i].get('link', '')
            item['target'] = items[i].get('target', '')
        set_cache(cache_key, translated, hours=24)
        return {"city": city, "language": language, "items": translated}
    except Exception as e:
        print(f"복지정책 번역 오류: {e}")
        return {"city": city, "language": "ko", "items": items}


# ─── 기도 시간 ────────────────────────────────────────────────
# 위도/경도 기반으로 기도 시간 계산 (prayer.py에서 외부 API 호출)
@app.get("/prayer")
async def get_prayer(lat: float, lng: float):
    from prayer import fetch_prayer_times
    return await fetch_prayer_times(lat, lng)


# ─── 퀴즈 ────────────────────────────────────────────────────
# Gemini로 한국 생활 퀴즈 생성 + 언어별 번역 (quiz.py)
@app.get("/quiz")
async def get_quiz(language: str = "ko"):
    from quiz import generate_quiz
    return await generate_quiz(language)


# ─── 미션 목록 ────────────────────────────────────────────────
# 날짜 시드로 오늘의 미션 3개 반환 + 기기별 완료 여부 포함
# 번역 결과는 캐시에 저장, 완료 여부는 항상 실시간 반영
@app.get("/missions")
async def get_missions_list(device_id: str, language: str = "ko"):
    from database import get_daily_missions
    from datetime import date

    # 날짜 시드 기반 오늘의 미션 3개 + 완료 여부
    daily = get_daily_missions(device_id)
    today = date.today().isoformat()

    if language == "ko":
        return {"missions": daily, "date": today}

    # 번역 캐시 키: 미션 ID 조합 + 언어 (날짜 바뀌면 ID도 달라져서 자동 무효화)
    ids = [m["id"] for m in daily]
    cache_key = f"missions:{'-'.join(map(str, ids))}:{language}"
    cached = get_cache(cache_key)
    if cached:
        # 캐시 히트: 번역본 반환하되 완료 여부는 실시간으로 덮어씀
        for i, m in enumerate(cached):
            m["completed"] = daily[i]["completed"]
        return {"missions": cached, "date": today}

    # 캐시 미스: Gemini로 번역
    try:
        lang_name = LANG_MAP.get(language, '영어')
        translated = await gemini_translate(daily, lang_name, ['title', 'description'])
        # id, completed, category는 원본에서 복사 (번역 대상 아님)
        for i, m in enumerate(translated):
            m["id"] = daily[i]["id"]
            m["completed"] = daily[i]["completed"]
            m["category"] = daily[i].get("category", "")
        set_cache(cache_key, translated, hours=24)
        return {"missions": translated, "date": today}
    except Exception as e:
        print(f"미션 번역 오류: {e}")
        return {"missions": daily, "date": today}


# ─── 미션 완료 처리 ───────────────────────────────────────────
# POST: 미션 완료 → mission_completion에 INSERT
# 이미 완료된 미션이면 success: false 반환
@app.post("/missions/{mission_id}/complete")
def complete_mission_endpoint(mission_id: int, device_id: str):
    result = complete_mission(device_id, mission_id)
    if result:
        return {"success": True, "message": "미션 완료!"}
    else:
        return {"success": False, "message": "이미 완료한 미션이에요"}


# ─── 미션 완료 취소 ───────────────────────────────────────────
# DELETE: 완료 취소 → mission_completion에서 DELETE
# 앱에서 완료된 미션 카드를 다시 탭할 때 호출됨
@app.delete("/missions/{mission_id}/complete")
def cancel_mission_endpoint(mission_id: int, device_id: str):
    result = cancel_mission(device_id, mission_id)
    return result


# ─── 할랄 식당 검색 ───────────────────────────────────────────
@app.get("/halal/nearby")
async def get_halal_nearby(lat: float, lng: float, radius: int = 3000):
    from forworker_map import fetch_halal_restaurants  # ← 여기만 변경
    restaurants = await fetch_halal_restaurants(lat, lng, radius)
    return {"restaurants": restaurants, "count": len(restaurants)}