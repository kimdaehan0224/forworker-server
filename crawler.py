# 크롤링 파일이에요.
# 시흥시/안산시 홈페이지에서 분리수거 정보를 가져와요.

import requests
from bs4 import BeautifulSoup


# 안산시 분리수거 페이지 크롤링
def crawl_ansan_recycling():
    url = "https://www.ansan.go.kr/www/common/cntnts/selectContents.do?cntnts_id=C0001357"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 웹 접근성용 숨겨진 텍스트에 내용이 있음
        content = soup.find('div', class_='skip') or soup.find('div', id='contents') or soup.find('div', class_='contents')

        if content:
            text = content.get_text(separator='\n', strip=True)
            result = parse_ansan_text(text)
            if result:
                return result

        # table 안의 텍스트 추출 시도
        tables = soup.find_all('table')
        if tables:
            result = parse_ansan_tables(tables)
            if result:
                return result

        print("안산시 본문 영역을 찾지 못했어요")
        return get_ansan_hardcoded()

    except Exception as e:
        print(f"안산시 크롤링 오류: {e}")
        return get_ansan_hardcoded()


def parse_ansan_text(text: str):
    """안산시 페이지 텍스트를 카테고리별로 파싱"""
    items = []
    category_keywords = [
        "무색(투명)페트병", "플라스틱류", "비닐류", "스티로폼류",
        "종이팩", "종이류", "금속캔", "유리병류", "옷, 신발, 가방",
        "전지류", "폐형광등"
    ]
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    current_category = None
    current_desc = []

    for line in lines:
        matched = next((kw for kw in category_keywords if kw in line), None)
        if matched:
            if current_category and current_desc:
                items.append({
                    "category": current_category,
                    "description": ' '.join(current_desc[:3])
                })
            current_category = matched
            current_desc = []
        elif current_category and len(current_desc) < 4:
            if len(line) > 3 and '재활용' not in line[:4]:
                current_desc.append(line)

    if current_category and current_desc:
        items.append({
            "category": current_category,
            "description": ' '.join(current_desc[:3])
        })
    return items


def parse_ansan_tables(tables):
    """안산시 테이블 구조 파싱"""
    items = []
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                category = cells[0].get_text(strip=True)
                desc = cells[1].get_text(separator=' ', strip=True)
                if category and len(category) < 20 and desc:
                    items.append({"category": category, "description": desc[:100]})
    return items if len(items) >= 3 else []


# 시흥시 분리수거 페이지 크롤링
def crawl_siheung_recycling():
    url = "https://www.siheung.go.kr/portal/contents.do?mId=0703010300"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 시흥시 본문 영역 탐색
        content = (
            soup.find('div', class_='cont_area') or
            soup.find('div', class_='contents_area') or
            soup.find('div', id='contents') or
            soup.find('div', class_='board_view') or
            soup.find('article')
        )

        if content:
            result = parse_siheung_content(content)
            if result:
                return result

        # table 기반 파싱 시도
        tables = soup.find_all('table')
        if tables:
            result = parse_siheung_tables(tables)
            if result:
                return result

        print("시흥시 본문 영역을 찾지 못했어요")
        return get_siheung_hardcoded()

    except Exception as e:
        print(f"시흥시 크롤링 오류: {e}")
        return get_siheung_hardcoded()


def parse_siheung_content(content):
    """시흥시 페이지 본문 파싱"""
    items = []
    # 시흥시는 품목명이 th 또는 strong 태그에 있을 가능성
    category_map = {
        "골판지": "골판지류",
        "종이팩": "종이팩",
        "신문지": "신문지류",
        "종이컵": "종이컵",
        "유리병": "유리병류",
        "금속캔": "금속캔류",
        "PET": "투명 PET병",
        "합성수지": "플라스틱류",
        "비닐류": "비닐류",
        "발포 합성수지": "스티로폼",
        "의류": "의류·원단",
        "전지류": "폐전지류",
        "형광등": "형광등",
        "소형 가전": "소형가전",
        "식용유": "폐식용유",
    }
    rows = content.find_all('tr')
    for row in rows:
        th = row.find('th')
        td = row.find('td')
        if th and td:
            raw_cat = th.get_text(strip=True)
            desc = td.get_text(separator=' ', strip=True)[:150]
            display_cat = next((v for k, v in category_map.items() if k in raw_cat), raw_cat)
            if display_cat and desc:
                items.append({"category": display_cat, "description": desc})
    return items if len(items) >= 3 else []


def parse_siheung_tables(tables):
    """시흥시 테이블 파싱 (th/td 혼합 구조)"""
    items = []
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['th', 'td'])
            if len(cells) >= 2:
                category = cells[0].get_text(strip=True)
                desc = cells[1].get_text(separator=' ', strip=True)
                if category and 5 < len(category) < 30 and desc and len(desc) > 10:
                    items.append({"category": category, "description": desc[:150]})
    return items if len(items) >= 3 else []


