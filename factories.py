# -*- coding: utf-8 -*-
"""
factories.py — 공장 데이터 수집 및 5km 반경 필터링

[함수 2] 역할분담 문서의 'filter_nearby_factories' 에 대응.
산단공 입주기업 데이터(API 또는 엑셀)에서 아파트 반경 5km 이내 공장만 골라
하버사인 거리를 계산해 반환합니다.

산단공 입주기업 현황 API는 좌표를 직접 제공하지 않는 경우가 많아,
(1) 좌표가 있으면 그대로 사용하고
(2) 없으면 주소를 브이월드로 지오코딩하는 폴백을 지원합니다.
"""

import hashlib
import json as _json
import re as _re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

import os

from config import DATA_GO_KR_API_KEY, SEARCH_RADIUS_KM
from geo import haversine_km
from geocoding import geocode, clean_address

# 한국산업단지공단 공장등록정보 조회 서비스 (B550624)
# getFctryListInIrsttService_v2 : 산업단지명으로 해당 단지의 등록공장 목록 조회
SANDAN_URL = ("https://apis.data.go.kr/B550624/fctryRegistInfo/"
              "getFctryListInIrsttService_v2")

# 산업단지명을 담는 요청 파라미터 이름 (Swagger 명세 확인됨).
COMPLEX_PARAM = "irsttNm"


# ---------------------------------------------------------------------------
# 데이터 로더
# ---------------------------------------------------------------------------
def load_factories_from_csv(path: str) -> pd.DataFrame:
    """
    로컬 CSV/엑셀에서 공장 목록 로드.
    필수 컬럼: 회사명, 업종코드, 위도, 경도
    """
    if path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    return _normalize_columns(df)


def _build_params(industrial_complex, key, num_rows, page, return_json):
    return {
        "serviceKey": key,
        "pageNo": page,
        "numOfRows": num_rows,
        "type": "json" if return_json else "xml",
        COMPLEX_PARAM: industrial_complex,
    }


def diagnose_api(industrial_complex: str = "울산미포국가산업단지",
                 api_key: str = None) -> None:
    """
    실제 서버가 무엇을 돌려주는지 그대로 출력하는 진단 함수.
    (키 활성화 오류인지, 파라미터 이름 문제인지 바로 확인용)
    """
    key = api_key or DATA_GO_KR_API_KEY
    if not key:
        print("DATA_GO_KR_API_KEY 가 비어 있습니다 (.env 확인).")
        return
    params = _build_params(industrial_complex, key, 5, 1, True)
    safe = {k: (v if k != "serviceKey" else v[:4] + "...") for k, v in params.items()}
    print("요청 URL :", SANDAN_URL)
    print("요청 파라미터 :", safe)
    try:
        resp = requests.get(SANDAN_URL, params=params, timeout=15)
    except Exception as e:
        print("연결 실패:", e)
        return
    print("HTTP 상태 :", resp.status_code)
    print("응답 본문(앞 800자) :")
    print(resp.text[:800])


def load_factories_from_api(industrial_complex: str,
                            api_key: str = None,
                            max_rows: int = 2000,
                            per_page: int = 100) -> pd.DataFrame:
    """
    산단공 API에서 특정 산업단지의 등록공장 '전체'를 페이지네이션으로 수집.
    (회사명 가나다순 한 페이지만 받으면 대형 배출원이 누락되므로 여러 페이지를 받음)
    좌표가 없으므로 주소를 지오코딩하되, 같은 주소는 한 번만 호출(중복 제거).

    max_rows : 안전 상한(이 수만큼 모으면 중단)
    per_page : 페이지당 요청 수
    """
    key = api_key or DATA_GO_KR_API_KEY
    if not key:
        raise RuntimeError("DATA_GO_KR_API_KEY 가 설정되지 않았습니다 (.env 확인).")

    all_items = []
    page = 1
    while len(all_items) < max_rows:
        params = _build_params(industrial_complex, key, per_page, page, True)
        resp = requests.get(SANDAN_URL, params=params, timeout=15)
        items = _parse_items(resp.text)
        if not items:
            break
        all_items.extend(items)
        print(f"  공장목록 수신 {len(all_items)}개 (page {page})")
        if len(items) < per_page:    # 마지막 페이지
            break
        page += 1

    df = _normalize_columns(pd.DataFrame(all_items))
    if df.empty:
        return df
    _geocode_inplace(df)
    return df.dropna(subset=["위도", "경도"]).reset_index(drop=True)


