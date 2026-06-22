# -*- coding: utf-8 -*-
"""
app.py — '우리 동네 안심 명당' 웹 시연 (Streamlit)

실행:  streamlit run app.py

흐름: 주소 검색 → 결과 선택 → (인근 산업단지 자동 탐지) 공장 수집
      → 소음/악취 화공 수식 → 종합 안심 등급(AAA~F) + 지도
모든 조작은 본문 상단 '검색 카드'에 모았고, 결과는 session_state로 유지됩니다.
"""

import json
import math

import os

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# 배포(Streamlit Cloud)에서는 .env 대신 'Secrets'를 환경변수로 연결.
# (config 모듈이 import 시점에 키를 읽으므로 반드시 그 전에 실행)
try:
    for _k in ("VWORLD_API_KEY", "DATA_GO_KR_API_KEY", "KMA_API_KEY",
               "KAKAO_JS_KEY"):
        if _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass  # 로컬(.env 사용) 등 secrets 없을 때는 무시

from geocoding import geocode, search_address
from factories import fetch_and_geocode, fetch_near_apartment
from pipeline import run_assessment
from config import (VWORLD_API_KEY, KAKAO_JS_KEY, core_of, INDUSTRY_WEIGHTS,
                    get_industry_weight, DEFAULT_STACK_HEIGHT_M,
                    NOISE_REFERENCE_DISTANCE_M)
from geo import decompose_wind
from dispersion import sigma_y_z
from formulas import (gaussian_concentration, noise_attenuation_db,
                      combine_noise_db)

# 핵심 업종별 지도 색상
CORE_COLOR = {"C20": "#dc2626", "C22": "#ea580c", "C25": "#2563eb"}

try:
    import folium
    from streamlit_folium import st_folium
    HAS_MAP = True
except ImportError:
    HAS_MAP = False

st.set_page_config(page_title="우리 동네 안심 명당", page_icon="🏠", layout="wide")

st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');

