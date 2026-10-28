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
import logging
import time
import traceback

# ─── 로깅 설정 (Railway 로그에서 시간 표시) ───────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

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
async def gemini_translate(items: list, lang_name: str, fields: list) -> list:
    """items 리스트를 6개씩 배치로 나눠 Gemini 호출로 번역"""
    api_key = os.getenv('GEMINI_API_KEY', '')
    field_str = ', '.join(fields)
    result = []
    batch_size = 6

    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        items_text = json.dumps(batch, ensure_ascii=False)

        prompt = f"""아래 JSON 배열의 {field_str} 필드를 {lang_name}로 번역해줘.
반드시 동일한 JSON 배열 구조로만 응답해. 다른 텍스트는 절대 포함하지 마.

{items_text}"""

        for attempt in range(3):
            try:
                start = time.time()
                async with httpx.AsyncClient() as client:
                    res = await client.post(
                        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}',
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                        timeout=60
                    )
                elapsed = time.time() - start
                data = res.json()

                if 'candidates' not in data or not data['candidates']:
                    err = data.get('error', {}).get('message', 'candidates 없음')
                    logger.warning(f"[Gemini] 재시도 {attempt+1}/3 | 배치 {i//batch_size+1} | {elapsed:.2f}s | {err}")
                    await asyncio.sleep(2)
                    continue

                logger.info(f"[Gemini] 번역 완료 | {lang_name} | 배치 {i//batch_size+1} | {elapsed:.2f}s | {len(batch)}개")
                text = data['candidates'][0]['content']['parts'][0]['text']
                text = text.strip().replace('```json', '').replace('```', '').strip()
                batch_result = json.loads(text)
                result.extend(batch_result)
                break

            except httpx.ReadTimeout:
                logger.error(f"[Gemini] 타임아웃 | 배치 {i//batch_size+1} | 시도 {attempt+1}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"[Gemini] 오류 | 배치 {i//batch_size+1} | 시도 {attempt+1} | {e}")
                traceback.print_exc()
                if attempt == 2:
                    raise
                await asyncio.sleep(2)

    return result


# ─── 서버 시작 이벤트 ─────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()
    logger.info("[서버] Forworker API 시작")

# ─── 헬스체크 ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "Forworker API 서버가 실행 중이에요"}


# ─── 캐시 삭제 ────────────────────────────────────────────────
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
    logger.info(f"[캐시] {msg}")
    return {"success": True, "message": msg}


# ─── 분리수거 정보 ────────────────────────────────────────────
@app.get("/recycling/{city}")
async def get_recycling(city: str, language: str = "ko"):
    from crawler import get_recycling_data

    cache_key = f"recycling:{city}:{language}"
    cached = get_cache(cache_key)
    if cached:
        logger.info(f"[캐시 히트] {cache_key}")
        return {"city": city, "language": language, "items": cached, "cached": True}

    items = get_recycling_data(city)

    if language == "ko":
        set_cache(cache_key, items, hours=168)
        return {"city": city, "language": language, "items": items}

    try:
        translated = await gemini_translate(items, LANG_MAP.get(language, '영어'), ['category', 'description'])
        set_cache(cache_key, translated, hours=168)
        return {"city": city, "language": language, "items": translated}
    except Exception as e:
        logger.error(f"[분리수거] 번역 오류: {e}")
        traceback.print_exc()
        return {"city": city, "language": "ko", "items": items}


# ─── 복지 정책 ────────────────────────────────────────────────
@app.get("/welfare/{city}")
async def get_welfare(city: str, language: str = "ko"):
    from welfare import fetch_welfare

    cache_key = f"welfare:{city}:{language}"
    cached = get_cache(cache_key)
    if cached:
        logger.info(f"[캐시 히트] {cache_key}")
        return {"city": city, "language": language, "items": cached, "cached": True}

    ko_key = f"welfare:{city}:ko"
    items = get_cache(ko_key)
    if not items:
        items = await fetch_welfare(city)
        set_cache(ko_key, items, hours=24)

    if language == "ko":
        return {"city": city, "language": language, "items": items}

    try:
        lang_name = LANG_MAP.get(language, '영어')
        translated = await gemini_translate(items, lang_name, ['title', 'description'])
        for i, item in enumerate(translated):
            item['link'] = items[i].get('link', '')
            item['target'] = items[i].get('target', '')
        set_cache(cache_key, translated, hours=24)
        return {"city": city, "language": language, "items": translated}
    except Exception as e:
        logger.error(f"[복지정책] 번역 오류: {e}")
        traceback.print_exc()
        return {"city": city, "language": "ko", "items": items}


# ─── 기도 시간 ────────────────────────────────────────────────
@app.get("/prayer")
async def get_prayer(lat: float, lng: float):
    from prayer import fetch_prayer_times
    return await fetch_prayer_times(lat, lng)


# ─── 퀴즈 ────────────────────────────────────────────────────
@app.get("/quiz")
async def get_quiz(language: str = "ko"):
    from quiz import generate_quiz
    return await generate_quiz(language)


# ─── 미션 목록 ────────────────────────────────────────────────
@app.get("/missions")
async def get_missions_list(device_id: str, language: str = "ko"):
    from database import get_daily_missions
    from datetime import date

    daily = get_daily_missions(device_id)
    today = date.today().isoformat()

    if language == "ko":
        return {"missions": daily, "date": today}

    ids = [m["id"] for m in daily]
    cache_key = f"missions:{'-'.join(map(str, ids))}:{language}"
    cached = get_cache(cache_key)
    if cached:
        for i, m in enumerate(cached):
            m["completed"] = daily[i]["completed"]
        return {"missions": cached, "date": today}

    try:
        lang_name = LANG_MAP.get(language, '영어')
        translated = await gemini_translate(daily, lang_name, ['title', 'description'])
        for i, m in enumerate(translated):
            m["id"] = daily[i]["id"]
            m["completed"] = daily[i]["completed"]
            m["category"] = daily[i].get("category", "")
        set_cache(cache_key, translated, hours=24)
        return {"missions": translated, "date": today}
    except Exception as e:
        logger.error(f"[미션] 번역 오류: {e}")
        traceback.print_exc()
        return {"missions": daily, "date": today}


# ─── 미션 완료 처리 ───────────────────────────────────────────
@app.post("/missions/{mission_id}/complete")
def complete_mission_endpoint(mission_id: int, device_id: str):
    result = complete_mission(device_id, mission_id)
    if result:
        return {"success": True, "message": "미션 완료!"}
    else:
        return {"success": False, "message": "이미 완료한 미션이에요"}


# ─── 미션 완료 취소 ───────────────────────────────────────────
@app.delete("/missions/{mission_id}/complete")
def cancel_mission_endpoint(mission_id: int, device_id: str):
    result = cancel_mission(device_id, mission_id)
    return result


# ─── 할랄 식당 검색 ───────────────────────────────────────────
@app.get("/halal/nearby")
async def get_halal_nearby(lat: float, lng: float, radius: int = 5000):
    from forworker_map import fetch_places_by_category
    places = await fetch_places_by_category(lat, lng, 'halal', radius)
    return {"restaurants": places, "total": len(places)}


# ─── 장소 검색 (카페 / 관광명소 등) ──────────────────────────
@app.get("/places/nearby")
async def get_places_nearby(lat: float, lng: float, category: str = "cafe", radius: int = 5000):
    from forworker_map import fetch_places_by_category
    places = await fetch_places_by_category(lat, lng, category, radius)
    return {"places": places, "category": category, "total": len(places)}