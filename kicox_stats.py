# -*- coding: utf-8 -*-
"""
kicox_stats.py — 한국산업단지공단 산업동향조사 통계 조회 서비스 클라이언트

Base URL: https://apis.data.go.kr/B550624/indparkstats
(하랑님이 활용신청·승인 완료한 키로 동작하는 API)

주의: 이 API는 '공장 좌표'를 주지 않습니다. 산단별·업종별 집계 통계
(입주업체 수, 가동률, 생산/수출/고용 등)만 제공합니다.
→ 5km 거리 계산용 공장 위치는 factories.py(공장등록정보 API/파일)로 따로 받습니다.
→ 여기서 얻는 '업종별 입주업체 수'는 가우스식 Q(배출량) 가중치를 정교화하는
   보조 자료로 활용합니다.
"""

import json as _json
import xml.etree.ElementTree as ET

import requests

from config import DATA_GO_KR_API_KEY

BASE = "https://apis.data.go.kr/B550624/indparkstats"

# 12개 상세기능 중 자주 쓰는 것
OP_MOVE_IN_BY_INDUSTRY = "kicoxMvnCmpnyByIndustryStatsService"  # 업종별 입주업체 현황
OP_MOVE_IN_BY_COMPLEX = "kicoxMvnCmpnyStatsService"            # 단지별 입주업체 현황
OP_OPRATE_BY_INDUSTRY = "kicoxOpRateByIndustryStatsService"    # 업종별 가동률
OP_EMP_BY_INDUSTRY = "kicoxEmpByIndustryStatsService"          # 업종별 고용 현황


def fetch_stats(operation: str, stdr_ym: str,
                api_key: str = None, want_json: bool = True) -> list:
    """
    산업동향 통계 1종을 조회.

    매개변수
    --------
    operation : 위 OP_* 중 하나 (상세기능 경로명)
    stdr_ym   : 검색년월 (예: '202412'). Swagger 명세상 필수 파라미터는 stdrYm 단일.
    want_json : True면 JSON 요청

    반환: item dict 들의 리스트. 각 item은 irsttNm(산단명), induty01~12, total 등.
    """
    key = api_key or DATA_GO_KR_API_KEY
    if not key:
        raise RuntimeError("DATA_GO_KR_API_KEY 가 설정되지 않았습니다 (.env 확인).")

    params = {
        "serviceKey": key,
        "stdrYm": stdr_ym,
        "type": "json" if want_json else "xml",
    }
    url = f"{BASE}/{operation}"
    resp = requests.get(url, params=params, timeout=15)
    return _parse(resp.text)


def diagnose(stdr_ym: str = "202403",
             operation: str = OP_MOVE_IN_BY_INDUSTRY, api_key: str = None) -> None:
    """서버 원문을 그대로 출력하는 진단 함수 (키는 마스킹)."""
    key = api_key or DATA_GO_KR_API_KEY
    if not key:
        print("DATA_GO_KR_API_KEY 가 비어 있습니다 (.env 확인).")
        return
    params = {"serviceKey": key, "stdrYm": stdr_ym, "type": "json"}
    url = f"{BASE}/{operation}"
    print("요청 URL :", url)
    print("요청 파라미터 :", {**params, "serviceKey": key[:4] + "..."})
    try:
        resp = requests.get(url, params=params, timeout=15)
    except Exception as e:
        print("연결 실패:", e)
        return
    print("HTTP 상태 :", resp.status_code)
    print("응답 본문(앞 800자) :")
    print(resp.text[:800])


def find_available(operation: str = OP_MOVE_IN_BY_INDUSTRY,
                   api_key: str = None) -> None:
    """
    최근 분기들을 훑어 데이터가 들어있는 검색년월(stdrYm)을 찾아 출력.
    (분기말 월 03/06/09/12 기준으로 최근 3년치 점검)
    """
    candidates = []
    for year in range(2025, 2021, -1):
        for mm in ("12", "09", "06", "03"):
            candidates.append(f"{year}{mm}")
    print("데이터가 있는 분기를 탐색합니다...")
    for ym in candidates:
        try:
            rows = fetch_stats(operation, ym, api_key)
        except Exception as e:
            print(f"  {ym}: 오류 {e}")
            continue
        if rows:
            print(f"  [OK] {ym}: {len(rows)}건 (사용 가능)")
            return ym
        else:
            print(f"  {ym}: 0건")
    print("최근 3년 내 데이터를 찾지 못했습니다. 다른 op를 시도해보세요.")
    return None


def _parse(text: str) -> list:
    """JSON/XML 응답에서 item 리스트 추출. 오류면 예외."""
    text = (text or "").strip()
    try:
        data = _json.loads(text)
        header = data.get("response", {}).get("header", {}) or data.get("header", {})
        code = header.get("resultCode")
        if code not in (None, "00", "0"):
            raise RuntimeError(f"API 오류 {code}: {header.get('resultMsg')}")
        body = data.get("response", {}).get("body", {}) or data.get("body", {})
        items = body.get("items", {})
        items = items.get("item", []) if isinstance(items, dict) else items
        return [items] if isinstance(items, dict) else (items or [])
    except _json.JSONDecodeError:
        pass
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise RuntimeError("응답이 JSON/XML 어느 쪽도 아닙니다. diagnose()로 원문 확인.\n"
                           + text[:300])
    reason = root.findtext(".//returnReasonCode")
    authmsg = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg")
    if reason or authmsg:
        raise RuntimeError(f"API 오류: {authmsg} (reasonCode={reason})")
    rows = []
    for item in root.findall(".//item"):
        rows.append({c.tag: c.text for c in item})
    return rows