html, body, [class*="css"], .stApp, button, input, textarea, select {
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif;
}
.stApp { background: #fbfcfd; }

#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

.block-container { padding-top: 1.4rem; padding-bottom: 2.5rem; max-width: 1180px; }
h1, h2, h3, h4 { letter-spacing: -0.5px; color: #0f172a; }

/* 카드(컨테이너 보더) */
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 16px; border-color: #e8edf2;
  box-shadow: 0 1px 3px rgba(15,23,42,0.04);
}

/* 지표 카드 */
[data-testid="stMetric"] {
  background: #ffffff; border: 1px solid #e8edf2; border-radius: 14px;
  padding: 16px 18px; box-shadow: 0 1px 2px rgba(15,23,42,0.04);
  transition: box-shadow .2s ease;
}
[data-testid="stMetric"]:hover { box-shadow: 0 6px 18px rgba(15,23,42,0.08); }
[data-testid="stMetricLabel"] p { color: #64748b; font-size: 0.8rem; font-weight: 500; }
[data-testid="stMetricValue"] { font-weight: 800; color: #0f172a; }

/* 버튼 */
.stButton > button {
  border-radius: 10px; font-weight: 700; border: 1px solid #dbe2e9;
  transition: transform .12s ease, box-shadow .12s ease;
}
.stButton > button:hover { transform: translateY(-1px); }
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #1aa257, #15803d); border: none; color: #fff;
  box-shadow: 0 3px 10px rgba(26,152,80,0.32);
}

/* 익스팬더 */
[data-testid="stExpander"] {
  border: 1px solid #e8edf2; border-radius: 12px; background: #ffffff;
  box-shadow: 0 1px 2px rgba(15,23,42,0.03);
}
[data-testid="stExpander"] summary { font-weight: 600; color: #334155; }

/* 데이터프레임 */
[data-testid="stDataFrame"] {
  border-radius: 12px; overflow: hidden; border: 1px solid #e8edf2;
}

/* 사이드바 */
section[data-testid="stSidebar"] {
  background: #f7f9fb; border-right: 1px solid #e8edf2;
}
section[data-testid="stSidebar"] h3 { font-size: 1.0rem; }
/* 사이드바 상단 여백 균형 */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 1.5rem; }
section[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }

[data-baseweb="input"], [data-baseweb="select"] > div { border-radius: 9px; }
hr { margin: 0.5rem 0; border-color: #eef2f6; }
</style>
""", unsafe_allow_html=True)

GRADE_COLOR = {
    "AAA": "#1a9850", "AA": "#66bd63", "A": "#a6d96a",
    "B": "#f9d057", "C": "#fdae61", "D": "#f46d43",
    "E": "#d73027", "F": "#a50026",
}

ss = st.session_state
ss.setdefault("report", None)
ss.setdefault("candidates", [])
ss.setdefault("picked", None)

GRADE_DESC = {
    "AAA": "최상 · 매우 안전", "AA": "우수", "A": "양호", "B": "보통",
    "C": "주의", "D": "미흡", "E": "나쁨", "F": "매우 나쁨",
}


def render_sidebar():
    sb = st.sidebar
    # 브랜드 헤더
    sb.markdown(
        "<div style='padding:15px 16px;border-radius:14px;"
        "background:linear-gradient(135deg,#1aa25718,#1aa25706);"
        "border:1px solid #cfe8da;margin-bottom:14px;'>"
        "<div style='font-size:17px;font-weight:800;color:#14803d;'>🏠 우리 동네 안심 명당</div>"
        "<div style='font-size:12px;color:#5b7a68;margin-top:3px;'>"
        "산단 인근 소음·악취 안심 등급 진단</div></div>",
        unsafe_allow_html=True)

    # 분석 결과 요약 자리(나중에 fill_summary로 채움)
    summary_slot = sb.empty()

    # 등급 범례
    sb.markdown("**📊 등급 범례**")
    rows = "".join(
        f"<div style='display:flex;align-items:center;gap:8px;margin:2px 0;'>"
        f"<span style='display:inline-block;min-width:38px;text-align:center;"
        f"background:{c};color:#fff;border-radius:6px;padding:2px 0;"
        f"font-weight:700;font-size:11px;'>{g}</span>"
        f"<span style='font-size:12.5px;color:#475569;'>{GRADE_DESC[g]}</span></div>"
        for g, c in GRADE_COLOR.items())
    sb.markdown(rows, unsafe_allow_html=True)

    sb.divider()
    sb.markdown("**📝 사용 방법**")
    sb.markdown(
        "1. 아파트 **주소 검색** 후 결과 선택\n"
        "2. 반경·주야·가중치 조정(선택)\n"
        "3. **안심 등급 분석** 클릭\n"
        "4. 지도에서 주변 공장·바람 확인")

    sb.markdown("**🔗 데이터 출처**")
    sb.markdown(
        "- 좌표: **국토교통부 브이월드**\n"
        "- 공장·업종: **한국산업단지공단**\n"
        "- 바람: **기상청 단기예보**")

    sb.markdown("**⚠️ 참고**")
    sb.caption("본 등급은 정부 공인 배출 원단위·소음 표준과 지역 기상통계를 화공 "
               "수식에 적용해 산출한 추정치예요. 실제 환경은 그날의 기상과 공장 운영 "
               "상황에 따라 달라질 수 있어요.")
    return summary_slot


def fill_summary(slot):
    """사이드바 상단 결과 요약 카드를 현재 ss.report 로 채움(없으면 비움)."""
    rep = ss.get("report")
    if not rep:
        return
    g = rep["grade"]
    c = GRADE_COLOR.get(g, "#888")
    slot.markdown(
        f"<div style='padding:14px 16px;border-radius:12px;background:{c}14;"
        f"border:1px solid {c}55;margin-bottom:6px;'>"
        f"<div style='font-size:11px;color:#64748b;letter-spacing:.3px;'>현재 분석 결과</div>"
        f"<div style='display:flex;align-items:baseline;gap:8px;'>"
        f"<span style='font-size:30px;font-weight:800;color:{c};'>{g}</span>"
        f"<span style='font-size:14px;color:#334155;font-weight:600;'>"
        f"{rep['composite_score']}점 · {GRADE_DESC.get(g,'')}</span></div>"
        f"<div style='font-size:12px;color:#64748b;margin-top:7px;line-height:1.6;'>"
        f"소음 {rep['noise_db']} dB · 악취 {rep['odor_ou']} OU<br>"
        f"핵심 배출원 {rep.get('core_source_count',0)} / {rep['nearby_factory_count']}곳</div></div>",
        unsafe_allow_html=True)


# 사이드바는 항상 먼저 렌더(에러로 st.stop 돼도 유지). 요약은 자리표시자로 갱신.
_summary_slot = render_sidebar()
fill_summary(_summary_slot)


@st.cache_data(show_spinner=False)
def load_factories(complex_name: str, max_rows: int) -> pd.DataFrame:
    return fetch_and_geocode(complex_name, max_rows=max_rows,
                             cache_path=f"factory_cache_{complex_name}.csv")


@st.cache_data(show_spinner=False)
def load_near(lat: float, lon: float, complex_km: float, max_rows: int):
    return fetch_near_apartment(round(lat, 4), round(lon, 4),
                                max_complex_km=complex_km, max_rows=max_rows)


def downwind_point(lat, lon, wind_from_deg, dist_km=1.5):
    going = math.radians((wind_from_deg + 180) % 360)
    dlat = (dist_km / 110.54) * math.cos(going)
    dlon = (dist_km / (111.32 * math.cos(math.radians(lat)))) * math.sin(going)
    return lat + dlat, lon + dlon


KAKAO_TEMPLATE = """
<div id="map" style="width:100%;height:520px;border-radius:12px;"></div>
<script src="//dapi.kakao.com/v2/maps/sdk.js?appkey=__KEY__&autoload=false"></script>
<script>
kakao.maps.load(function(){
  var center = new kakao.maps.LatLng(__LAT__, __LON__);
  var map = new kakao.maps.Map(document.getElementById('map'),
                               {center: center, level: 6});
  map.addControl(new kakao.maps.ZoomControl(),
                 kakao.maps.ControlPosition.RIGHT);
  // 아파트 위치
  new kakao.maps.Marker({position: center, map: map});
  // 5km(탐색 반경) 원
  new kakao.maps.Circle({
    center: center, radius: __RADIUS__, map: map,
    strokeWeight: 2, strokeColor: '__COLOR__', strokeOpacity: 0.85,
    strokeStyle: 'solid', fillColor: '__COLOR__', fillOpacity: 0.07
  });
  // 바람 가는 방향 선
  var wp = new kakao.maps.LatLng(__WLAT__, __WLON__);
  new kakao.maps.Polyline({
    path: [center, wp], map: map, strokeWeight: 3,
    strokeColor: '#2563eb', strokeOpacity: 0.8, strokeStyle: 'solid'
  });
  // 공장 점들
  var facs = __FACS__;
  facs.forEach(function(f){
    var el = document.createElement('div');
    el.title = f.name + ' · ' + f.ind + ' · ' + f.d + 'km';
    el.style.cssText = 'width:9px;height:9px;background:#b91c1c;' +
      'border:1px solid #fff;border-radius:50%;box-shadow:0 0 2px rgba(0,0,0,.4);';
    new kakao.maps.CustomOverlay({
      position: new kakao.maps.LatLng(f.lat, f.lon),
      content: el, map: map, xAnchor: 0.5, yAnchor: 0.5
    });
  });
  // 반경이 한눈에 들어오도록 영역 맞춤
  var b = new kakao.maps.LatLngBounds();
  b.extend(new kakao.maps.LatLng(__LAT__ + __DLT__, __LON__ + __DLN__));
  b.extend(new kakao.maps.LatLng(__LAT__ - __DLT__, __LON__ - __DLN__));
  map.setBounds(b);
});
</script>
"""


def render_kakao_map(report: dict, color: str, radius: float):
    apt_lat = report["coordinates"]["lat"]
    apt_lon = report["coordinates"]["lon"]
    w = report["wind"]
    wlat, wlon = downwind_point(apt_lat, apt_lon, w["wind_from_deg"], 1.5)
    facs = [{"lat": f["lat"], "lon": f["lon"], "name": f["factory_name"],
             "ind": f["ksic_code"], "d": f["distance_km"]}
            for f in report["nearby_factories"]]
    dlt = radius / 111.0 * 1.2          # 위도 여유
    dln = radius / (88.0) * 1.2         # 경도 여유(중위도 근사)
    html = (KAKAO_TEMPLATE
            .replace("__KEY__", KAKAO_JS_KEY)
            .replace("__LAT__", f"{apt_lat:.6f}")
            .replace("__LON__", f"{apt_lon:.6f}")
            .replace("__WLAT__", f"{wlat:.6f}")
            .replace("__WLON__", f"{wlon:.6f}")
            .replace("__RADIUS__", str(int(radius * 1000)))
            .replace("__COLOR__", color)
            .replace("__DLT__", f"{dlt:.4f}")
            .replace("__DLN__", f"{dln:.4f}")
            .replace("__FACS__", json.dumps(facs, ensure_ascii=False)))
    components.html(html, height=540)


# ── 헤더 ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="border-left:6px solid #1a9850;padding:4px 0 4px 16px;margin-bottom:10px;">
  <div style="font-size:28px;font-weight:800;">🏠 우리 동네 안심 명당</div>
  <div style="color:#64748b;font-size:14px;margin-top:2px;">
    주소만 입력하면 인근 산업단지를 자동 탐지해 소음·악취 안심 등급(AAA~F)을 매깁니다.
  </div>
</div>
""", unsafe_allow_html=True)

with st.expander("📚 분석 방법론 · 과학적 근거"):
    st.markdown("""
**왜 시뮬레이션인가?** 공장의 실시간 배출량·악취 농도는 영업비밀이라 공개되지
않습니다. 그래서 본 플랫폼은 **정부 공인 '배출 원단위 가중치'와 '물리적 소음 표준'을
공인 화공 수식에 대입**하는 시뮬레이션 방식을 사용합니다. (실측 불가 영역을
공공데이터+물리식으로 합리적으로 추정)

**3대 핵심 배출 업종** — 주거지에 상시 민원을 일으키는 화학·플라스틱·금속만 배출원으로 봅니다.

| 업종 | 악취 잠재력 Q | 초기소음 SPL₁ | 근거 |
|---|---|---|---|
| C20 화학·석유화학 | 100 | 85 dB | 복합악취 평균 10,000 OU↑(국립환경과학원) / 24h 연속 소음 |
| C22 고무·플라스틱 | 60 | 80 dB | 사출 성형 시 특정악취물질(악취방지법) |
| C25 금속가공·기계 | 15 | 95 dB | 금속 프레스 '강렬한 소음작업'(산안법 규칙 §512) |

**악취 — 2차원 가우스 확산 모델**  `C = Q/(π·u·σy·σz)·exp(−y²/2σy²)·exp(−H²/2σz²)`
- `Q = 업종 가중치 × (공장 규모 / 단지 내 최대 규모)` — 규모가 큰 공장일수록 배출 잠재력 Q↑ (규모는 고용 인원 기준)
- `σy = a·xᵇ`, `σz = c·xᵈ` (Martin, 1976) — 낮 C등급(a=104,b=0.894,c=61,d=0.911) /
  밤 E등급(50.5, 0.894, 22.8, 0.678), x는 km
- 굴뚝 유효고 H=15 m 고정

**소음 — 거리 역자승 감쇄 + 로그 합산**  `SPL₂ = SPL₁ − 20·log₁₀(r₂)` (r₁=1 m),
여러 공장은 `SPL_total = 10·log₁₀(Σ10^(SPLᵢ/10))`

**표준 풍속 u** — 울산 2025 기상통계 기준 낮 3.24 / 밤 2.61 m/s
(단일화 시 연평균 2.98 m/s, Pasquill상 낮 C·밤 E를 모두 만족하는 통계 중심값)

*법적·학술 근거: 악취방지법 §6·시행규칙[별표1], 산업안전보건기준 규칙 §512,
Pasquill(1961) 안정도, Martin(1976) 분산계수, 환경부 주거지역 소음기준(주55/야45 dB).*
""")

# ── 검색 카드 (모든 조작을 본문에) ──────────────────────────────────────────
with st.container(border=True):
    cq, cb = st.columns([5, 1])
    query = cq.text_input("주소", "울산 남구 야음동", label_visibility="collapsed",
                          placeholder="아파트 주소를 입력하세요 (예: 울산 남구 야음동)")
    if cb.button("🔍 주소 검색", use_container_width=True):
        ss.candidates = search_address(query)
        ss.picked = None
        if not ss.candidates:
            st.warning("검색 결과가 없습니다. 더 구체적으로 입력해 보세요.")

    if ss.candidates:
        labels = [c["label"] for c in ss.candidates]
        sel = st.selectbox("📍 검색 결과에서 선택", labels)
        ss.picked = ss.candidates[labels.index(sel)]

    o1, o2, o3 = st.columns([1.4, 1, 1.4])
    radius_km = o1.slider("공장 탐색 반경 (km)", 1.0, 10.0, 5.0, step=0.5)
    period = o2.radio("평가 기준", ["주간", "야간"], horizontal=True)
    is_daytime = period == "주간"
    w_noise = o3.slider("소음 가중치 (나머지는 악취)", 0.0, 1.0, 0.5, step=0.05)
    w_odor = round(1.0 - w_noise, 2)

    with st.expander("⚙️ 고급 설정"):
        a1, a2 = st.columns(2)
        auto_complex_km = a1.slider("산업단지 자동탐지 반경 (km)", 5, 30, 15)
        max_rows = a2.slider("단지별 공장 수집 상한", 100, 2000, 600, step=100)
        manual_complex = st.text_input("산업단지 직접 지정 (선택)", "")
        use_live = st.checkbox("기상청 실시간 바람 사용", value=False,
                               help="기상청 키 승인 후 체크. 실패 시 기본 바람으로 폴백.")

    run = st.button("🏠 안심 등급 분석", type="primary", use_container_width=True)


# ── 분석 (결과를 session_state에 저장) ──────────────────────────────────────
if run:
    if ss.picked:
        apt_lat, apt_lon, apt_label = (ss.picked["lat"], ss.picked["lon"],
                                       ss.picked["label"])
    else:
        with st.spinner("주소 좌표 변환 중..."):
            apt_lat, apt_lon = geocode(query)
        apt_label = query
    if apt_lat is None:
        st.error(f"주소 좌표를 찾지 못했습니다: {query}. '주소 검색'으로 골라 보세요.")
        st.stop()

    used = []
    if manual_complex.strip():
        with st.spinner(f"'{manual_complex}' 공장 수집·지오코딩 중..."):
            factory_df = load_factories(manual_complex.strip(), max_rows)
        used = [{"name": manual_complex.strip(), "dist_km": "-",
                 "region": "직접 지정", "factory_count": len(factory_df)}]
    else:
        with st.spinner("인근 산업단지 자동 탐지 + 공장 수집·지오코딩 중 "
                        "(첫 실행은 한 단지당 1~2분, 이후 캐시로 즉시)..."):
            factory_df, used = load_near(apt_lat, apt_lon,
                                         auto_complex_km, max_rows)
    if factory_df.empty:
        st.error("주변 산업단지를 찾지 못했습니다. '고급 설정'에서 자동탐지 반경을 "
                 "넓히거나 산업단지를 직접 지정해 보세요.")
        st.stop()

    report = run_assessment(
        address=apt_label, factory_df=factory_df, apt_coords=(apt_lat, apt_lon),
        is_daytime=is_daytime, radius_km=radius_km,
        use_live_weather=use_live, noise_weight=w_noise, odor_weight=w_odor,
    )
    report["_radius"] = radius_km
    report["_complexes"] = used
    ss.report = report


# ── 렌더 (session_state에서 읽어 항상 표시) ─────────────────────────────────
if not HAS_MAP:
    st.warning("지도를 보려면 `pip install folium streamlit-folium` 후 재실행하세요.")


def compute_detail(report: dict):
    """핵심 배출원별 수식 변수·중간 계산값을 재현해 표로 반환."""
    apt_lat = report["coordinates"]["lat"]
    apt_lon = report["coordinates"]["lon"]
    w = report["wind"]
    u, wfrom = w["wind_speed"], w["wind_from_deg"]
    stab = report["stability_class"]
    H = DEFAULT_STACK_HEIGHT_M
    facs = report["nearby_factories"]

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
        rows.append({
            "회사명": f["factory_name"],
            "업종": INDUSTRY_WEIGHTS[core]["label"],
            "거리 r₂(km)": round(f["distance_km"], 3),
            "풍하 x(km)": round(x_km, 3),
            "횡풍 y(m)": round(y_m, 0),
            "σy(m)": round(sy, 1),
            "σz(m)": round(sz, 1),
            "Q": round(Q, 1),
            "악취 C(OU)": round(C, 5),
            "소음 SPL₂(dB)": round(spl2, 1),
        })
    return rows, {"u": u, "stab": stab, "H": H, "wfrom": wfrom}


def render(report: dict):
    grade = report["grade"]
    color = GRADE_COLOR.get(grade, "#888")
    radius = report.get("_radius", 5.0)
    apt_lat = report["coordinates"]["lat"]
    apt_lon = report["coordinates"]["lon"]

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:26px;padding:22px 26px;
             border-radius:16px;background:linear-gradient(135deg,{color}1a,{color}0d);
             border:1px solid {color}55;box-shadow:0 2px 12px {color}1f;margin-top:10px;">
          <div style="font-size:66px;font-weight:800;color:{color};line-height:1;">{grade}</div>
          <div style="border-left:1px solid {color}40;padding-left:24px;">
            <div style="font-size:14px;color:#64748b;">종합 안심 주거 등급</div>
            <div style="font-size:30px;font-weight:800;color:#1f2937;">{report['composite_score']}<span style="font-size:16px;color:#94a3b8;"> / 100점</span></div>
            <div style="font-size:13px;color:#94a3b8;margin-top:2px;">📍 {report['address']}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    st.write("")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("누적 소음", f"{report['noise_db']} dB", f"{report['noise_score']}점")
    c2.metric("누적 악취", f"{report['odor_ou']} OU", f"{report['odor_score']}점")
    c3.metric("핵심 배출원 / 반경내",
              f"{report.get('core_source_count', 0)} / {report['nearby_factory_count']}",
              help="화학·플라스틱·금속 3대 핵심 업종만 배출원으로 계산")
    w = report["wind"]
    c4.metric("바람", f"{w['wind_speed']} m/s",
              f"{w['wind_from_deg']}° / 안정도 {report['stability_class']}")

    cx = report.get("_complexes", [])
    if cx:
        chips = "  ".join(
            f"<span style='background:#eef2f7;border:1px solid #dbe2ea;border-radius:999px;"
            f"padding:3px 10px;font-size:12px;color:#475569;'>🏭 {c['name']} "
            f"({c['dist_km']}km · {c.get('factory_count','?')}곳)</span>" for c in cx)
        st.markdown(f"**자동 탐지된 산업단지** &nbsp; {chips}", unsafe_allow_html=True)

    st.write("")
    left, right = st.columns([3, 2])
    with left:
        if KAKAO_JS_KEY:
            render_kakao_map(report, color, radius)
        elif HAS_MAP:
            m = folium.Map(location=[apt_lat, apt_lon], zoom_start=13,
                           tiles=None)
            # 기본: 브이월드 한국지도(컬러, 작동 확인됨) — 동해·독도 표기
            if VWORLD_API_KEY:
                base = "https://api.vworld.kr/req/wmts/1.0.0/" + VWORLD_API_KEY
                folium.TileLayer(base + "/Base/{z}/{y}/{x}.png",
                                 attr="© VWorld (국토교통부)",
                                 name="브이월드 한국지도", max_zoom=19).add_to(m)
                folium.TileLayer(base + "/Hybrid/{z}/{y}/{x}.png",
                                 attr="© VWorld", name="브이월드 위성",
                                 max_zoom=19, show=False).add_to(m)
            # 더 밝고 단정한 대체 지도(작동 확인됨)
            folium.TileLayer("CartoDB positron", name="밝은 지도",
                             show=not bool(VWORLD_API_KEY)).add_to(m)
            folium.Circle([apt_lat, apt_lon], radius=radius * 1000, color=color,
                          fill=True, fill_opacity=0.06, weight=2).add_to(m)
            folium.Marker([apt_lat, apt_lon], tooltip="검색 아파트",
                          icon=folium.Icon(color="blue", icon="home",
                                           prefix="fa")).add_to(m)
            wp = downwind_point(apt_lat, apt_lon, w["wind_from_deg"], 1.5)
            folium.PolyLine([[apt_lat, apt_lon], list(wp)], color="#3b82f6",
                            weight=3, opacity=0.7,
                            tooltip=f"바람 가는 방향 {w['wind_speed']}m/s").add_to(m)
            for f in report["nearby_factories"]:
                core = core_of(f.get("ksic_code"), f.get("industry_name"))
                if core:                       # 핵심 배출원: 업종색 큰 점
                    col, rad, op = CORE_COLOR[core], 6, 0.85
                else:                          # 비배출원: 회색 작은 점
                    col, rad, op = "#9ca3af", 3, 0.5
                folium.CircleMarker(
                    [f["lat"], f["lon"]], radius=rad, color=col,
                    fill=True, fill_opacity=op,
                    tooltip=(f"{f['factory_name']} · "
                             f"{f.get('industry_name') or f['ksic_code']} · "
                             f"{f['distance_km']}km")).add_to(m)
            folium.LayerControl(collapsed=True).add_to(m)
            st_folium(m, height=520, width=720, returned_objects=[])
        else:
            dfm = pd.DataFrame(report["nearby_factories"])
            if not dfm.empty:
                st.map(dfm.rename(columns={"lat": "latitude", "lon": "longitude"}))
    with right:
        st.subheader(f"반경 내 공장 {report['nearby_factory_count']}개")
        # 색상 범례
        st.markdown(
            "<span style='color:#dc2626;'>●</span> 화학·석유화학 &nbsp;"
            "<span style='color:#ea580c;'>●</span> 고무·플라스틱 &nbsp;"
            "<span style='color:#2563eb;'>●</span> 금속·기계 &nbsp;"
            "<span style='color:#9ca3af;'>●</span> 비배출원",
            unsafe_allow_html=True)
        if report["nearby_factories"]:
            rows = []
            for f in report["nearby_factories"]:
                core = core_of(f.get("ksic_code"), f.get("industry_name"))
                rows.append({
                    "핵심": INDUSTRY_WEIGHTS[core]["label"] if core else "-",
                    "회사명": f["factory_name"],
                    "업종": f.get("industry_name") or f.get("ksic_code"),
                    "거리(km)": f["distance_km"],
                })
            tbl = pd.DataFrame(rows)
            st.dataframe(tbl, hide_index=True, height=430, width="stretch")

    st.info("본 진단은 정부 공인 배출 원단위·산업안전 소음표준·지역 기상통계를 가우스 "
            "확산·역자승 감쇄 수식에 적용해 산출해요. 실제 환경은 그날의 기상·공장 운영 "
            "상황에 따라 달라질 수 있으니 참고용으로 활용하세요. 자세한 계산 근거는 상단 "
            "'📚 분석 방법론'에서 볼 수 있어요.")

    # ── 세부 계산식·변수값 (고급) ───────────────────────────────────────────
    with st.expander("🔬 세부 계산식 · 변수값 (고급)"):
        rows, p = compute_detail(report)
        st.markdown(
            f"**고정 변수** — 풍속 u = {p['u']} m/s · 안정도 **{p['stab']}등급** · "
            f"굴뚝높이 H = {p['H']} m · 풍향(불어오는) {p['wfrom']}° · 기준거리 r₁ = 1 m")
        st.markdown("**① 악취 — 2차원 가우스 확산**")
        st.latex(r"C=\frac{Q}{\pi\,u\,\sigma_y\,\sigma_z}"
                 r"\exp\!\Big(-\frac{y^2}{2\sigma_y^2}\Big)"
                 r"\exp\!\Big(-\frac{H^2}{2\sigma_z^2}\Big),\quad "
                 r"\sigma_y=a\,x^{b},\ \ \sigma_z=c\,x^{d}")
        st.markdown("**② 소음 — 거리 역자승 감쇄 + 로그 합산**")
        st.latex(r"SPL_2=SPL_1-20\log_{10}(r_2),\qquad "
                 r"SPL_{total}=10\log_{10}\!\sum_i 10^{\,SPL_i/10}")
        st.markdown("**③ 악취 배출량** "
                    r"$Q=\text{업종 가중치}\times(\text{공장 크기}/\text{최대 크기})$ "
                    "(크기 = 고용인원 대용치)")
        if rows:
            st.markdown("**핵심 배출원별 변수·기여값**")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            odor_sum = sum(r["악취 C(OU)"] for r in rows)
            noise_total = combine_noise_db([r["소음 SPL₂(dB)"] for r in rows])
            st.markdown(
                f"→ **누적 악취** ΣC = **{odor_sum:.4f} OU**  ·  "
                f"**누적 소음**(로그합) = **{noise_total:.2f} dB**  "
                f"→ 종합 점수 {report['composite_score']} ({report['grade']}등급)")
        else:
            st.caption("반경 내 핵심 배출원(C20·C22·C25)이 없어 표시할 계산이 없습니다.")


if ss.report:
    render(ss.report)
else:
    st.info("위에서 **주소 입력 → 🔍 주소 검색 → 결과 선택 → 🏠 안심 등급 분석** 순으로 눌러주세요.")

# 분석 후 사이드바 요약 카드를 최신 결과로 갱신
fill_summary(_summary_slot)
