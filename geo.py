# -*- coding: utf-8 -*-
"""
geo.py — 좌표·거리 계산 유틸리티

- haversine_km : 둥근 지구를 반영한 두 좌표 사이의 직선거리(km)
- offset_meters : 한 점에서 다른 점까지의 동/북 방향 변위(m)
- decompose_wind : 공장→아파트 변위를 '바람축(x)'과 '바람직각(y)'으로 분해

가우스 확산식은 바람이 부는 방향을 기준으로 x(풍하거리), y(횡풍거리)를
나눠 계산해야 하므로 단순 직선거리 외에 방향 분해가 필요합니다.
"""

import math

EARTH_RADIUS_KM = 6371.0088
# 위도 1도 ≈ 110540 m, 경도 1도 ≈ 111320*cos(위도) m (구면 근사)
M_PER_DEG_LAT = 110540.0
M_PER_DEG_LON = 111320.0


def haversine_km(lat1, lon1, lat2, lon2):
    """하버사인 공식. 두 (위도,경도) 사이 대권거리(km)."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2)
    c = 2 * math.asin(min(1.0, math.sqrt(a)))
    return EARTH_RADIUS_KM * c


def offset_meters(lat_from, lon_from, lat_to, lon_to):
    """from→to 의 (동쪽 변위, 북쪽 변위)를 미터로 반환 (등거사각 근사)."""
    lat_mean = math.radians((lat_from + lat_to) / 2.0)
    dx_east = (lon_to - lon_from) * M_PER_DEG_LON * math.cos(lat_mean)
    dy_north = (lat_to - lat_from) * M_PER_DEG_LAT
    return dx_east, dy_north


def decompose_wind(factory_lat, factory_lon, apt_lat, apt_lon, wind_from_deg):
    """
    공장→아파트 변위를 바람 좌표계로 분해.

    매개변수
    --------
    wind_from_deg : 바람이 '불어오는' 방향(기상학 관례, 북=0, 시계방향).
                    예) 북풍 = 0도(북에서 남으로 분다).

    반환
    ----
    x : 풍하(downwind) 거리(m). 아파트가 바람을 받는 쪽이면 +.
        음수면 아파트가 바람 위쪽(upwind)이라 연기가 거의 안 옴.
    y : 바람축에서 옆으로 벗어난 횡풍(crosswind) 거리(m), 절댓값.
    """
    dx_east, dy_north = offset_meters(factory_lat, factory_lon, apt_lat, apt_lon)

    # 바람이 '가는' 방향(풍하) 단위벡터. from의 정반대.
    # from 방향 단위벡터 = (sinθ, cosθ) in (east, north) → going = 음의 부호
    theta = math.radians(wind_from_deg)
    g_east = -math.sin(theta)
    g_north = -math.cos(theta)

    # x = 변위를 풍하 단위벡터에 정사영
    x = dx_east * g_east + dy_north * g_north
    # y = 풍하축에 수직인 성분의 크기 (2D 외적 절댓값)
    y = abs(dx_east * g_north - dy_north * g_east)
    return x, y