def _geocode_inplace(df: pd.DataFrame, workers: int = 8) -> None:
    """df의 '주소'를 지오코딩해 위/경도를 채움.
    동일 주소는 1회만, 그리고 여러 주소를 '병렬'로 호출해 속도를 높임."""
    if "주소" not in df.columns:
        return
    need = df[df["위도"].isna()]
    # 중복 제거: 정제한 주소 목록
    addrs = list({clean_address(str(a))
                  for a in need["주소"].dropna() if str(a).strip()})
    print(f"  지오코딩 고유주소 {len(addrs)}개 (전체 {len(need)}건, 병렬 {workers})")

    results = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(geocode, a): a for a in addrs}
        for fut in as_completed(futs):
            a = futs[fut]
            try:
                results[a] = fut.result()
            except Exception:
                results[a] = (None, None)
            done += 1
            if done % 50 == 0:
                print(f"  지오코딩 {done}/{len(addrs)} ...")

    # 매핑 반영
    for idx, row in need.iterrows():
        if pd.isna(row.get("주소")):
            continue
        lat, lon = results.get(clean_address(str(row["주소"])), (None, None))
        df.at[idx, "위도"] = lat
        df.at[idx, "경도"] = lon


def _safe_cache_path(path: str) -> str:
    """한글 등 비ASCII 파일명을 Windows에서 안전한 ASCII 이름으로 변환.
    원본 이름의 짧은 해시를 붙여 산업단지별로 구분되게 함."""
    folder, fname = os.path.split(path)
    base, ext = os.path.splitext(fname)
    h = hashlib.md5(base.encode("utf-8")).hexdigest()[:8]
    ascii_base = _re.sub(r"[^A-Za-z0-9._-]", "", base) or "cache"
    return os.path.join(folder, f"{ascii_base}_{h}{ext or '.csv'}")


def fetch_and_geocode(industrial_complex: str, max_rows: int = 1500,
                      cache_path: str = None, api_key: str = None) -> pd.DataFrame:
    """
    산업단지 공장 '전체'를 받아 좌표까지 채운 DataFrame 반환.
    cache_path 를 주면 한 번 지오코딩한 결과를 CSV로 저장/재사용해
    중복 호출과 브이월드 쿼터 낭비를 막습니다. (파일명은 ASCII로 안전화)
    """
    targets = _cache_targets(cache_path) if cache_path else []
    # 읽기: 후보 위치 중 존재하는 캐시를 사용
    for t in targets:
        if os.path.exists(t):
            print(f"캐시 사용: {t}")
            return load_factories_from_csv(t)
    df = load_factories_from_api(industrial_complex, api_key, max_rows)
    # 쓰기: 후보 위치에 순서대로 저장 시도 (cwd·OneDrive 문제 회피)
    if targets and not df.empty:
        for t in targets:
            try:
                df.to_csv(t, index=False, encoding="utf-8-sig")
                print(f"캐시 저장: {t} ({len(df)}개 공장)")
                break
            except Exception as e:
                print(f"(캐시 저장 실패, 다음 위치 시도: {e})")
    return df


def _cache_targets(cache_path: str) -> list:
    """캐시 후보 절대경로 목록: [스크립트 폴더, 시스템 임시폴더]."""
    import tempfile
    fname = os.path.basename(_safe_cache_path(cache_path))
    here = os.path.dirname(os.path.abspath(__file__))
    return [os.path.join(here, fname),
            os.path.join(tempfile.gettempdir(), fname)]


