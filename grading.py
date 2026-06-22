# -*- coding: utf-8 -*-
"""
grading.py — 지수화 및 종합 안심 등급(AAA~F) 산출

Step 3: 소음(dB)·악취(OU) 원시값을 0~100점으로 환산하고
가중치(w1, w2)로 종합 점수를 만든 뒤 AAA~F 등급으로 변환합니다.
"""

from config import (NOISE_LIMIT_DAY, NOISE_LIMIT_NIGHT,
                    ODOR_GOOD_OU, ODOR_LIMIT_OU,
                    NOISE_WEIGHT, ODOR_WEIGHT)


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def noise_score(db: float, is_daytime: bool = True) -> float:
    """
    소음 dB → 0~100점 (높을수록 조용/안전).
    기준치 이하면 만점에 가깝고, 기준치를 크게 넘으면 0점으로 선형 감점.
    만점 기준선: 기준치 - 20dB / 0점 기준선: 기준치 + 15dB
    """
    limit = NOISE_LIMIT_DAY if is_daytime else NOISE_LIMIT_NIGHT
    full = limit - 20.0   # 이 이하 = 100점
    zero = limit + 15.0   # 이 이상 = 0점
    if db <= full:
        return 100.0
    if db >= zero:
        return 0.0
    return _clamp(100.0 * (zero - db) / (zero - full))


def odor_score(ou: float) -> float:
    """
    악취 OU → 0~100점 (높을수록 무취/안전).
    ODOR_GOOD_OU 이하 = 100점, ODOR_LIMIT_OU 이상 = 0점, 사이 선형.
    """
    if ou <= ODOR_GOOD_OU:
        return 100.0
    if ou >= ODOR_LIMIT_OU:
        return 0.0
    return _clamp(100.0 * (ODOR_LIMIT_OU - ou) / (ODOR_LIMIT_OU - ODOR_GOOD_OU))


def composite_score(n_score: float, o_score: float,
                    w1: float = NOISE_WEIGHT, w2: float = ODOR_WEIGHT) -> float:
    """종합 점수 = w1*소음점수 + w2*악취점수 (w1+w2=1)."""
    s = w1 + w2
    if s == 0:
        return 0.0
    return (w1 * n_score + w2 * o_score) / s


def score_to_grade(score: float) -> str:
    """0~100 종합 점수를 AAA~F 등급으로 변환."""
    table = [
        (95, "AAA"), (90, "AA"), (80, "A"),
        (70, "B"), (55, "C"), (40, "D"), (25, "E"),
    ]
    for cutoff, grade in table:
        if score >= cutoff:
            return grade
    return "F"


def evaluate(noise_db: float, odor_ou: float, is_daytime: bool = True,
             w1: float = NOISE_WEIGHT, w2: float = ODOR_WEIGHT) -> dict:
    """소음/악취 원시값 → 점수·종합점수·등급 일괄 산출."""
    n = noise_score(noise_db, is_daytime)
    o = odor_score(odor_ou)
    comp = composite_score(n, o, w1, w2)
    return {
        "noise_db": round(noise_db, 2),
        "odor_ou": round(odor_ou, 3),
        "noise_score": round(n, 1),
        "odor_score": round(o, 1),
        "composite_score": round(comp, 1),
        "grade": score_to_grade(comp),
    }
