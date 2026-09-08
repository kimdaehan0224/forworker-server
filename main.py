# Forworker 백엔드 서버 메인 파일이에요.
# FastAPI로 만든 서버로, 앱에서 필요한 데이터를 제공해요.

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

# FastAPI 앱 생성
app = FastAPI(title="Forworker API")

# CORS 설정 - 앱에서 서버에 접근할 수 있게 해줘요
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 서버 상태 확인용 엔드포인트
@app.get("/")
def root():
    return {"status": "ok", "message": "Forworker API 서버가 실행 중이에요"}

# 분리수거 정보 엔드포인트 (임시 더미 데이터)
# 분리수거 정보 엔드포인트 (크롤링 데이터)
@app.get("/recycling/{city}")
def get_recycling(city: str):
    # crawler.py에서 실제 데이터 가져오기
    from crawler import get_recycling_data
    items = get_recycling_data(city)
    return {"city": city, "items": items}
    # city: siheung 또는 ansan
    data = {
        "siheung": [
            {"category": "플라스틱", "description": "라벨 제거 후 찌그러뜨려서 배출"},
            {"category": "종이류", "description": "물기 제거 후 묶어서 배출"},
            {"category": "유리병", "description": "내용물 비우고 뚜껑 분리 후 배출"},
            {"category": "캔류", "description": "내용물 비우고 찌그러뜨려서 배출"},
            {"category": "음식물", "description": "물기 제거 후 음식물 전용 봉투에 배출"},
        ],
        "ansan": [
            {"category": "플라스틱", "description": "라벨 제거 후 찌그러뜨려서 배출"},
            {"category": "종이류", "description": "물기 제거 후 묶어서 배출"},
            {"category": "유리병", "description": "내용물 비우고 뚜껑 분리 후 배출"},
            {"category": "캔류", "description": "내용물 비우고 찌그러뜨려서 배출"},
            {"category": "음식물", "description": "물기 제거 후 음식물 전용 봉투에 배출"},
        ]
    }
    # 요청한 도시 데이터 반환, 없으면 빈 리스트
    return {"city": city, "items": data.get(city, [])}

# 복지 정책 엔드포인트 (임시 더미 데이터)
# 복지 정책 엔드포인트 (공공데이터 API 연동)
@app.get("/welfare/{city}")
async def get_welfare(city: str):
    import httpx
    import os
    from urllib.parse import unquote
    import xml.etree.ElementTree as ET

    # 도시명 매핑
    city_names = {
        'siheung': '시흥시',
        'ansan': '안산시',
    }

    api_key = os.getenv('WELFARE_API_KEY', '')
    city_name = city_names.get(city, '시흥시')

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                'https://apis.data.go.kr/B554287/LocalGovernmentWelfareInformations/LcgvWelfarelist',
                params={
                    'serviceKey': unquote(api_key),
                    'pageNo': '1',
                    'numOfRows': '1000000',  # 많이 가져와서 필터링
                    'sggNm': city_name,
                },
                timeout=15
            )

        root = ET.fromstring(res.text)
        items = []

        for item in root.findall('.//servList'):
            sgg = item.findtext('sggNm') or ''

            # 시흥시 또는 안산시 데이터만 필터링
            if city_name not in sgg:
                continue

            title = item.findtext('servNm') or ''
            desc = item.findtext('servDgst') or ''
            life_nm = item.findtext('lifeNmArray') or ''
            link = item.findtext('servDtlLink') or ''

            items.append({
                'title': title,
                'description': desc,
                'target': life_nm,
                'link': link,
            })

        if items:
            return {'city': city, 'items': items}
        else:
            print(f"{city_name} 데이터 없음, 더미 반환")
            return {'city': city, 'items': get_welfare_dummy()}

    except Exception as e:
        print(f"복지 API 오류: {e}")
        return {'city': city, 'items': get_welfare_dummy()}


# 복지 더미 데이터 (API 실패 시 대체)
def get_welfare_dummy():
    return [
        {
            'title': '외국인 근로자 의료비 지원',
            'description': '건강보험 미가입 외국인 근로자 의료비 지원',
            'target': '외국인',
            'link': ''
        },
        {
            'title': '이주민 한국어 교육 지원',
            'description': '무료 한국어 교육 프로그램 운영',
            'target': '외국인',
            'link': ''
        },
        {
            'title': '외국인 근로자 생활안정자금 대출',
            'description': '저금리 생활안정자금 대출 지원',
            'target': '외국인',
            'link': ''
        },
    ]

# 기도 시간 엔드포인트 (aladhan API 중계)
@app.get("/prayer")
async def get_prayer(lat: float, lng: float):
    import httpx
    from datetime import datetime

    today = datetime.now()
    date_str = f"{today.day}-{today.month}-{today.year}"

    # aladhan.com API 호출
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"https://api.aladhan.com/v1/timings/{date_str}",
            params={"latitude": lat, "longitude": lng, "method": 3}
        )
        data = res.json()

    if data.get("code") == 200:
        timings = data["data"]["timings"]
        return {
            "Fajr": timings["Fajr"],
            "Dhuhr": timings["Dhuhr"],
            "Asr": timings["Asr"],
            "Maghrib": timings["Maghrib"],
            "Isha": timings["Isha"],
        }
    return {"error": "기도 시간을 불러오지 못했어요"}

# 퀴즈 엔드포인트 (Gemini API로 퀴즈 자동 생성)
@app.get("/quiz")
async def get_quiz(category: str = "분리수거", language: str = "ko"):
    import httpx
    import os
    import json

    api_key = os.getenv('GEMINI_API_KEY', '')

    # 언어별 프롬프트
    lang_map = {
        'ko': '한국어',
        'en': '영어',
        'zh': '중국어',
        'vi': '베트남어',
        'ru': '러시아어',
    }
    lang_name = lang_map.get(language, '한국어')

    prompt = f"""
한국 {category} 관련 상식 퀴즈 1개를 {lang_name}로 만들어줘.
반드시 아래 JSON 형식으로만 응답해. 다른 텍스트는 절대 포함하지 마.

{{
  "question": "질문 내용",
  "options": ["보기1", "보기2", "보기3", "보기4"],
  "answer": 0,
  "explanation": "정답 해설"
}}

answer는 정답 보기의 인덱스(0~3)이야.
"""

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}',
                json={
                    "contents": [{"parts": [{"text": prompt}]}]
                },
                timeout=15
            )

        data = res.json()
        print("Gemini 응답:", data)  # 추가 08 22
        text = data['candidates'][0]['content']['parts'][0]['text']

        # JSON 파싱
        text = text.strip().replace('```json', '').replace('```', '').strip()
        quiz = json.loads(text)
        return {"success": True, "quiz": quiz}

    except Exception as e:
        print(f"퀴즈 생성 오류: {e}")
        # 실패 시 하드코딩 퀴즈 반환
        return {
            "success": False,
            "quiz": {
                "question": "한국에서 페트병을 버릴 때 올바른 방법은?",
                "options": ["그냥 버린다", "라벨 제거 후 찌그러뜨려서 버린다", "음식물 쓰레기통에 버린다", "종이류와 함께 버린다"],
                "answer": 1,
                "explanation": "페트병은 라벨을 제거하고 찌그러뜨린 후 플라스틱 분리수거함에 버려야 해요."
            }
        }