# ---------------------------------------------------------------------------
# 사전수집(prefetch) 데이터 — 있으면 API/지오코딩 없이 이 파일만 읽음
# ---------------------------------------------------------------------------
_PREFETCHED = None   # {단지명: DataFrame} 캐시 (서버 기동 후 1회 로드)

PREFETCH_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "factories_prefetched.csv")


def _load_prefetched():
    """data/factories_prefetched.csv 를 {단지명: df} 로 1회 로드(메모리 캐시).
    파일이 없으면 None 을 반환해 라이브 수집으로 폴백한다."""
    global _PREFETCHED
    if _PREFETCHED is not None:
        return _PREFETCHED
    if not os.path.exists(PREFETCH_CSV):
        _PREFETCHED = {}
        return _PREFETCHED
    try:
        df = pd.read_csv(PREFETCH_CSV, encoding="utf-8-sig")
        df = _normalize_columns(df)
        if "단지" not in df.columns:
            _PREFETCHED = {}
            return _PREFETCHED
        _PREFETCHED = {name: g.reset_index(drop=True)
                       for name, g in df.groupby("단지")}
        print(f"[prefetch] 사전수집 데이터 로드: 단지 {len(_PREFETCHED)}곳, "
              f"공장 {len(df)}개")
    except Exception as e:
        print(f"[prefetch] 로드 실패(라이브로 폴백): {e}")
        _PREFETCHED = {}
    return _PREFETCHED


def fetch_near_apartment(apt_lat: float, apt_lon: float,
                         max_complex_km: float = 15.0,
                         max_rows: int = 1500,
                         api_key: str = None,
                         max_complexes: int = 3,
                         max_total: int = 1200,
                         use_prefetched: bool = True):
    """
    아파트 주변 산업단지를 '자동 탐지'해 그 단지들의 공장을 모두 합쳐 반환.
    (사용자가 산업단지명을 몰라도 주소만으로 인근 공장이 수집됨)

    use_prefetched : True 면 사전수집 CSV 우선(빠름·OOM 없음),
                     False 면 항상 산단공 API 실시간 수집(최신·느림).
    max_complexes  : 가장 가까운 단지 N곳까지만 처리 (서버 과부하 방지)
    max_total      : 누적 공장 수가 이 값에 도달하면 중단

    반환: (factory_df, used_complexes)
    """
    from complexes import nearby_complexes

    pre = _load_prefetched() if use_prefetched else {}
    cands = nearby_complexes(apt_lat, apt_lon, max_complex_km)[:max_complexes]
    frames, used, total = [], [], 0
    for c in cands:
        if total >= max_total:
            break
        # 1) 사전수집 데이터 우선(즉시·무지오코딩)
        if pre and c["name"] in pre:
            df = pre[c["name"]]
            src = "사전수집"
        else:
            # 2) 폴백: 라이브 API 수집(+지오코딩)
            try:
                df = fetch_and_geocode(c["name"], max_rows=max_rows,
                                       cache_path=f"factory_cache_{c['name']}.csv",
                                       api_key=api_key)
                src = "라이브"
            except Exception as e:
                print(f"  ({c['name']} 조회 실패, 건너뜀: {e})")
                continue
        if df is not None and not df.empty:
            frames.append(df)
            used.append({**c, "factory_count": len(df)})
            total += len(df)
            print(f"  [단지/{src}] {c['name']} ({c['dist_km']}km): 공장 {len(df)}개")

    if not frames:
        return pd.DataFrame(columns=["회사명", "업종코드", "위도", "경도"]), []

    merged = pd.concat(frames, ignore_index=True)
    # 회사명+주소(없으면 좌표)로 중복 제거
    subset = [col for col in ["회사명", "주소"] if col in merged.columns]
    if not subset:
        subset = ["위도", "경도"]
    merged = merged.drop_duplicates(subset=subset).reset_index(drop=True)
    return merged, used


