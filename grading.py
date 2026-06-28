# -*- coding: utf-8 -*-
"""
grading.py — 통합 등급표(변환점수) 기반 안심 등급(AAA~F) 산출

화공팀 '통합 등급 기준표'(2024 수정본):
    등급   소음(dB)     악취(OU)     변환점수
    AAA    45 이하      3 이하       100
    AA     46~51        4~6          85
    A      52~57        7~10         70
    B      58~63        11~15        55
    C      64~69        16~20        40
    D      70~75        21~25        25
    E      76~85        26~30        10
    F      85 초과      30 초과      0

소음·악취를 '비율로 합산'하기 쉽도록 등급 대신 '변환점수'를 사용한다.
  종합점수 = w1·소음변환점수 + w2·악취변환점수  (w1 + w2 = 1)
  → 종합점수를 다시 AAA~F 등급으로 환산한다.
"""

GRADES = ["AAA", "AA", "A", "B", "C", "D", "E", "F"]
SCORES = [100, 85, 70, 55, 40, 25, 10, 0]
NOISE_UP = [45, 51, 57, 63, 69, 75, 85, float("inf")]   # dB 상한
ODOR_UP = [3, 6, 10, 15, 20, 25, 30, float("inf")]      # OU 상한
# 변환점수 → 등급 경계(인접 점수의 중간값)
SCORE_CUT = [(92.5, "AAA"), (77.5, "AA"), (62.5, "A"), (47.5, "B"),
             (32.5, "C"), (17.5, "D"), (5.0, "E")]


def _band_index(v, ups):
    for i, up in enumerate(ups):
        if v <= up:
            return i
    return len(ups) - 1


def noise_score(db: float, is_daytime: bool = True) -> float:
    """소음 dB → 변환점수(0~100). 통합 등급표 기준."""
    return float(SCORES[_band_index(db, NOISE_UP)])


def odor_score(ou: float) -> float:
    """악취 OU → 변환점수(0~100). 통합 등급표 기준."""
    return float(SCORES[_band_index(ou, ODOR_UP)])


def noise_grade(db: float) -> str:
    return GRADES[_band_index(db, NOISE_UP)]


def odor_grade(ou: float) -> str:
    return GRADES[_band_index(ou, ODOR_UP)]


def composite_score(n_score: float, o_score: float,
                    w1: float = 0.5, w2: float = 0.5) -> float:
    """종합 점수 = w1·소음변환점수 + w2·악취변환점수 (w1+w2=1)."""
    s = w1 + w2
    if s == 0:
        return 0.0
    return (w1 * n_score + w2 * o_score) / s


def score_to_grade(score: float) -> str:
    """종합 변환점수(0~100)를 AAA~F 등급으로 환산."""
    for cutoff, grade in SCORE_CUT:
        if score >= cutoff:
            return grade
    return "F"


def evaluate(noise_db: float, odor_ou: float, is_daytime: bool = True,
             w1: float = 0.5, w2: float = 0.5) -> dict:
    """소음/악취 원시값 → 변환점수·종합점수·등급 일괄 산출."""
    n = noise_score(noise_db, is_daytime)
    o = odor_score(odor_ou)
    comp = composite_score(n, o, w1, w2)
    return {
        "noise_db": round(noise_db, 2),
        "odor_ou": round(odor_ou, 3),
        "noise_score": round(n, 1),
        "odor_score": round(o, 1),
        "noise_grade": noise_grade(noise_db),
        "odor_grade": odor_grade(odor_ou),
        "composite_score": round(comp, 1),
        "grade": score_to_grade(comp),
    }
