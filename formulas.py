# -*- coding: utf-8 -*-
"""
formulas.py — 화공 수식 엔진 (소음 + 악취)

[소음] 거리 역자승 감쇄 법칙 + 다중 음원 로그 합산
[악취] 2차원 가우스 확산 모델 (z=0 가정) + Martin 분산계수

핵심 3업종(C20/C22/C25)만 배출원으로 본다. 그 외 업종(창고·임대 등)은 배출원이
아니므로 계산에서 제외한다. (화공팀 시트 기준)

Q(악취 배출량) = 업종별 잠재력 가중치 × (해당 공장 부지면적 / 산단 내 최대 부지면적)
  - 부지면적 데이터가 없으면 size_ratio=1.0 으로 두며, 현재는 고용인원을
    크기 대용치로 사용한다(부지면적 API 연동 시 교체).
"""

import math

from config import (NOISE_REFERENCE_DISTANCE_M, DEFAULT_STACK_HEIGHT_M,
                    get_industry_weight, ODOR_CALIBRATION, ODOR_WIND_DIRS)
from geo import decompose_wind
from dispersion import sigma_y_z


# ===========================================================================
# 1. 소음 : 거리 역자승 감쇄 법칙   SPL2 = SPL1 - 20*log10(r2/r1)
# ===========================================================================
def noise_attenuation_db(spl1_db, r2_m, r1_m=NOISE_REFERENCE_DISTANCE_M):
    """단일 공장 소음이 거리 r2(m)에서 감쇄된 dB."""
    r2 = max(r2_m, r1_m)   # 기준거리(1m)보다 가까울 수 없음
    return spl1_db - 20.0 * math.log10(r2 / r1_m)


def combine_noise_db(spl_list):
    """다중 음원 로그 합산. SPL_total = 10*log10( Σ 10^(SPLi/10) )."""
    vals = [s for s in spl_list if s is not None]
    if not vals:
        return 0.0
    total = sum(10 ** (s / 10.0) for s in vals)
    return 10.0 * math.log10(total) if total > 0 else 0.0


def total_noise_at_apartment(apt_lat, apt_lon, factories):
    """아파트 누적 소음(dB). 핵심 3업종만 음원으로 본다."""
    spls = []
    for f in factories:
        w = get_industry_weight(f.get("ksic_code"), f.get("industry_name"))
        if w is None:        # 배출원 아님(창고·임대 등) → 제외
            continue
        r2_m = f["distance_km"] * 1000.0
        spls.append(noise_attenuation_db(w["noise_db"], r2_m))
    return combine_noise_db(spls)


# ===========================================================================
# 2. 악취 : 2차원 가우스 확산 모델 (z=0)
#    C(x,y) = Q / (pi*u*σy*σz) * exp(-y^2/2σy^2) * exp(-H^2/2σz^2)
# ===========================================================================
def gaussian_concentration(Q, u, x_km, y_m, stab, H=DEFAULT_STACK_HEIGHT_M):
    """
    한 공장에서 (x, y) 지점의 악취 농도(상대 OU).
    x_km : 풍하거리(km). 0 이하(upwind)면 도달 안 함 → 0.
    y_m  : 횡풍 편차거리(m).
    """
    if x_km <= 0:
        return 0.0
    u = max(u, 0.3)
    sigma_y, sigma_z = sigma_y_z(x_km, stab)   # Martin: x는 km, σ는 m
    if sigma_y <= 0 or sigma_z <= 0:
        return 0.0
    coef = Q / (math.pi * u * sigma_y * sigma_z)
    term_y = math.exp(-(y_m ** 2) / (2 * sigma_y ** 2))
    term_z = math.exp(-(H ** 2) / (2 * sigma_z ** 2))
    return coef * term_y * term_z


def _size_ratio(f, max_size):
    """공장 크기 대용치(고용인원) 기반 면적비. 데이터 없으면 1.0."""
    try:
        size = float(f.get("employees") or 0)
    except (TypeError, ValueError):
        size = 0.0
    if max_size and max_size > 0 and size > 0:
        return size / max_size
    return 1.0


def total_odor_at_apartment(apt_lat, apt_lon, factories,
                            wind_speed, wind_from_deg, stab,
                            H=DEFAULT_STACK_HEIGHT_M, n_dirs=ODOR_WIND_DIRS):
    """
    아파트 누적 악취 농도(OU). 핵심 3업종만, Q는 면적(크기)비로 가중.

    [방향성] 단일 풍향 대신 n_dirs 방위(기본 8방위) '바람장미 평균'을 사용한다.
      → 주거 입지 추천은 그날의 풍향이 아니라 장기(연평균) 노출을 봐야 하므로,
        모든 방위에서 부는 경우를 평균해 인근 배출원이 빠짐없이 반영되게 한다.
    [스케일] 마지막에 ODOR_CALIBRATION(상대→OU)을 곱해 등급밴드(3~30 OU)에 맞춘다.
    """
    # 분모: 핵심 배출원들의 최대 크기(고용인원). 면적비 가중용.
    sizes = []
    for f in factories:
        if get_industry_weight(f.get("ksic_code"), f.get("industry_name")):
            try:
                sizes.append(float(f.get("employees") or 0))
            except (TypeError, ValueError):
                pass
    max_size = max(sizes) if sizes else 0

    dirs = [360.0 * k / n_dirs for k in range(n_dirs)]
    total = 0.0
    for f in factories:
        w = get_industry_weight(f.get("ksic_code"), f.get("industry_name"))
        if w is None:
            continue
        Q = w["odor_q"] * _size_ratio(f, max_size)
        acc = 0.0
        for wd in dirs:                      # 바람장미: 모든 방위 평균
            x_m, y_m = decompose_wind(f["lat"], f["lon"],
                                      apt_lat, apt_lon, wd)
            acc += gaussian_concentration(Q, wind_speed, x_m / 1000.0,
                                          y_m, stab, H)
        total += acc / n_dirs
    return total * ODOR_CALIBRATION


def count_core_sources(factories):
    """핵심 배출원(3업종) 개수."""
    return sum(1 for f in factories
               if get_industry_weight(f.get("ksic_code"),
                                      f.get("industry_name")))
