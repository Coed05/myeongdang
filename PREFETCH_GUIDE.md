# 공장 데이터 사전수집 → 배포 안내

서버가 요청마다 공장 주소를 실시간 변환(지오코딩)하던 걸 **미리 한 번만** 해서
파일로 저장합니다. 그러면 Render 서버는 그 파일만 읽어 → **OOM 없음 + 즉시 응답**.
데이터는 산단공 **실제 데이터**의 스냅샷입니다(가짜 아님).

> 이 작업공간(클라우드)에서는 산단공·카카오 API가 차단돼 실행 불가.
> **반드시 내 컴퓨터**(`python api.py` 가 잘 되던 그 환경)에서 실행하세요.

---

## 1단계 — 로컬에서 사전수집 실행 (한 번만)

프로젝트 폴더에서 터미널을 열고:

```bash
cd ansim_myeongdang
py prefetch.py
```

- 전국 산업단지 34곳을 하나씩 조회 + 좌표 변환 (전체 ~40분)
- **단지마다 중간 저장**되니 도중에 멈춰도 데이터가 보존됩니다
- 다시 실행하면 끝낸 단지는 건너뛰고 **이어서** 진행해요
- 끝나면 `factories_prefetched.csv` 가 prefetch.py 옆에 생깁니다
- 화면에 `총 공장 NNNN개 → 저장` 이 뜨면 성공

## 2단계 — GitHub에 올리기

바뀐/새 파일을 `myeongdang` 저장소에 올립니다:

- `ansim_myeongdang/factories.py`  (사전수집 우선 로직)
- `ansim_myeongdang/api.py`        (메모리 캡 + 오류 핸들러)
- `ansim_myeongdang/prefetch.py`   (수집 스크립트)
- `ansim_myeongdang/factories_prefetched.csv`  ← **핵심 데이터 파일**

폴더째 드래그앤드롭으로 덮어쓰면 한 번에 됩니다.

## 3단계 — Render 자동 재배포

올리면 Render가 2~3분간 자동 재배포해요. 끝나면 **안산 반월동** 등으로 분석 →
이번엔 OOM(502) 없이 바로 결과가 나옵니다.

---

## 갱신하고 싶을 때

공장 정보를 최신화하려면 `python prefetch.py` 를 다시 실행하고
새 `data/factories_prefetched.csv` 를 커밋하면 됩니다. (자주 안 해도 됩니다)

## 동작 방식 (참고)

- `factories.py` 는 `data/factories_prefetched.csv` 가 있으면 그걸 우선 사용
- 파일에 없는 단지가 잡히면 자동으로 기존 라이브 API 수집으로 폴백
- 즉, 사전수집 파일이 없어도 앱은 그대로 작동(느릴 뿐)
