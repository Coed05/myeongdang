# -*- coding: utf-8 -*-
"""
weather.py — 기상청 실시간 풍향·풍속 수집

가우스 확산식에 필요한 u(풍속, m/s)와 풍향(불어오는 방향, deg)을 제공합니다.
실제 서비스에서는 기상청 초단기실황(getUltraSrtNcst) API를 사용합니다.
키가 없거나 호출이 실패하면 기본값(약풍/남서풍)으로 폴백합니다.
"""

import math
from datetime import datetime, timedelta

import requests
from config import KMA_API_KEY

KMA_URL = ("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/"
           "getUltraSrtNcst")

# 폴백 기본값
DEFAULT_WIND = {"wind_speed": 2.0, "wind_from_deg": 225.0}  # 남서풍 2 m/s


def latest_ncst_base(now: datetime = None):
    """
    초단기실황(getUltraSrtNcst) 호출용 base_date, base_time 계산.
    실황은 매시 정각 생성되어 약 40분 뒤 제공되므로, 분<45면 직전 시각 사용.
    """
    now = now or datetime.now()
    if now.minute < 45:
        now = now - timedelta(hours=1)
    return now.strftime("%Y%m%d"), now.strftime("%H00")


def get_wind_by_latlon(lat: float, lon: float, api_key: str = None) -> dict:
    """위경도로 바로 실시간 풍향·풍속 조회 (격자변환+기준시각 자동)."""
    nx, ny = latlon_to_grid(lat, lon)
    base_date, base_time = latest_ncst_base()
    return get_wind(nx, ny, base_date, base_time, api_key)


def diagnose(lat: float = 35.528, lon: float = 129.330,
             api_key: str = None) -> None:
    """기상청 서버 원문을 그대로 출력 (키는 마스킹)."""
    key = api_key or KMA_API_KEY
    if not key:
        print("KMA_API_KEY 가 비어 있습니다 (.env 확인).")
        return
    nx, ny = latlon_to_grid(lat, lon)
    base_date, base_time = latest_ncst_base()
    params = {
        "serviceKey": key, "pageNo": 1, "numOfRows": 100, "dataType": "JSON",
        "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny,
    }
    print("요청 URL :", KMA_URL)
    print("요청 파라미터 :", {**params, "serviceKey": key[:4] + "..."})
    try:
        resp = requests.get(KMA_URL, params=params, timeout=15)
    except Exception as e:
        print("연결 실패:", e)
        return
    print("HTTP 상태 :", resp.status_code)
    print("응답 본문(앞 800자) :")
    print(resp.text[:800])


def get_wind(nx: int, ny: int, base_date: str, base_time: str,
             api_key: str = None) -> dict:
    """
    기상청 격자좌표(nx, ny) 지점의 풍향·풍속을 반환.

    반환: {"wind_speed": m/s, "wind_from_deg": deg(불어오는 방향)}
    """
    key = api_key or KMA_API_KEY
    if not key:
        return dict(DEFAULT_WIND)

    params = {
        "serviceKey": key, "pageNo": 1, "numOfRows": 100, "dataType": "JSON",
        "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny,
    }
    try:
        resp = requests.get(KMA_URL, params=params, timeout=10)
        items = (resp.json()["response"]["body"]["items"]["item"])
    except Exception as e:
        print(f"[weather] 기상청 호출 실패, 기본값 사용: {e}")
        return dict(DEFAULT_WIND)

    cat = {it["category"]: float(it["obsrValue"]) for it in items}
    # UUU=동서바람성분, VVV=남북바람성분, WSD=풍속, VEC=풍향
    if "WSD" in cat and "VEC" in cat:
        return {"wind_speed": max(cat["WSD"], 0.3),
                "wind_from_deg": cat["VEC"]}
    if "UUU" in cat and "VVV" in cat:
        u, v = cat["UUU"], cat["VVV"]
        speed = math.hypot(u, v)
        # 바람이 불어오는 방향(meteorological)
        from_deg = (270 - math.degrees(math.atan2(v, u))) % 360
        return {"wind_speed": max(speed, 0.3), "wind_from_deg": from_deg}
    return dict(DEFAULT_WIND)


def latlon_to_grid(lat: float, lon: float):
    """위경도 → 기상청 격자좌표(nx, ny) (LCC DFS 변환)."""
    RE, GRID = 6371.00877, 5.0
    SLAT1, SLAT2, OLON, OLAT, XO, YO = 30.0, 60.0, 126.0, 38.0, 43, 136
    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1, slat2 = SLAT1 * DEGRAD, SLAT2 * DEGRAD
    olon, olat = OLON * DEGRAD, OLAT * DEGRAD
    sn = (math.log(math.cos(slat1) / math.cos(slat2)) /
          math.log(math.tan(math.pi*0.25 + slat2*0.5) /
                   math.tan(math.pi*0.25 + slat1*0.5)))
    sf = (math.tan(math.pi*0.25 + slat1*0.5) ** sn) * math.cos(slat1) / sn
    ro = re * sf / (math.tan(math.pi*0.25 + olat*0.5) ** sn)
    ra = re * sf / (math.tan(math.pi*0.25 + lat*DEGRAD*0.5) ** sn)
    theta = lon * DEGRAD - olon
    theta = (theta + math.pi) % (2*math.pi) - math.pi
    theta *= sn
    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny
