# ─── forworker_map.py ─────────────────────────────────────────
# 지도 기반 장소 검색 로직이에요.
# 카카오 로컬 API(장소 검색 + 카테고리 검색)를 사용해요.
#
# [카테고리]
# - halal     : '할랄', '무슬림', '이슬람음식', 'halal' 키워드 검색
# - tourist   : 카테고리 AT4 (관광명소)
# - restaurant: 카테고리 FD6 (음식점) — 일반 식당/베이커리 fallback
# - cafe      : 카테고리 CE7 (카페/베이커리)

import asyncio
import os

import httpx

KAKAO_CATEGORY_CODES = {
    'tourist': 'AT4',    # 관광명소
    'restaurant': 'FD6', # 음식점
    'cafe': 'CE7',       # 카페/베이커리
}

HALAL_KEYWORDS = ['할랄', '무슬림', '이슬람음식', 'halal']


async def _search_keyword(
    client: httpx.AsyncClient,
    key: str,
    query: str,
    lng: float,
    lat: float,
    radius: int,
) -> list:
    """단일 키워드로 카카오 로컬 키워드 검색"""
    try:
        res = await client.get(
            'https://dapi.kakao.com/v2/local/search/keyword.json',
            headers={'Authorization': f'KakaoAK {key}'},
            params={
                'query': query,
                'x': str(lng),
                'y': str(lat),
                'radius': str(radius),
                'sort': 'distance',
                'size': '15',
            },
            timeout=10,
        )
        data = res.json()
        return data.get('documents', [])
    except Exception as e:
        print(f"키워드 '{query}' 검색 오류: {e}")
        return []


async def _search_category(
    client: httpx.AsyncClient,
    key: str,
    category_group_code: str,
    lng: float,
    lat: float,
    radius: int,
) -> list:
    """카카오 로컬 카테고리 검색"""
    try:
        res = await client.get(
            'https://dapi.kakao.com/v2/local/search/category.json',
            headers={'Authorization': f'KakaoAK {key}'},
            params={
                'category_group_code': category_group_code,
                'x': str(lng),
                'y': str(lat),
                'radius': str(radius),
                'sort': 'distance',
                'size': '15',
            },
            timeout=10,
        )
        data = res.json()
        return data.get('documents', [])
    except Exception as e:
        print(f"카테고리 '{category_group_code}' 검색 오류: {e}")
        return []


def _normalize_places(docs: list, category: str) -> list:
    """카카오 응답을 공통 형식으로 변환"""
    places = []
    seen_urls: set[str] = set()
    for place in docs:
        url = place.get('place_url', '')
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        places.append({
            'name': place.get('place_name', ''),
            'address': place.get('road_address_name') or place.get('address_name', ''),
            'phone': place.get('phone', ''),
            'distance': int(place.get('distance', 0)),
            'lat': float(place.get('y', 0)),
            'lng': float(place.get('x', 0)),
            'url': url,
            'category': category,
        })
    return places


async def fetch_places_by_category(
    lat: float,
    lng: float,
    category: str = 'halal',
    radius: int = 5000,
) -> list:
    """
    카테고리별 장소 검색.
    category: 'halal' | 'tourist' | 'restaurant' | 'cafe'
    """
    kakao_api_key = os.getenv('KAKAO_API_KEY', '')

    if not kakao_api_key:
        print("KAKAO_API_KEY 환경변수가 없어요")
        return get_dummy(category)

    try:
        async with httpx.AsyncClient() as client:
            if category == 'halal':
                # 키워드 병렬 검색
                results = await asyncio.gather(*[
                    _search_keyword(client, kakao_api_key, kw, lng, lat, radius)
                    for kw in HALAL_KEYWORDS
                ])
                docs = [place for docs in results for place in docs]
            else:
                code = KAKAO_CATEGORY_CODES.get(category, 'FD6')
                docs = await _search_category(client, kakao_api_key, code, lng, lat, radius)

        places = _normalize_places(docs, category)
        places.sort(key=lambda r: r['distance'])
        print(f"[{category}] 검색 완료: {len(places)}곳 (반경 {radius}m)")
        return places

    except Exception as e:
        print(f"장소 검색 오류: {e}")
        return get_dummy(category)


# 기존 API 호환성 유지
async def fetch_halal_restaurants(lat: float, lng: float, radius: int = 5000):
    return await fetch_places_by_category(lat, lng, 'halal', radius)


def get_dummy(category: str = 'halal') -> list:
    """API 오류 시 반환하는 더미 데이터"""
    dummy_map = {
        'halal': [{'name': '할랄 식당 (샘플)', 'address': '경기도 안산시 단원구', 'phone': '', 'distance': 500, 'lat': 37.3219, 'lng': 126.8308, 'url': '', 'category': 'halal'}],
        'tourist': [{'name': '안산 관광명소 (샘플)', 'address': '경기도 안산시', 'phone': '', 'distance': 800, 'lat': 37.3210, 'lng': 126.8310, 'url': '', 'category': 'tourist'}],
        'restaurant': [{'name': '식당 (샘플)', 'address': '경기도 안산시 단원구', 'phone': '', 'distance': 300, 'lat': 37.3225, 'lng': 126.8300, 'url': '', 'category': 'restaurant'}],
        'cafe': [{'name': '카페/베이커리 (샘플)', 'address': '경기도 안산시 단원구', 'phone': '', 'distance': 400, 'lat': 37.3230, 'lng': 126.8305, 'url': '', 'category': 'cafe'}],
    }
    return dummy_map.get(category, dummy_map['halal'])


# 기존 호환성
def get_halal_dummy():
    return get_dummy('halal')
