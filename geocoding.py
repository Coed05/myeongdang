# -*- coding: utf-8 -*-
"""
geocoding.py — 주소 → 위도/경도 변환 (국토교통부 브이월드 API)

[함수 1] 역할분담 문서의 'get_apt_coordinates' 에 대응.
사용자가 텍스트 주소를 입력하면 브이월드 지오코딩 API로 GPS 좌표를 얻습니다.
"""

import os
import re
import requests
from config import VWORLD_API_KEY

VWORLD_URL = "https://api.vworld.kr/req/address"

# 브이월드 키에 등록한 도메인. 서버에서 호출할 때 이 Referer를 함께 보내야
# 도메인 제한을 통과한다. (배포 주소에 맞게 Secrets의 VWORLD_REFERER로 변경 가능)
VWORLD_REFERER = os.getenv("VWORLD_REFERER", "https://myeongdang.streamlit.app")
_VWORLD_HEADERS = {"Referer": VWORLD_REFERER}


def clean_address(addr: str) -> str:
    """
    지오코딩 정확도를 위해 주소 뒤 괄호 부가정보를 제거.
    예) '울산광역시 북구 염포로 700 (양정동, (주)현대자동차)'
        -> '울산광역시 북구 염포로 700'
    """
    if not addr:
        return ""
    s = str(addr)
    # 첫 번째 여는 괄호 이후를 잘라냄(중첩 괄호도 함께 제거됨)
    idx = s.find("(")
    if idx != -1:
        s = s[:idx]
    return re.sub(r"\s+", " ", s).strip()


def geocode(address: str, api_key: str = None, address_type: str = "ROAD"):
    """
    주소를 (위도, 경도)로 변환.

    매개변수
    --------
    address : 검색할 주소 문자열 (예: "울산광역시 남구 야음동 ...")
    address_type : "ROAD"(도로명) 또는 "PARCEL"(지번). 실패 시 자동 폴백.

    반환
    ----
    (lat, lon) 튜플. 실패하면 (None, None).
    """
    key = api_key or VWORLD_API_KEY
    if not key:
        raise RuntimeError("VWORLD_API_KEY 가 설정되지 않았습니다 (.env 확인).")

    params = {
        "service": "address",
        "request": "getcoord",
        "version": "2.0",
        "crs": "EPSG:4326",       # 위경도 좌표계
        "address": address,
        "type": address_type,
        "format": "json",
        "key": key,
    }

    data = None
    for attempt in range(2):  # 타임아웃 시 1회 재시도
        try:
            resp = requests.get(VWORLD_URL, params=params,
                                headers=_VWORLD_HEADERS, timeout=15)
            data = resp.json()
            break
        except (requests.RequestException, ValueError) as e:
            if attempt == 0:
                continue
            print(f"[geocode] 요청 실패: {e}")
            return None, None

    status = data.get("response", {}).get("status")
    if status == "OK":
        point = data["response"]["result"]["point"]
        lon = float(point["x"])   # 브이월드: x=경도, y=위도
        lat = float(point["y"])
        return lat, lon

    # 도로명으로 실패하면 지번으로 한 번 더 시도
    if address_type == "ROAD":
        return geocode(address, key, address_type="PARCEL")

    # 브이월드가 (배포 서버에서) 막히면 키 불필요한 OSM Nominatim 으로 폴백
    lat, lon = _nominatim(address)
    if lat is not None:
        return lat, lon

    print(f"[geocode] 좌표를 찾지 못했습니다 (status={status}): {address}")
    return None, None


def _nominatim(address: str):
    """OpenStreetMap Nominatim 지오코딩 (키 불필요, 서버 어디서든 동작)."""
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1,
                    "countrycodes": "kr", "accept-language": "ko"},
            headers={"User-Agent": "ansim-myeongdang/1.0"}, timeout=15)
        arr = resp.json()
        if arr:
            return float(arr[0]["lat"]), float(arr[0]["lon"])
    except Exception as e:
        print(f"[nominatim] 실패: {e}")
    return None, None


VWORLD_SEARCH_URL = "https://api.vworld.kr/req/search"


def search_address(query: str, api_key: str = None, size: int = 10) -> list:
    """
    브이월드 주소 검색. 부분 검색어로 후보 주소+좌표 목록을 반환.
    반환: [{'label': 표시주소, 'lat': float, 'lon': float}, ...]
    """
    key = api_key or VWORLD_API_KEY
    if not key or not query.strip():
        return []

    results = []
    # 1) 브이월드 '검색 API' (권한 있으면 여러 후보 반환)
    for cat in ("road", "parcel"):   # 도로명 먼저, 없으면 지번
        params = {
            "service": "search", "request": "search", "version": "2.0",
            "crs": "EPSG:4326", "size": size, "page": 1,
            "query": query, "type": "address", "category": cat,
            "format": "json", "key": key,
        }
        try:
            resp = requests.get(VWORLD_SEARCH_URL, params=params,
                                headers=_VWORLD_HEADERS, timeout=15)
            data = resp.json()
        except (requests.RequestException, ValueError):
            continue
        res = data.get("response", {})
        if res.get("status") != "OK":
            continue
        for it in res.get("result", {}).get("items", []):
            addr = it.get("address", {})
            label = addr.get("road") or addr.get("parcel") or it.get("title", "")
            pt = it.get("point", {})
            try:
                results.append({"label": label,
                                "lat": float(pt["y"]), "lon": float(pt["x"])})
            except (KeyError, TypeError, ValueError):
                continue
        if results:
            break

    # 2) 폴백: 검색 API가 막혔거나 결과가 없으면 '지오코더'로 직접 변환
    #    (지오코더 API만 켜져 있어도 동작하도록)
    if not results:
        lat, lon = geocode(query)
        if lat is not None:
            results.append({"label": query, "lat": lat, "lon": lon})
    return results