def _parse_items(text: str):
    """응답 텍스트(JSON 또는 XML)에서 item 리스트 추출. 오류면 예외."""
    text = (text or "").strip()
    # 1) JSON 시도
    try:
        data = _json.loads(text)
        header = (data.get("response", {}).get("header", {}))
        code = header.get("resultCode")
        if code not in (None, "00", "0"):
            raise RuntimeError(f"API 오류 {code}: {header.get('resultMsg')}")
        items = (data.get("response", {}).get("body", {})
                     .get("items", {}))
        items = items.get("item", []) if isinstance(items, dict) else items
        return [items] if isinstance(items, dict) else (items or [])
    except _json.JSONDecodeError:
        pass
    # 2) XML 시도 (정상 또는 에러봉투)
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise RuntimeError("서버 응답이 JSON/XML 어느 쪽도 아닙니다. "
                           "diagnose_api() 로 원문을 확인하세요.\n원문 앞부분: "
                           + text[:300])
    # 데이터포털 표준 에러봉투
    reason = root.findtext(".//returnReasonCode")
    authmsg = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg")
    if reason or authmsg:
        raise RuntimeError(f"API 오류: {authmsg} (reasonCode={reason})")
    rows = []
    for item in root.findall(".//item"):
        rows.append({child.tag: child.text for child in item})
    return rows


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """다양한 컬럼명을 표준(회사명/업종코드/위도/경도/주소)으로 정규화."""
    alias = {
        "회사명": ["회사명", "cmpnyNm", "기업체명", "업체명", "company",
                "factory_name", "name"],
        # 업종코드 = '숫자' KSIC (핵심 3업종 매칭용). 대표업종코드 우선.
        "업종코드": ["업종코드", "rprsntvIndutyCode", "indutyCodes", "KSIC",
                 "ksic", "ksic_code", "표준산업분류코드"],
        # 업종명 = indutyNm (표시·보조 매칭용)
        "업종명": ["업종명", "indutyNm"],
        # 고용인원 = allEmplyCo (Q 면적가중 대용치)
        "고용": ["고용", "allEmplyCo", "고용인원"],
        "위도": ["위도", "lat", "latitude", "y"],
        "경도": ["경도", "lon", "lng", "longitude", "x"],
        "주소": ["주소", "rnAdres", "소재지", "address", "도로명주소", "지번주소",
               "lnmAdres"],
    }
    rename = {}
    lower_cols = {c.lower(): c for c in df.columns}
    for std, names in alias.items():
        for n in names:
            if n in df.columns:
                rename[df.columns[list(df.columns).index(n)]] = std
                break
            if n.lower() in lower_cols:
                rename[lower_cols[n.lower()]] = std
                break
    df = df.rename(columns=rename)
    # 누락 컬럼 보강
    for col in ["회사명", "업종코드", "업종명", "고용", "위도", "경도"]:
        if col not in df.columns:
            df[col] = pd.NA
    # 숫자형 변환
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# 5km 반경 필터 + 거리 계산
# ---------------------------------------------------------------------------
def filter_nearby_factories(apt_lat, apt_lon, factory_df,
                            radius_km=SEARCH_RADIUS_KM) -> pd.DataFrame:
    """
    아파트 좌표 기준 radius_km 이내 공장만 추려 거리(km)와 함께 반환.

    반환 컬럼: factory_name, ksic_code, industry_name, employees,
              lat, lon, distance_km  (distance_km 오름차순 정렬)
    """
    rows = []
    for _, r in factory_df.iterrows():
        f_lat, f_lon = r["위도"], r["경도"]
        if pd.isna(f_lat) or pd.isna(f_lon):
            continue
        dist = haversine_km(apt_lat, apt_lon, f_lat, f_lon)
        if dist <= radius_km:
            rows.append({
                "factory_name": r.get("회사명"),
                "ksic_code": r.get("업종코드"),
                "industry_name": r.get("업종명"),
                "employees": r.get("고용"),
                "lat": f_lat,
                "lon": f_lon,
                "distance_km": round(dist, 4),
            })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("distance_km").reset_index(drop=True)
    return out
