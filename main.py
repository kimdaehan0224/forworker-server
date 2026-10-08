# Forworker 백엔드 서버 메인 파일이에요.
# FastAPI로 만든 서버로, 앱에서 필요한 데이터를 제공해요.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from database import init_db, get_cache, set_cache, complete_mission
import asyncio
import os
import httpx
import json

load_dotenv()

app = FastAPI(title="Forworker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LANG_MAP = {'ko': '한국어', 'en': '영어', 'zh': '중국어', 'vi': '베트남어', 'ru': '러시아어'}
    
async def gemini_translate(items: list, lang_name: str, fields: list) -> list:
    """items 리스트를 배치로 묶어 Gemini 1번 호출로 번역"""
    api_key = os.getenv('GEMINI_API_KEY', '')
    items_text = json.dumps(items, ensure_ascii=False)
    field_str = ', '.join(fields)

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
        
        # candidates 없으면 재시도
        if 'candidates' not in data or not data['candidates']:
            print(f"번역 재시도 {attempt+1}: {data.get('error', {}).get('message', 'candidates 없음')}")
            await asyncio.sleep(2)
            continue
            
        text = data['candidates'][0]['content']['parts'][0]['text']
        text = text.strip().replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    
    raise Exception("번역 실패: 3회 재시도 후에도 candidates 없음")


@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def root():
    return {"status": "ok", "message": "Forworker API 서버가 실행 중이에요"}


# 분리수거 (크롤링 + 캐시 + LLM 번역)
@app.get("/recycling/{city}")
async def get_recycling(city: str, language: str = "ko"):
    from crawler import get_recycling_data

    cache_key = f"recycling:{city}:{language}"
    cached = get_cache(cache_key)
    if cached:
        print(f"캐시 히트: {cache_key}")
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
        print(f"번역 오류: {e}")
        return {"city": city, "language": "ko", "items": items}


# 복지 정책 (캐시 + LLM 번역)
@app.get("/welfare/{city}")
async def get_welfare(city: str, language: str = "ko"):
    from welfare import fetch_welfare

    cache_key = f"welfare:{city}:{language}"
    cached = get_cache(cache_key)
    if cached:
        print(f"캐시 히트: {cache_key}")
        return {"city": city, "language": language, "items": cached, "cached": True}

    # 한국어 원본 먼저 가져오기
    ko_key = f"welfare:{city}:ko"
    items = get_cache(ko_key)
    if not items:
        items = await fetch_welfare(city)
        set_cache(ko_key, items, hours=24)

    if language == "ko":
        return {"city": city, "language": language, "items": items}

    try:
        # title, description 배치 번역
        lang_name = LANG_MAP.get(language, '영어')
        translated = await gemini_translate(items, lang_name, ['title', 'description'])
        # link, target은 원본 유지
        for i, item in enumerate(translated):
            item['link'] = items[i].get('link', '')
            item['target'] = items[i].get('target', '')
        set_cache(cache_key, translated, hours=24)
        return {"city": city, "language": language, "items": translated}
    except Exception as e:
        print(f"복지정책 번역 오류: {e}")
        return {"city": city, "language": "ko", "items": items}


# 기도시간
@app.get("/prayer")
async def get_prayer(lat: float, lng: float):
    from prayer import fetch_prayer_times
    return await fetch_prayer_times(lat, lng)


# 퀴즈
@app.get("/quiz")
async def get_quiz(language: str = "ko"):
    from quiz import generate_quiz
    return await generate_quiz(language)


# 미션 목록 (캐시 + LLM 번역)
@app.get("/missions")
async def get_missions_list(device_id: str, language: str = "ko"):
    from database import get_daily_missions
    from datetime import date

    daily = get_daily_missions(device_id)
    today = date.today().isoformat()

    if language == "ko":
        return {"missions": daily, "date": today}

    # 번역 캐시 확인 (mission id 목록 기반)
    ids = [m["id"] for m in daily]
    cache_key = f"missions:{'-'.join(map(str, ids))}:{language}"
    cached = get_cache(cache_key)
    if cached:
        # completed 상태는 원본에서 가져옴
        for i, m in enumerate(cached):
            m["completed"] = daily[i]["completed"]
        return {"missions": cached, "date": today}

    try:
        lang_name = LANG_MAP.get(language, '영어')
        translated = await gemini_translate(daily, lang_name, ['title', 'description'])
        # completed, id, category 원본 유지
        for i, m in enumerate(translated):
            m["id"] = daily[i]["id"]
            m["completed"] = daily[i]["completed"]
            m["category"] = daily[i].get("category", "")
        set_cache(cache_key, translated, hours=24)
        return {"missions": translated, "date": today}
    except Exception as e:
        print(f"미션 번역 오류: {e}")
        return {"missions": daily, "date": today}


# 미션 완료 처리
@app.post("/missions/{mission_id}/complete")
def complete_mission_endpoint(mission_id: int, device_id: str):
    result = complete_mission(device_id, mission_id)
    if result:
        return {"success": True, "message": "미션 완료!"}
    else:
        return {"success": False, "message": "이미 완료한 미션이에요"}