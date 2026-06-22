# -*- coding: utf-8 -*-
"""
complexes.py — 전국 주요 산업단지 위치 레지스트리 + 인근 단지 자동 탐지

공장 조회 API(getFctryListInIrsttService_v2)는 '산업단지명(irsttNm)'으로만
조회되므로, 아파트 주변에 어떤 단지가 있는지 모를 때를 대비해
주요 국가/일반 산업단지의 대표 좌표를 등록해 둡니다.

아파트 좌표가 주어지면 이 레지스트리에서 일정 거리 내 단지를 자동 선택합니다.

주의: name 문자열은 API의 irsttNm 과 정확히 일치해야 공장이 조회됩니다.
'울산미포국가산업단지'는 실제 조회 확인됨. 그 외는 대표 좌표이며,
조회가 비면 graceful 하게 건너뛰도록 설계되어 있습니다. (이름은 통계 API의
irsttNm 목록으로 검증·보강 가능)
"""

from geo import haversine_km

# 대표 좌표(중심부 근사). 산업 밀집 지역 위주.
INDUSTRIAL_COMPLEXES = [
    {"name": "울산미포국가산업단지", "lat": 35.501, "lon": 129.389, "region": "울산"},
    {"name": "온산국가산업단지",     "lat": 35.432, "lon": 129.341, "region": "울산"},
    {"name": "여수국가산업단지",     "lat": 34.861, "lon": 127.701, "region": "전남 여수"},
    {"name": "대산국가산업단지",     "lat": 36.991, "lon": 126.361, "region": "충남 서산"},
    {"name": "포항철강산업단지",     "lat": 36.013, "lon": 129.398, "region": "경북 포항"},
    {"name": "광양국가산업단지",     "lat": 34.921, "lon": 127.701, "region": "전남 광양"},
    {"name": "구미국가산업단지",     "lat": 36.118, "lon": 128.392, "region": "경북 구미"},
    {"name": "창원국가산업단지",     "lat": 35.224, "lon": 128.631, "region": "경남 창원"},
    {"name": "반월국가산업단지",     "lat": 37.312, "lon": 126.792, "region": "경기 안산"},
    {"name": "시화국가산업단지",     "lat": 37.342, "lon": 126.722, "region": "경기 시흥"},
    {"name": "남동국가산업단지",     "lat": 37.411, "lon": 126.701, "region": "인천"},
    {"name": "군산국가산업단지",     "lat": 35.971, "lon": 126.621, "region": "전북 군산"},
    {"name": "아산국가산업단지",     "lat": 36.881, "lon": 126.621, "region": "충남 아산"},
]


def nearby_complexes(apt_lat: float, apt_lon: float,
                     max_km: float = 15.0) -> list:
    """
    아파트 좌표에서 max_km 이내의 산업단지를 거리순으로 반환.
    반환: [{'name','lat','lon','region','dist_km'}, ...]
    """
    out = []
    for c in INDUSTRIAL_COMPLEXES:
        d = haversine_km(apt_lat, apt_lon, c["lat"], c["lon"])
        if d <= max_km:
            out.append({**c, "dist_km": round(d, 2)})
    out.sort(key=lambda x: x["dist_km"])
    return out
