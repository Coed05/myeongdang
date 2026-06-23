# Render 배포 가이드 (동적 · 실시간 데이터 · Streamlit 아님)

Flask 백엔드(`api.py`)가 산단공 API로 **실시간으로 공장을 조회**하고,
화공 수식으로 등급을 계산해 프론트엔드(`web/`)에 보여줘요.
무료 파이썬 호스트 **Render**에 올립니다.

## 추가/변경된 파일
- `api.py` — Flask 백엔드 (`/` 프론트, `/api/analyze` 분석)
- `web/index.html`, `web/style.css`, `web/app.js` — 프론트엔드
- `Procfile`, `render.yaml` — 배포 설정
- `requirements.txt` — flask·gunicorn 추가

## 배포 순서

**1. GitHub에 올리기**
기존 `myeongdang` 저장소에 위 파일들(특히 `api.py`, `web/` 폴더, `Procfile`,
`render.yaml`, 수정된 `requirements.txt`)을 **Add file → Upload files**로 올려요.
(`web` 폴더는 폴더째 드래그)

**2. Render 가입 & 서비스 생성**
1. [render.com](https://render.com) → GitHub로 가입
2. **New + → Web Service** → `myeongdang` 저장소 선택
3. 설정 (render.yaml 있으면 자동 인식):
   - Runtime: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn api:app --timeout 300 --workers 1`
   - Instance Type: **Free**

**3. 환경변수(Environment) 등록**
Render의 **Environment** 탭에서 키 추가 (Streamlit Secrets와 같은 값):
```
VWORLD_API_KEY     = 978C22B2-...      (브이월드 키)
DATA_GO_KR_API_KEY = 9796ba...         (산단공 키)
KMA_API_KEY        = 9796ba...
VWORLD_REFERER     = https://myeongdang.streamlit.app
```
> `VWORLD_REFERER`는 브이월드에 **등록된 도메인**과 같으면 돼요(헤더 값만 맞으면
> 통과). 이미 `myeongdang.streamlit.app`을 등록해 두었으니 그대로 쓰면 됩니다.

**4. Deploy**
배포되면 `https://ansim-myeongdang.onrender.com` 같은 **공개 주소**가 생겨요.

## 사용 시 참고
- **첫 분석은 1~2분** 걸려요(인근 단지 공장 수백 곳 주소를 실시간 변환). 같은 단지는
  서버 메모리에 캐시돼서 이후엔 빨라요. Render 무료는 15분 미사용 시 잠들어서 다음
  접속 시 30초쯤 깨어나는 시간도 있어요.
- 공장 데이터는 **한국산업단지공단 실시간 API** — 가짜/샘플 아님.
- 브이월드가 막혀도 주소 변환은 **OSM(키 불필요)** 으로 자동 폴백돼요.

## 로컬에서 먼저 테스트
```
pip install -r requirements.txt
python api.py
```
→ 브라우저에서 `http://localhost:8000`
