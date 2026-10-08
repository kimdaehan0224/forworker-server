# 퀴즈 생성 관련 로직이에요. (Gemini API 활용)
import httpx
import os
import json
import random
import time
import asyncio


CATEGORIES = [
    "분리수거", "한국 문화", "복지 상식", "대중교통",
    "생활 예절", "행정 절차", "음식 문화", "의료·약국 이용"
]

LANG_MAP = {
    'ko': '한국어',
    'en': '영어',
    'zh': '중국어',
    'vi': '베트남어',
    'ru': '러시아어',
}

FALLBACK_QUIZ = {
    "category": "분리수거",
    "question": "한국에서 페트병을 버릴 때 올바른 방법은?",
    "options": ["그냥 버린다", "라벨 제거 후 찌그러뜨려서 버린다", "음식물 쓰레기통에 버린다", "종이류와 함께 버린다"],
    "answer": 1,
    "explanation": "페트병은 라벨을 제거하고 찌그러뜨린 후 플라스틱 분리수거함에 버려야 해요."
}


async def generate_quiz(language: str = "ko"):
    api_key = os.getenv('GEMINI_API_KEY', '')
    selected_category = random.choice(CATEGORIES)
    lang_name = LANG_MAP.get(language, '한국어')

    prompt = f"""
한국 {selected_category} 관련 상식 퀴즈 1개를 {lang_name}로 만들어줘.
반드시 아래 JSON 형식으로만 응답해. 다른 텍스트는 절대 포함하지 마.

{{
    "category": "{selected_category}",
    "question": "질문 내용",
    "options": ["보기1", "보기2", "보기3", "보기4"],
    "answer": 0,
    "explanation": "정답 해설"
}}

answer는 정답 보기의 인덱스(0~3)이야.
"""

    for attempt in range(2):
        try:
            start_time = time.time()

            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f'https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}',
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=30
                )

            elapsed = time.time() - start_time
            print(f"Gemini 응답 시간: {elapsed:.2f}초 (시도 {attempt+1})")

            data = res.json()
            print("상태코드:", res.status_code)
            text = data['candidates'][0]['content']['parts'][0]['text']
            text = text.strip().replace('```json', '').replace('```', '').strip()
            quiz = json.loads(text)
            return {"success": True, "quiz": quiz}

        except Exception as e:
            import traceback
            print(f"퀴즈 생성 오류 (시도 {attempt+1}): {e}")
            print(traceback.format_exc())
            if attempt == 0:
                print("1초 후 재시도...")
                await asyncio.sleep(1)
            if attempt == 1:
                return {"success": False, "quiz": FALLBACK_QUIZ}