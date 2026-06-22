# -*- coding: utf-8 -*-
"""
dispersion.py — 대기 안정도 및 분산계수(σy, σz) : Martin scheme

가우스 확산식의 σy(횡방향 퍼짐), σz(연직방향 퍼짐)는 '대기 안정도 등급'과
'풍하거리 x'에 따라 달라진다. 화공팀 'a,b' 시트(Martin, 1976)를 따른다.

    σy = a · x^b        (x: km,  σ: m)
    σz = c · x^d

표준화: 울산 연평균 풍속 u=2.98 m/s 기준으로 Pasquill 안정도를
   - 낮(06~18시) → C 등급
   - 밤(18~06시) → E 등급
으로 단일화하여 적용한다. (화공팀 'u값' 시트 근거)
"""

# Martin 분산계수 상수 (a,b: 수평 / c,d: 수직). x는 km, σ는 m.
# 화공팀 'a,b' 시트에 명시된 낮=C / 밤=E 값을 기본으로 두고,
# 참고용으로 다른 등급(Table 3, x<1km)도 함께 둔다.
MARTIN = {
    "A": (213,  0.894, 440.8, 1.041),
    "B": (156,  0.894, 106.6, 1.149),
    "C": (104,  0.894, 61.0,  0.911),   # 낮 표준
    "D": (68,   0.894, 33.2,  0.725),
    "E": (50.5, 0.894, 22.8,  0.678),   # 밤 표준
    "F": (34,   0.894, 14.35, 0.74),
}


def stability_class(is_daytime: bool) -> str:
    """울산 표준 u=2.98 기준 안정도: 낮=C, 밤=E (화공팀 표준화)."""
    return "C" if is_daytime else "E"


def sigma_y_z(x_km: float, stab: str):
    """
    Martin 분산계수. x_km: 풍하거리(km). 반환 (σy, σz) [m].
        σy = a · x^b,  σz = c · x^d
    """
    x = max(x_km, 1e-3)  # 0/음수 방지 (약 1m)
    a, b, c, d = MARTIN.get(stab, MARTIN["C"])
    sigma_y = a * (x ** b)
    sigma_z = c * (x ** d)
    return sigma_y, sigma_z
