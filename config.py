# -*- coding: utf-8 -*-
"""
config.py — 환경설정 및 업종별 배출 가중치 테이블
'우리 동네 안심 명당' 백엔드 연산 엔진

- API 인증키는 환경변수(.env)에서 읽어옵니다. 코드에 키를 직접 적지 마세요.
- 업종(KSIC)별 소음/악취 초기 배출 가중치를 정의합니다.
"""

import os

# ---------------------------------------------------------------------------
# 1. API 인증키 (환경변수에서 로드)
# ---------------------------------------------------------------------------
# .env 파일을 쓰는 경우 python-dotenv가 설치되어 있으면 자동 로드합니다.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv 미설치 시 OS 환경변수만 사용
    pass

# 국토교통부 브이월드 지오코딩 API 키 (vworld.kr)
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "")

# 공공데이터포털 산단공 입주기업 현황 API 키 (data.go.kr) — 디코딩된 일반 인증키
DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY", "")

# 기상청 단기예보/실황 API 키 (data.go.kr) — 풍향·풍속용
KMA_API_KEY = os.getenv("KMA_API_KEY", "")

# 카카오맵 JavaScript 키 (developers.kakao.com) — 웹 지도 표시용
KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY", "")


# ---------------------------------------------------------------------------
# 2. 분석 파라미터 (근거는 README의 '파라미터 근거' 참조)
# ---------------------------------------------------------------------------
# 공장 탐색 반경(km). 환경 민원 영향권/생활소음 도달권 기준.
SEARCH_RADIUS_KM = 5.0

# 소음 역자승 감쇄의 기준거리 r1(m). 보통 공장 경계선 1m에서 측정한 SPL1을 기준으로 함.
NOISE_REFERENCE_DISTANCE_M = 1.0

# 굴뚝 유효고 H(m) 기본값. 2차원 단순화 모델에서 상수로 사용.
DEFAULT_STACK_HEIGHT_M = 15.0

# 악취 농도 보정상수(relative → OU 스케일 변환).
# 공장의 실제 악취 배출량(절대 OU·m³/s)은 공개되지 않으므로 업종별 '상대 배출잠재력'
# 가중치(Q)를 가우스식에 대입한 뒤, 단일 상수로 OU 등급밴드(3~30)에 맞춰 보정한다.
# 전국 최대 석유화학·산단 밀집지(여수·온산·녹산 등) 주거 인접지가 최악(E~F)에 닿고
# 청정지역이 AAA에 닿도록 실측 분포로 캘리브레이션한 값.
ODOR_CALIBRATION = 12000.0

# 악취 방향성 처리: 단일 풍향 대신 8방위 '바람장미 평균'을 사용한다.
# (주거 입지 추천은 그날그날 풍향이 아니라 장기 노출을 봐야 하므로)
ODOR_WIND_DIRS = 8

# 종합 등급 가중치 (w1 = 소음, w2 = 악취). 반드시 합이 1.
NOISE_WEIGHT = 0.5   # w1
ODOR_WEIGHT = 0.5    # w2

# 표준 풍속 u (m/s). 울산 2025 기상통계 기준 (화공팀 산출).
WIND_SPEED_AVG = 2.98     # 연평균(단일화 적용 시)
WIND_SPEED_DAY = 3.24     # 주간
WIND_SPEED_NIGHT = 2.61   # 야간

# 환경부 주거지역 소음 기준 (dB)
NOISE_LIMIT_DAY = 55   # 주간
NOISE_LIMIT_NIGHT = 45  # 야간

# 악취방지법 공업지역 부지경계 복합악취 배출허용기준(희석배수, OU) 참고치.
# 등급화에서 만점/0점 기준선으로 사용.
ODOR_GOOD_OU = 1.0    # 이 이하면 사실상 무취 → 만점
ODOR_LIMIT_OU = 15.0  # 공업지역 배출허용기준(부지경계) 수준 → 하한


# ---------------------------------------------------------------------------
# 3. 3대 핵심 배출 업종 가중치 (화공팀 'Q,SPL1 상수값' 시트 기준)
# ---------------------------------------------------------------------------
# 실측 배출량은 영업비밀이라 공개되지 않으므로, 정부 공인 '배출 원단위 가중치'와
# '물리적 소음 표준'을 대입하는 시뮬레이션 방식을 사용한다.
# 주거지에 가장 큰 영향을 주는 산단 내 3대 핵심 업종만 배출원으로 본다.
#   - odor_q   : 악취 배출 잠재력 가중치 (가우스 확산식 Q)
#   - noise_db : 초기 소음 SPL1 (공장경계 1m 기준, 역자승 감쇄식 입력)
INDUSTRY_WEIGHTS = {
    "C20": {"odor_q": 100, "noise_db": 85, "label": "화학·석유화학"},
    "C22": {"odor_q": 60,  "noise_db": 80, "label": "고무·플라스틱"},
    "C25": {"odor_q": 15,  "noise_db": 95, "label": "금속가공·기계"},
}

# KSIC 숫자코드 division(앞 2자리) → 핵심 업종 버킷
# 19(석유정제)·20(화학) → C20 / 22(고무·플라스틱) → C22 / 24(1차금속)·25(금속가공) → C25
DIVISION_TO_CORE = {
    "19": "C20", "20": "C20",
    "22": "C22",
    "24": "C25", "25": "C25",
}

# 업종'명' 키워드 → 핵심 업종 (숫자코드가 없을 때 보조 매칭)
NAME_TO_CORE = [
    ("석유", "C20"), ("정제", "C20"), ("화학", "C20"),
    ("플라스틱", "C22"), ("고무", "C22"),
    ("금속 가공", "C25"), ("금속가공", "C25"), ("제철", "C25"),
    ("제련", "C25"), ("금속", "C25"),
]


def core_of(code=None, name=None):
    """업종코드/명을 받아 핵심 업종('C20'/'C22'/'C25') 또는 None(비배출원) 반환.
    code 자리에 숫자코드/'C20'형/업종명 무엇이 와도 처리(구버전 캐시 호환)."""
    texts = []
    if code is not None:
        s = str(code).strip().upper()
        if s[:3] in INDUSTRY_WEIGHTS:          # 이미 'C20' 형태
            return s[:3]
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) >= 2 and digits[:2] in DIVISION_TO_CORE:
            return DIVISION_TO_CORE[digits[:2]]
        texts.append(str(code))                # 숫자코드가 아니면 업종명일 수 있음
    if name:
        texts.append(str(name))
    for t in texts:
        for kw, core in NAME_TO_CORE:
            if kw in t:
                return core
    return None


def get_industry_weight(code=None, name=None):
    """핵심 3업종이면 가중치 dict, 아니면 None(배출원 아님)."""
    core = core_of(code, name)
    return INDUSTRY_WEIGHTS.get(core) if core else None
