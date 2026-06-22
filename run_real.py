# -*- coding: utf-8 -*-
"""
run_real.py — 실제 공공데이터로 전체 파이프라인 1회 실행

흐름:
  1) 아파트 주소 -> 브이월드 지오코딩 -> 좌표
  2) 산업단지 공장목록(산단공 API) -> 주소 지오코딩 -> 좌표 (캐시)
  3) 5km 반경 필터 -> 소음/악취 수식 -> 종합 안심 등급

실행 예:
  python run_real.py
  python run_real.py "울산광역시 남구 야음동 1234" "울산미포국가산업단지"
"""

import sys

from geocoding import geocode
from factories import fetch_and_geocode
from pipeline import run_assessment, print_report

# 기본값 (인자 없이 실행할 때)
DEFAULT_ADDRESS = "울산광역시 남구 야음동"
DEFAULT_COMPLEX = "울산미포국가산업단지"
# 단지 전체 공장 수집 상한. 대형 배출원까지 포함하려면 넉넉히.
# 첫 실행은 주소 지오코딩 때문에 수 분 걸리지만, 캐시되어 다음부터는 즉시.
DEFAULT_MAX = 1500


def main():
    address = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDRESS
    complex_name = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_COMPLEX

    print(f"[1/3] 아파트 주소 지오코딩: {address}")
    apt_lat, apt_lon = geocode(address)
    if apt_lat is None:
        print("  아파트 주소 좌표 변환 실패. 주소를 더 구체적으로 입력해 보세요.")
        return
    print(f"      -> ({apt_lat:.5f}, {apt_lon:.5f})")

    print(f"[2/3] 공장목록 전체 수집 + 지오코딩: {complex_name} (상한 {DEFAULT_MAX})")
    print("      (첫 실행은 수 분 걸릴 수 있고, 이후엔 캐시로 즉시 실행됩니다)")
    cache = f"factory_cache_{complex_name}.csv"
    factory_df = fetch_and_geocode(complex_name, max_rows=DEFAULT_MAX,
                                   cache_path=cache)
    if factory_df.empty:
        print("  공장 데이터를 가져오지 못했습니다. 산업단지명을 확인하세요.")
        return
    print(f"      -> 좌표 확보 공장 {len(factory_df)}개")

    print(f"[3/3] 5km 필터 + 화공 수식 + 등급 산출")
    report = run_assessment(
        address=address,
        factory_df=factory_df,
        apt_coords=(apt_lat, apt_lon),
        use_live_weather=False,   # 기상청 키 없으면 기본 바람값 사용
        is_daytime=True,
    )
    print()
    print_report(report)


if __name__ == "__main__":
    main()
