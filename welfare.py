# 복지 정책 관련 로직이에요.
# data.go.kr 공공API에서 시흥·안산시 복지정책을 가져와요.
# servCtgry 필드가 API에서 제공되지 않아 제목+설명 키워드로 카테고리를 자동 분류해요.

import httpx
import os
from urllib.parse import unquote
import xml.etree.ElementTree as ET

# 키워드 기반 카테고리 자동 분류
# 제목(title) + 설명(description) 텍스트에서 키워드 매칭
CATEGORY_KEYWORDS = {
    '외국인지원': ['외국인', '이민', '다문화', '결혼이민', '외국인주민', '이주민', '이주노동'],
    '의료·건강': ['의료', '병원', '예방접종', '치료', '재활', '건강', '달팽이관', '인플루엔자'],
    '교육': ['교육', '학교', '교복', '학습', '장학', '어학', '한국어', '한국사회'],
    '주거': ['주거', '집수리', '전세', '임대', '도배', '단열', '주택'],
    '교통': ['교통', '버스', '지하철', '이동', '운송', '교통비'],
    '출산·육아': ['출산', '임신', '산후', '출생', '영유아', '산모', '출생축하'],
    '장애인지원': ['장애', '재활', '보장구', '장애인', '장애학생'],
    '고용·생계': ['고용', '취업', '일자리', '노동', '생계', '수당', '급여', '임금'],
    '노인': ['노인', '어르신', '경로', '효도', '노년'],
}

def classify_category(title: str, description: str) -> str:
    """제목 + 설명 텍스트 기반으로 카테고리 자동 분류"""
    text = title + description
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return category
    return '기타복지'

def is_foreigner_related(title: str, description: str) -> bool:
    """외국인 관련 정책 여부 확인"""
    text = title + description
    keywords = ['외국인', '이민', '다문화', '결혼이민', '외국인주민', '이주민', '이주노동자']
    return any(k in text for k in keywords)


async def fetch_welfare(city: str):
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
                    'numOfRows': '100',
                    'sggNm': city_name,
                },
                timeout=15
            )

        root = ET.fromstring(res.text)
        items = []

        for item in root.findall('.//servList'):
            sgg = item.findtext('sggNm') or ''
            if city_name not in sgg:
                continue

            title = item.findtext('servNm') or ''
            description = item.findtext('servDgst') or ''

            items.append({
                'title': title,
                'description': description,
                'target': item.findtext('lifeNmArray') or '',
                # API에서 카테고리 미제공 → 키워드 기반 자동 분류
                'category': classify_category(title, description),
                # 외국인 관련 여부 플래그
                'isForeigner': is_foreigner_related(title, description),
                'link': item.findtext('servDtlLink') or '',
            })

        if items:
            return items
        else:
            print(f"{city_name} 데이터 없음, 더미 반환")
            return get_welfare_dummy()

    except Exception as e:
        print(f"복지 API 오류: {e}")
        return get_welfare_dummy()


def get_welfare_dummy():
    return [
        {'title': '외국인 근로자 의료비 지원', 'description': '건강보험 미가입 외국인 근로자 의료비 지원', 'target': '외국인', 'category': '외국인지원', 'isForeigner': True, 'link': ''},
        {'title': '이주민 한국어 교육 지원', 'description': '무료 한국어 교육 프로그램 운영', 'target': '외국인', 'category': '외국인지원', 'isForeigner': True, 'link': ''},
        {'title': '외국인 근로자 생활안정자금 대출', 'description': '저금리 생활안정자금 대출 지원', 'target': '외국인', 'category': '고용·생계', 'isForeigner': True, 'link': ''},
    ]