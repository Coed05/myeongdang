# -*- coding: utf-8 -*-
"""
api.py — Flask 백엔드 (실시간 데이터). Streamlit 대신 Render 등 파이썬 호스트에 배포.

엔드포인트:
  GET /                  → 프론트엔드(web/index.html)
  GET /api/analyze       → 주소를 받아 실시간 분석 결과(JSON) 반환

실행(로컬):  python api.py   또는   gunicorn api:app
배포(Render): build `pip install -r requirements.txt`, start `gunicorn api:app`
"""

import math
import os

from flask import Flask, request, jsonify, send_from_directory

from geocoding import geocode, search_address
from factories import fetch_near_apartment
from pipeline import run_assessment
from config import (core_of, get_industry_weight, INDUSTRY_WEIGHTS,
                    DEFAULT_STACK_HEIGHT_M)
from geo import decompose_wind
from dispersion import sigma_y_z
from formulas import gaussian_concentration, noise_attenuation_db

app = Flask(__name__, static_folder="web", static_url_path="")

# 같은 단지 결과를 메모리에 캐시(콜드스타트 후 첫 요청만 느림)
_CACHE = {}


@app.errorhandler(Exception)
def _handle_err(e):
    """잡히는 예외는 502 대신 깔끔한 JSON으로 반환."""
    return jsonify({"error": f"분석 중 서버 오류가 발생했어요: {e}"}), 200


@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/api/search")
def api_search():
    """주소 검색 → 후보 목록 [{label, lat, lon}, ...]."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    return jsonify(search_address(q))


@app.route("/api/analyze")
def api_analyze():
    address = (request.args.get("address") or "").strip()
    radius = float(request.args.get("radius") or 5)
    is_day = (request.args.get("day") or "true").lower() == "true"
    wnoise = float(request.args.get("wnoise") or 0.5)
    max_rows = int(request.args.get("max_rows") or 600)
    complex_km = float(request.args.get("complex_km") or 15)
    use_live = (request.args.get("live") or "false").lower() == "true"
    # 검색 후보를 골랐으면 좌표를 직접 받음(재지오코딩 생략)
    qlat = request.args.get("lat")
    qlon = request.args.get("lon")

    if not address and not (qlat and qlon):
        return jsonify({"error": "주소를 입력하세요."})

    # 1) 좌표 결정: 선택 좌표 우선, 없으면 지오코딩(브이월드 + OSM 폴백)
    if qlat and qlon:
        lat, lon = float(qlat), float(qlon)
    else:
        lat, lon = geocode(address)
    if lat is None:
        return jsonify({"error": f"주소 좌표를 찾지 못했습니다: {address}"})

    # 2) 인근 산단 자동탐지 + 공장 실시간 수집 (단지별 캐시)
    key = (round(lat, 3), round(lon, 3), max_rows, complex_km)
    if key in _CACHE:
        factory_df, used = _CACHE[key]
    else:
        # 무료 호스트(512MB) OOM/타임아웃 방지: 가까운 단지 2곳, 단지당 400, 누적 600 상한
        factory_df, used = fetch_near_apartment(lat, lon,
                                                max_complex_km=complex_km,
                                                max_rows=min(max_rows, 400),
                                                max_complexes=2, max_total=600)
        # 캐시 무한 증가 방지: 최근 8개 위치만 유지
        if len(_CACHE) >= 8:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = (factory_df, used)

    # 산업단지/공장을 못 찾아도 그 위치 기준으로 평가(배출원 0 → 안전)하도록
    # run_assessment 는 빈 목록도 처리(소음·악취 0 → AAA)한다.
    import pandas as pd
    if factory_df is None:
        factory_df = pd.DataFrame(columns=["회사명", "업종코드", "위도", "경도"])

    rep = run_assessment(address, factory_df, apt_coords=(lat, lon),
                         is_daytime=is_day, radius_km=radius,
                         use_live_weather=use_live,
                         noise_weight=wnoise, odor_weight=1 - wnoise)
    no_data_note = bool(factory_df.empty)
    if "error" in rep:
        return jsonify(rep)

    nearby = [{**f, "core": core_of(f.get("ksic_code"), f.get("industry_name"))}
              for f in rep["nearby_factories"]]
    out = {
        "address": address,
        "aptLat": rep["coordinates"]["lat"], "aptLon": rep["coordinates"]["lon"],
        "radiusKm": radius, "grade": rep["grade"],
        "composite": rep["composite_score"],
        "noiseDb": rep["noise_db"], "odorOu": rep["odor_ou"],
        "noiseScore": rep["noise_score"], "odorScore": rep["odor_score"],
        "coreCount": rep["core_source_count"], "nearby": nearby,
        "wind": {"speed": rep["wind"]["wind_speed"],
                 "fromDeg": rep["wind"]["wind_from_deg"],
                 "stab": rep["stability_class"]},
        "complexes": [{"name": c["name"], "dist": c["dist_km"]} for c in used],
        "detail": _detail(rep),
        "note": ("주변 탐색 반경 내에서 등록 산업단지의 공장을 찾지 못했어요. "
                 "배출원이 없어 매우 안전한 지역으로 평가됩니다.") if no_data_note else "",
    }
    return jsonify(out)


def _detail(rep):
    """핵심 배출원별 수식 변수·중간값 재현."""
    apt_lat = rep["coordinates"]["lat"]
    apt_lon = rep["coordinates"]["lon"]
    w = rep["wind"]
    u, wfrom = w["wind_speed"], w["wind_from_deg"]
    stab = rep["stability_class"]
    H = DEFAULT_STACK_HEIGHT_M
    facs = rep["nearby_factories"]

    emps = []
    for f in facs:
        if get_industry_weight(f.get("ksic_code"), f.get("industry_name")):
            try:
                emps.append(float(f.get("employees") or 0))
            except (TypeError, ValueError):
                pass
    max_emp = max(emps) if emps else 0

    rows = []
    for f in facs:
        wgt = get_industry_weight(f.get("ksic_code"), f.get("industry_name"))
        if not wgt:
            continue
        try:
            emp = float(f.get("employees") or 0)
        except (TypeError, ValueError):
            emp = 0
        ratio = (emp / max_emp) if (max_emp > 0 and emp > 0) else 1.0
        Q = wgt["odor_q"] * ratio
        x_m, y_m = decompose_wind(f["lat"], f["lon"], apt_lat, apt_lon, wfrom)
        x_km = x_m / 1000.0
        sy, sz = sigma_y_z(max(x_km, 1e-3), stab)
        C = gaussian_concentration(Q, u, x_km, y_m, stab, H)
        spl2 = noise_attenuation_db(wgt["noise_db"], f["distance_km"] * 1000.0)
        core = core_of(f.get("ksic_code"), f.get("industry_name"))
        rows.append({"name": f["factory_name"], "label": INDUSTRY_WEIGHTS[core]["label"],
                     "r2": round(f["distance_km"], 3), "x": round(x_km, 3),
                     "y": round(y_m), "sy": round(sy, 1), "sz": round(sz, 1),
                     "Q": round(Q, 1), "C": round(C, 5), "spl2": round(spl2, 1)})
    return rows


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)), debug=False)