# 크롤링 실패 시 하드코딩 데이터 (안산시)
def get_ansan_hardcoded():
    return [
        {"category": "투명 페트병", "description": "내용물 비우기 → 물로 헹구기 → 라벨 제거 → 압착 후 뚜껑 닫아 배출. 유색 페트병은 플라스틱류로 배출"},
        {"category": "플라스틱류", "description": "내용물 비우기 → 라벨 제거 → 물로 헹군 후 배출. 이물질 묻은 것, 장난감·칫솔·옷걸이 등은 불가"},
        {"category": "비닐류", "description": "내용물 비우기 → 이물질 제거 후 배출. 딱지접듯 접으면 재활용 어려움. 랩필름·장판·고무장갑 불가"},
        {"category": "스티로폼", "description": "내용물 비우기 → 라벨·테이프 제거 후 배출. 음식물 오염·타 재질 코팅된 것 불가"},
        {"category": "종이팩", "description": "내용물 비우기 → 물로 헹구기 → 잘 펴서 말린 후 배출. 행정복지센터에서 휴지 교환 가능"},
        {"category": "종이류", "description": "신문지: 비닐 광고지 섞지 않고 묶어 배출 / 책·노트: 스프링 제거 / 박스: 테이프 제거. 영수증·택배전표·사진 불가"},
        {"category": "금속캔", "description": "내용물 비우기 → 라벨·플라스틱 뚜껑 제거 후 배출"},
        {"category": "유리병류", "description": "내용물 비우기 → 라벨·뚜껑 제거 후 배출. 소주·맥주 빈병은 소매점 보증금 환급 가능. 깨진 유리·도자기 불가"},
        {"category": "의류·신발·가방", "description": "투명 비닐봉투에 담아 배출. 이불·요 등은 종량제봉투로 배출"},
        {"category": "폐전지류", "description": "폐전지 수거함에 배출 (망간·알칼리·니켈·리튬·산화은·납축전지·공기아연전지)"},
    ]


# 시흥시 하드코딩 데이터 (크롤링 실패 시 폴백)
def get_siheung_hardcoded():
    return [
        {"category": "골판지류", "description": "비닐코팅·테이프·철핀·알루미늄박 제거 후 접어서 배출. 보냉 상자(알루미늄박 내장) 불가"},
        {"category": "종이팩", "description": "내용물 비우기 → 물로 헹구기 → 잘 펴서 말린 후 배출. 빨대·비닐 제거. (우유팩·두유팩·소주팩·쥬스팩 등)"},
        {"category": "신문지류", "description": "물기 없이 펴서 차곡차곡 묶어 배출. 비닐코팅 광고지 혼입 금지"},
        {"category": "종이컵", "description": "내용물 비우고 물로 헹군 후 압착하여 봉투에 넣거나 묶어서 배출"},
        {"category": "유리병류", "description": "내용물 비우기 → 라벨·뚜껑 제거 후 배출. 소주·맥주 빈병은 소매점 보증금 환급. 깨진 유리·도자기·내열유리 불가"},
        {"category": "금속캔류", "description": "내용물 비우기 → 라벨·플라스틱 뚜껑 제거 후 배출. 부탄가스·살충제 용기는 내용물 완전 제거 후 배출. 락카·페인트통 불가"},
        {"category": "투명 PET병", "description": "내용물 비우기 → 라벨 제거 → 압착 후 뚜껑 닫아 배출. 유색 PET는 플라스틱류로 배출"},
        {"category": "플라스틱류", "description": "내용물 비우기 → 물로 헹구기 → 라벨·이종 재질 제거 후 배출. 완구·칫솔·옷걸이·CD 등 불가"},
        {"category": "비닐류", "description": "내용물 비우기 → 이물질 제거 → 투명 봉투에 담아 배출. 랩필름·장판·고무장갑·섬유류 불가"},
        {"category": "스티로폼", "description": "내용물 비우기 → 라벨·테이프 제거 후 배출. 가전 구매 시 완충재는 가급적 구입처 반납. 음식물 오염·건축용 불가"},
        {"category": "의류·원단", "description": "민간 재활용사업자 폐의류 전용수거함에 배출. 재활용 어려운 품목은 종량제봉투로"},
        {"category": "폐전지류", "description": "제품에서 분리 후 주요 거점 건전지 수거함에 배출 (망간·알칼리·니켈·리튬·수은전지 등)"},
        {"category": "형광등", "description": "주요 거점 형광등 분리배출용기에 배출 (직관형·환형·안정기내장형 등)"},
        {"category": "소형가전", "description": "재활용 배출장소에 배출. 5종 이상 시 무상 방문수거 (1599-0903 / '폐가전무상배출' 검색)"},
        {"category": "폐식용유", "description": "다른 이물질 섞이지 않게 지정 수거용기(민간 재활용사업자 수거함)에 배출"},
    ]


# 도시별 분리수거 정보 반환 함수
def get_recycling_data(city: str):
    if city == 'ansan':
        return crawl_ansan_recycling()
    elif city == 'siheung':
        return crawl_siheung_recycling()
    else:
        return []