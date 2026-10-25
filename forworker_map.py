# ─── forworker_map.py ─────────────────────────────────────────
# 지도 기반 장소 검색 로직이에요.
# 카카오 로컬 API(장소 검색)를 사용해서 현재 위치 주변 할랄 식당을 가져와요.
# 추후 관광지, 병원 등 다른 장소 유형도 이 파일에서 확장할 수 있어요.
#
# [사용 API]
# - 카카오 로컬 키워드 검색: https://dapi.kakao.com/v2/local/search/keyword.json
# - 인증: REST API 키 (헤더 Authorization: KakaoAK {key})
# - Railway 환경변수: KAKAO_API_KEY
#
# [검색 방식]
# - 키워드 '할랄'로 검색
# - 현재 위치(위도/경도) 기준 반경 내 결과만 반환
# - 거리순(distance) 정렬 → 가장 가까운 식당부터 표시
#
# [반환 데이터]
# - name     : 식당 이름
# - address  : 도로명 주소 (없으면 지번 주소)
# - phone    : 전화번호
# - distance : 현재 위치에서의 거리 (미터 단위)
# - lat      : 식당 위도 (지도 핀 표시에 사용)
# - lng      : 식당 경도 (지도 핀 표시에 사용)
# - url      : 카카오맵 상세 페이지 링크

import httpx
import os


async def fetch_halal_restaurants(lat: float, lng: float, radius: int = 3000):
    """
    위도(lat), 경도(lng) 기준으로 반경 radius(m) 내 할랄 식당을 검색해요.
    카카오 로컬 API 호출 → 결과 파싱 → 정제된 리스트 반환.
    API 오류 발생 시 더미 데이터를 반환해서 앱이 크래시되지 않아요.
    """
    kakao_api_key = os.getenv('KAKAO_API_KEY', '')

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                'https://dapi.kakao.com/v2/local/search/keyword.json',
                headers={
                    # 카카오 REST API 인증 헤더
                    'Authorization': f'KakaoAK {kakao_api_key}'
                },
                params={
                    'query': '할랄',          # 검색 키워드
                    'x': str(lng),            # 경도 (카카오 API는 x=경도, y=위도)
                    'y': str(lat),            # 위도
                    'radius': str(radius),    # 검색 반경 (미터)
                    'sort': 'distance',       # 거리순 정렬
                    'size': '15',             # 최대 반환 개수
                },
                timeout=10
            )

        data = res.json()
        places = data.get('documents', [])  # 검색 결과 목록

        # 카카오 API 응답 필드를 앱에서 사용할 형태로 정제
        restaurants = []
        for place in places:
            restaurants.append({
                'name': place.get('place_name', ''),
                # 도로명 주소 우선, 없으면 지번 주소 사용
                'address': place.get('road_address_name') or place.get('address_name', ''),
                'phone': place.get('phone', ''),
                'distance': int(place.get('distance', 0)),  # 미터 단위 거리
                'lat': float(place.get('y', 0)),            # 위도 (카카오 응답에서 y)
                'lng': float(place.get('x', 0)),            # 경도 (카카오 응답에서 x)
                'url': place.get('place_url', ''),          # 카카오맵 상세 링크
            })

        return restaurants

    except Exception as e:
        print(f"할랄 식당 검색 오류: {e}")
        # API 오류 시 더미 데이터 반환 (앱 크래시 방지)
        return get_halal_dummy()


def get_halal_dummy():
    """API 오류 또는 결과 없을 때 반환하는 더미 데이터"""
    return [
        {
            'name': '할랄 식당 (샘플)',
            'address': '경기도 안산시 단원구',
            'phone': '',
            'distance': 500,
            'lat': 37.3219,
            'lng': 126.8308,
            'url': '',
        },
    ]
