# -*- coding: utf-8 -*-
"""
prefetch.py — 공장 데이터 '사전 수집' 스크립트 (로컬에서 한 번만 실행)

이 작업공간(클라우드)에서는 산단공·카카오 API가 차단돼 실행할 수 없습니다.
반드시 내 컴퓨터(api.py 가 정상 동작하는 그 환경)에서 실행하세요.

  py prefetch.py      (또는 python prefetch.py)

동작:
  - complexes.py 의 전국 산업단지를 하나씩 산단공 API로 조회
  - 주소를 좌표로 변환(지오코딩)까지 끝낸 뒤
  - factories_prefetched.csv 한 파일로 저장 (이 스크립트와 같은 폴더)

견고성:
  - 단지 하나 끝날 때마다 '중간 저장' → 도중에 멈춰도 데이터 보존
  - 다시 실행하면 이미 끝낸 단지는 건너뛰고 '이어서' 진행
  - 저장 폴더를 따로 만들지 않음(OneDrive 빈 폴더 삭제 문제 회피)

이렇게 만든 CSV 를 GitHub 에 올리면 배포 서버(Render)는 실시간 API·지오코딩
없이 이 파일만 읽어 → OOM 없음 + 즉시 응답. (데이터는 산단공 실제 데이터 스냅샷)
"""

import os
import sys
import time

import pandas as pd

from complexes import INDUSTRIAL_COMPLEXES
from factories import fetch_and_geocode

# 단지별 최대 수집 공장 수(대형 단지도 이 수까지만). 더 빨리 끝내려면 줄이세요.
MAX_ROWS_PER_COMPLEX = 1500

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(SCRIPT_DIR, "factories_prefetched.csv")


def _dedup(df):
    subset = [c for c in ["회사명", "주소"] if c in df.columns]
    if subset:
        df = df.drop_duplicates(subset=subset).reset_index(drop=True)
    return df


def _save(all_dfs):
    """누적 데이터를 CSV로 저장. OneDrive 잠금 등 실패 시 예외를 올림."""
    merged = _dedup(pd.concat(all_dfs, ignore_index=True))
    merged.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    return len(merged)


def main():
    total = len(INDUSTRIAL_COMPLEXES)
    all_dfs = []
    done = set()

    # 이전에 만들다 만 결과가 있으면 이어서 진행
    if os.path.exists(OUT_CSV):
        try:
            prev = pd.read_csv(OUT_CSV, encoding="utf-8-sig")
            if "단지" in prev.columns and not prev.empty:
                all_dfs.append(prev)
                done = set(prev["단지"].dropna().unique())
                print(f"이전 진행분 발견: 단지 {len(done)}곳, 공장 {len(prev)}개 → 이어서 진행\n")
        except Exception as e:
            print(f"(이전 파일 읽기 실패, 처음부터 진행: {e})\n")

    print(f"전국 산업단지 {total}곳 사전 수집 시작\n" + "=" * 50)
    ok, empty = len(done), 0
    for i, c in enumerate(INDUSTRIAL_COMPLEXES, 1):
        name = c["name"]
        if name in done:
            print(f"\n[{i}/{total}] {name} — 이미 완료, 건너뜀")
            continue
        print(f"\n[{i}/{total}] {name} ({c.get('region','')}) 수집 중...")
        t0 = time.time()
        try:
            df = fetch_and_geocode(name, max_rows=MAX_ROWS_PER_COMPLEX,
                                   cache_path=None)
        except Exception as e:
            print(f"  ! 실패(건너뜀): {e}")
            empty += 1
            continue
        if df is None or df.empty:
            print("  - 등록 공장 없음(또는 단지명 불일치) → 건너뜀")
            empty += 1
            continue
        df = df.copy()
        df["단지"] = name
        all_dfs.append(df)
        ok += 1
        print(f"  ✓ 공장 {len(df)}개 (좌표 확보), {time.time()-t0:.1f}초")
        # 중간 저장: 단지마다 누적본을 파일로 — 도중에 멈춰도 보존됨
        try:
            n = _save(all_dfs)
            print(f"    💾 중간 저장 완료 (누적 공장 {n}개)")
        except Exception as e:
            print(f"    (중간 저장 실패, 계속 진행: {e})")

    if not all_dfs:
        print("\n수집된 데이터가 없습니다. 키·네트워크를 확인하세요.")
        sys.exit(1)

    try:
        n = _save(all_dfs)
    except Exception as e:
        # 최후 폴백: 홈 폴더에 저장
        alt = os.path.join(os.path.expanduser("~"), "factories_prefetched.csv")
        _dedup(pd.concat(all_dfs, ignore_index=True)).to_csv(
            alt, index=False, encoding="utf-8-sig")
        print(f"\n[주의] 원래 위치 저장 실패({e}).\n  대신 여기에 저장했어요: {alt}")
        print("  이 파일을 ansim_myeongdang 폴더로 옮겨주세요.")
        return

    print("\n" + "=" * 50)
    print(f"완료! 데이터 있는 단지 {ok}곳 / 비어있음 {empty}곳")
    print(f"총 공장 {n}개 → 저장: {OUT_CSV}")
    print("\n이제 factories_prefetched.csv 를 GitHub 에 올리세요.")


if __name__ == "__main__":
    main()
