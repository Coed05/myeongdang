# -*- coding: utf-8 -*-
"""
pipeline.py — 전체 파이프라인 오케스트레이션

흐름:
  주소 입력 → (지오코딩) 좌표 → (산단공) 주변 공장 → 5km 필터
            → (기상청) 풍향·풍속 → 소음/악취 수식 → 종합 안심 등급

run_assessment() 하나로 '종합 안심 주거 리포트' dict 를 반환합니다.
프론트엔드(웹)는 이 dict 를 받아 인포그래픽으로 출력하면 됩니다.
"""

from datetime import datetime

import pandas as pd

from config import (SEARCH_RADIUS_KM, DEFAULT_STACK_HEIGHT_M,
                    WIND_SPEED_DAY, WIND_SPEED_NIGHT)
from geocoding import geocode
from factories import filter_nearby_factories
from weather import get_wind_by_latlon
from dispersion import stability_class
from formulas import (total_noise_at_apartment, total_odor_at_apartment,
                      count_core_sources)
from grading import evaluate


def run_assessment(address: str,
                   factory_df: pd.DataFrame,
                   apt_coords=None,
                   wind=None,
                   is_daytime: bool = True,
                   radius_km: float = SEARCH_RADIUS_KM,
                   stack_height_m: float = DEFAULT_STACK_HEIGHT_M,
                   use_live_weather: bool = False,
                   noise_weight: float = None,
                   odor_weight: float = None) -> dict:
    """
    매개변수
    --------
    address      : 사용자가 입력한 아파트 주소
    factory_df   : 공장 목록 DataFrame (회사명/업종코드/위도/경도)
    apt_coords   : (lat, lon)을 직접 줄 경우(지오코딩 건너뜀). None이면 API 사용.
    wind         : {'wind_speed','wind_from_deg'} 직접 지정. None이면 기본/실시간.
    is_daytime   : 주간 기준 평가 여부
    use_live_weather : True면 기상청 실시간 풍향·풍속 호출

    반환
    ----
    종합 안심 주거 리포트 dict
    """
    # 1) 좌표
    if apt_coords:
        apt_lat, apt_lon = apt_coords
    else:
        apt_lat, apt_lon = geocode(address)
        if apt_lat is None:
            return {"error": f"주소 좌표 변환 실패: {address}"}

    # 2) 주변 공장 5km 필터
    nearby = filter_nearby_factories(apt_lat, apt_lon, factory_df, radius_km)
    factories = nearby.to_dict("records") if not nearby.empty else []

    # 3) 풍향·풍속 (기본값: 울산 표준 풍속 낮 3.24 / 밤 2.61)
    if wind is None:
        if use_live_weather:
            wind = get_wind_by_latlon(apt_lat, apt_lon)
        else:
            u = WIND_SPEED_DAY if is_daytime else WIND_SPEED_NIGHT
            wind = {"wind_speed": u, "wind_from_deg": 225.0}
    # 안정도: 표준화(낮=C / 밤=E)
    stab = stability_class(is_daytime)

    # 4) 수식 연산
    noise_db = total_noise_at_apartment(apt_lat, apt_lon, factories)
    odor_ou = total_odor_at_apartment(
        apt_lat, apt_lon, factories,
        wind["wind_speed"], wind["wind_from_deg"], stab, stack_height_m)

    # 5) 등급화 (가중치 미지정 시 config 기본값 사용)
    from config import NOISE_WEIGHT, ODOR_WEIGHT
    w1 = NOISE_WEIGHT if noise_weight is None else noise_weight
    w2 = ODOR_WEIGHT if odor_weight is None else odor_weight
    result = evaluate(noise_db, odor_ou, is_daytime, w1, w2)

    return {
        "address": address,
        "coordinates": {"lat": round(apt_lat, 6), "lon": round(apt_lon, 6)},
        "wind": wind,
        "stability_class": stab,
        "is_daytime": is_daytime,
        "nearby_factory_count": len(factories),
        "core_source_count": count_core_sources(factories),
        "nearby_factories": factories,
        **result,
    }


def print_report(report: dict):
    """터미널(콘솔) 검증용 리포트 출력 — 역할분담 문서의 '2일차 검증 화면'."""
    if "error" in report:
        print("오류:", report["error"])
        return
    print("=" * 56)
    print(f" 종합 안심 주거 리포트")
    print("=" * 56)
    print(f" 입력 주소   : {report['address']}")
    c = report["coordinates"]
    print(f" 변환 좌표   : ({c['lat']}, {c['lon']})")
    w = report["wind"]
    print(f" 기상 조건   : 풍속 {w['wind_speed']} m/s, "
          f"풍향(불어오는) {w['wind_from_deg']}°, 안정도 {report['stability_class']}")
    print(f" 주야 구분   : {'주간' if report['is_daytime'] else '야간'}")
    print(f" 5km 내 공장 : {report['nearby_factory_count']} 개")
    for f in report["nearby_factories"]:
        print(f"    - {f['factory_name']} "
              f"(업종 {f['ksic_code']} / 거리 {f['distance_km']}km)")
    print("-" * 56)
    print(f" 누적 소음   : {report['noise_db']} dB  → 소음점수 {report['noise_score']}")
    print(f" 누적 악취   : {report['odor_ou']} OU  → 악취점수 {report['odor_score']}")
    print(f" 종합 점수   : {report['composite_score']} / 100")
    print(f" ★ 안심 등급 : {report['grade']}")
    print("=" * 56)
