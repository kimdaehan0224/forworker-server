# 크롤링 파일이에요.
# 시흥시/안산시 홈페이지에서 분리수거 정보를 가져와요.

import requests
from bs4 import BeautifulSoup

# 안산시 분리수거 페이지 크롤링
def crawl_ansan_recycling():
    url = "https://www.ansan.go.kr/www/common/bbs/selectBbsDetail.do?key=497&bbs_code=B0274&bbs_seq=1074814"
    
    try:
        # 한국 정부 사이트는 User-Agent 필요해요
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        print("크롤링 시도:", url)
        classes = [tag.get('class') for tag in soup.find_all('div') if tag.get('class')]
        print("div 클래스들:", classes[:10])

        # 본문 텍스트 추출
        # 안산시 게시판 본문 영역 찾기
        # 안산시는 class="skip" 안에 본문이 있어요
        content = soup.find('div', class_='skip')

        if content:
            text = content.get_text(separator='\n', strip=True)
            return parse_recycling_text(text)
        else:
            print("안산시 본문 영역을 찾지 못했어요")
            return get_ansan_hardcoded()

    except Exception as e:
        print(f"안산시 크롤링 오류: {e}")
        return get_ansan_hardcoded()


# 크롤링한 텍스트를 카테고리별로 파싱하는 함수
def parse_recycling_text(text: str):
    items = []
    # ▶ 로 시작하는 카테고리 분리
    sections = text.split('▶')
    for section in sections[1:]:  # 첫 번째는 헤더라 건너뜀
        lines = [l.strip() for l in section.strip().split('\n') if l.strip()]
        if not lines:
            continue
        category = lines[0].replace(':', '').strip()
        description = ' '.join(lines[1:4])  # 앞 3줄만 요약
        items.append({
            "category": category,
            "description": description
        })
    return items if items else get_ansan_hardcoded()


# 크롤링 실패 시 하드코딩 데이터 (안산시)
def get_ansan_hardcoded():
    return [
        {"category": "종이류", "description": "신문지, 책, 공책 등. 비닐코팅, 스프링 제거 후 끈으로 묶어서 배출"},
        {"category": "종이팩", "description": "우유팩, 음료수팩, 종이컵. 내용물 비우고 물로 헹군 후 압착하여 배출"},
        {"category": "유리병류", "description": "음료수·술병, 식료품병. 병뚜껑 제거 후 내용물 깨끗이 비우고 배출"},
        {"category": "캔·고철류", "description": "철캔, 알루미늄캔, 살충제·부탄가스 용기. 구멍 뚫어 내용물 비운 후 배출"},
        {"category": "플라스틱류", "description": "페트병 등 플라스틱 용기류. 내용물 깨끗이 비우고 다른 재질 제거 후 배출"},
        {"category": "스티로폼", "description": "가전제품 포장재, 과일 상자. 테이프, 오염물질 제거 후 묶어서 배출"},
        {"category": "비닐류", "description": "1회용 비닐봉투, 포장 필름류. 내용물 비우고 이물질 제거 후 봉투에 담아 배출"},
        {"category": "폐형광등·폐건전지", "description": "형광램프, 폐건전지. 전용수거함에 배출"},
    ]


# 시흥시 분리수거 하드코딩 데이터 (이미지라 크롤링 불가)
def get_siheung_hardcoded():
    return [
        {"category": "종이류", "description": "신문지, 책, 종이상자 등. 비닐코팅, 테이프 제거 후 끈으로 묶어서 배출"},
        {"category": "종이팩", "description": "우유팩, 음료수팩. 내용물 비우고 물로 헹군 후 압착하여 배출"},
        {"category": "유리병류", "description": "음료수·술병, 식료품병. 병뚜껑 제거 후 내용물 비우고 배출"},
        {"category": "캔·고철류", "description": "철캔, 알루미늄캔. 내용물 비우고 가능한 압착하여 배출"},
        {"category": "플라스틱류", "description": "페트병 등 플라스틱 용기. 내용물 비우고 라벨 제거 후 찌그러뜨려서 배출"},
        {"category": "스티로폼", "description": "가전제품 포장재, 과일 상자. 이물질 제거 후 배출"},
        {"category": "비닐류", "description": "1회용 비닐봉투, 포장 필름류. 이물질 제거 후 봉투에 담아 배출"},
        {"category": "폐형광등·폐건전지", "description": "형광램프, 폐건전지. 전용수거함에 배출"},
    ]


# 도시별 분리수거 정보 반환 함수
def get_recycling_data(city: str):
    if city == 'ansan':
        return crawl_ansan_recycling()
    elif city == 'siheung':
        return get_siheung_hardcoded()
    else:
        return []