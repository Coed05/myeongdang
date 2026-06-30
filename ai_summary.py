# -*- coding: utf-8 -*-
"""
ai_summary.py — 규칙기반 'AI 요약' 생성기

분석 리포트(등급·점수·주변 공장·바람)를 바탕으로 "왜 이 등급이 나왔는가"를
자연어 한 단락으로 설명한다. 외부 LLM 없이 동작(무료·항상 동작)하며,
값에 따라 강조 포인트(소음 vs 악취, 바람 방향성, 가장 가까운 배출원)를
적응적으로 바꾼다.
"""

from config import get_industry_weight

COMPASS16 = ["북", "북북동", "북동", "동북동", "동", "동남동", "남동", "남남동",
             "남", "남남서", "남서", "서남서", "서", "서북서", "북서", "북북서"]
GRADE_DESC = {"AAA": "최상(매우 안전)", "AA": "우수", "A": "양호", "B": "보통",
              "C": "주의", "D": "미흡", "E": "나쁨", "F": "매우 나쁨"}


def _dir(deg):
    return COMPASS16[round(((deg % 360) + 360) % 360 / 22.5) % 16]


def generate_summary(rep: dict) -> str:
    """리포트 dict → 'AI 요약' 문자열."""
    if "error" in rep:
        return ""
    grade = rep.get("grade", "-")
    comp = rep.get("composite_score", 0)
    nd = rep.get("noise_db", 0)
    oo = rep.get("odor_ou", 0)
    ns = rep.get("noise_score", 0)
    os_ = rep.get("odor_score", 0)
    ng = rep.get("noise_grade", "-")
    og = rep.get("odor_grade", "-")
    core = rep.get("core_source_count", 0)
    total = rep.get("nearby_factory_count", 0)
    facs = rep.get("nearby_factories", [])
    wind = rep.get("wind", {}) or {}
    wdir = _dir(wind.get("wind_from_deg", 0))
    wspd = wind.get("wind_speed", 0)

    parts = []
    parts.append(f"왜 {grade}등급({comp}점)일까요?")

    if total == 0 or core == 0:
        parts.append(
            f"반경 내에 소음·악취를 일으키는 핵심 배출원(화학·플라스틱·금속)이 "
            f"없어, 배출 영향이 사실상 0에 가깝습니다. 그래서 '{GRADE_DESC.get(grade, '')}' "
            f"등급으로 매우 안전하게 평가됐어요.")
        return " ".join(parts)

    parts.append(
        f"반경 5km 안에 공장 {total}곳이 있고, 그중 소음·악취가 큰 핵심 배출원은 "
        f"{core}곳이에요.")
    parts.append(
        f"누적 소음은 {nd}dB({ng} 수준), 누적 악취는 {oo}OU({og} 수준)으로 환산됐어요.")

    # 등급을 끌어내린(혹은 올린) 주요인
    if ns < os_:
        parts.append(f"두 지표 중 소음(점수 {ns})이 악취(점수 {os_})보다 낮아, "
                     f"이번 등급은 소음이 더 크게 좌우했습니다.")
    elif os_ < ns:
        parts.append(f"두 지표 중 악취(점수 {os_})가 소음(점수 {ns})보다 낮아, "
                     f"이번 등급은 악취가 더 크게 좌우했습니다.")
    else:
        parts.append("소음과 악취 영향이 비슷한 수준이에요.")

    # 악취 수준의 이유 — 거리·밀집도·확산 (8방위 바람장미 평균 기준)
    if oo < 3.0:
        parts.append(
            f"핵심 배출원이 충분히 떨어져 있고 대기 확산(풍속 {wspd} m/s)으로 희석되어, "
            f"연중 바람 방향을 두루 평균해도 악취 도달이 사실상 미미해요.")
    elif oo < 11.0:
        parts.append(
            f"인근 핵심 배출원의 악취가 일부 도달하지만, 거리·확산을 고려하면 "
            f"비교적 낮은 수준이에요.")
    else:
        parts.append(
            f"가까운 거리에 핵심 배출원이 밀집해 있어, 바람 방향을 평균해도 "
            f"악취 도달이 큰 편이에요.")

    # 가장 가까운 핵심 배출원
    core_facs = [f for f in facs
                 if get_industry_weight(f.get("ksic_code"), f.get("industry_name"))]
    if core_facs:
        nearest = min(core_facs, key=lambda f: f.get("distance_km", 9e9))
        label = nearest.get("industry_name") or "핵심 업종"
        parts.append(
            f"가장 가까운 핵심 배출원은 '{nearest.get('factory_name')}'"
            f"({label}, {round(nearest.get('distance_km', 0), 2)}km)예요.")

    parts.append(f"종합하면 '{GRADE_DESC.get(grade, '')}'({grade}) 수준입니다.")
    return " ".join(parts)
