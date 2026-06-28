# -*- coding: utf-8 -*-
"""
dispersion.py — 대기 안정도 및 분산계수(σy, σz) : Martin (1976) scheme

가우스 확산식의 σy(횡방향 퍼짐), σz(연직방향 퍼짐)는 '대기 안정도 등급'과
'풍하거리 x'에 따라 달라진다. Martin's scheme(Table 3)을 따른다.

    σy = a · x^b            (x: km, σ: m)
    σz = c · x^d + f        (c,d,f 는 x<1km / x≥1km 구간별로 다름)

대기 안정도 등급은 고정값이 아니라 '풍속(u)'과 '하늘상태(일사량)'로 결정한다
(Pasquill, 1961, Table 2). 기상청 단기예보 SKY(1 맑음 / 3 구름많음 / 4 흐림)를
일사량 등급(Strong/Moderate/Slight)에 1:1 매핑해 산정한다.
실시간 값이 없으면 울산 표준(낮=C, 밤=E)으로 폴백한다.
"""

# Martin Table 3:  a, b, (c,d,f | x<1km), (c,d,f | x>=1km)
MARTIN = {
    "A": (213.0, 0.894, (440.8, 1.041, 9.27), (459.7, 2.094, -9.6)),
    "B": (156.0, 0.894, (106.6, 1.149, 3.3),  (108.2, 1.098, 2.0)),
    "C": (104.0, 0.894, (61.0,  0.911, 0.0),  (61.0,  0.911, 0.0)),
    "D": (68.0,  0.894, (33.2,  0.725, -1.7), (44.5,  0.516, -13.0)),
    "E": (50.5,  0.894, (22.8,  0.675, -1.3), (55.4,  0.305, -34.0)),
    "F": (34.0,  0.894, (14.35, 0.74,  -0.35), (62.6, 0.18,  -48.6)),
}


def stability_class(is_daytime: bool, wind_speed: float = None,
                    sky: int = None) -> str:
    """
    Pasquill 안정도 등급(A~F)을 풍속·하늘상태로 산정.

    is_daytime : 주간(06~18시) 여부
    wind_speed : 지상 풍속 u (m/s). None이면 표준(낮 C / 밤 E)으로 폴백.
    sky        : 기상청 SKY (1 맑음 / 3 구름많음 / 4 흐림). None이면 주간=Moderate,
                 야간=맑음(구름없음)으로 가정.
    """
    if wind_speed is None:
        return "C" if is_daytime else "E"
    u = wind_speed
    if is_daytime:
        # SKY → 일사량(Strong/Moderate/Slight)  (하이픈 등급은 더 안정한 쪽 채택)
        ins = {1: "S", 3: "M", 4: "W"}.get(sky, "M")
        if u < 2:
            return {"S": "A", "M": "B", "W": "B"}[ins]
        if u < 3:
            return {"S": "B", "M": "B", "W": "C"}[ins]
        if u < 5:
            return {"S": "B", "M": "C", "W": "C"}[ins]
        return {"S": "C", "M": "D", "W": "D"}[ins]
    else:
        clear = sky in (None, 1)   # 구름없음(≤3/8)
        if clear:
            if u < 2:
                return "F"
            if u < 3:
                return "E"
            return "D"
        else:                       # 구름많음(≥4/8)
            if u < 2:
                return "E"
            return "D"


def sigma_y_z(x_km: float, stab: str):
    """
    Martin 분산계수. x_km: 풍하거리(km). 반환 (σy, σz) [m].
        σy = a · x^b
        σz = c · x^d + f   (x<1km / x≥1km 구간별 상수)
    """
    x = max(x_km, 1e-3)   # 0/음수 방지 (약 1m)
    a, b, near, far = MARTIN.get(stab, MARTIN["C"])
    c, d, f = near if x < 1.0 else far
    sigma_y = a * (x ** b)
    sigma_z = c * (x ** d) + f
    if sigma_z < 1.0:
        sigma_z = 1.0     # 음수/0 방지 (최소 1m)
    return sigma_y, sigma_z
