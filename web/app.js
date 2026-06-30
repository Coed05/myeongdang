/* 프론트엔드 — Flask 백엔드(/api/analyze)를 호출해 실시간 결과를 렌더 */

const GRADE_COLOR = { AAA:"#1a9850", AA:"#66bd63", A:"#a6d96a", B:"#f9d057", C:"#fdae61", D:"#f46d43", E:"#d73027", F:"#a50026" };
const GRADE_DESC = { AAA:"최상 · 매우 안전", AA:"우수", A:"양호", B:"보통", C:"주의", D:"미흡", E:"나쁨", F:"매우 나쁨" };
const GRADE_VERDICT = {
  AAA: "소음·악취 영향이 거의 없는 매우 안전한 지역이에요.",
  AA:  "소음·악취 영향이 적어 쾌적한 편이에요.",
  A:   "대체로 양호해요. 약간의 영향은 있을 수 있어요.",
  B:   "보통 수준이에요. 가까운 배출원을 확인해 보세요.",
  C:   "주의가 필요해요. 소음·악취 영향이 다소 있어요.",
  D:   "영향이 큰 편이에요. 신중히 검토하세요.",
  E:   "소음·악취 영향이 커요. 권장하지 않아요.",
  F:   "영향이 매우 커요. 거주에 부적합할 수 있어요.",
};
const TIP = {
  noise: "반경 내 모든 공장의 소음을 거리에 따른 역자승 감쇄로 계산해 로그로 합산한 값이에요. 환경부 주거지역 기준은 주간 55dB · 야간 45dB.",
  odor:  "핵심 배출원의 악취를 2차원 가우스 확산식으로 계산해 합산한 농도예요. OU는 '냄새가 안 느껴질 때까지 희석한 배수'로, 낮을수록 좋아요.",
  core:  "반경 내 공장 중 소음·악취가 큰 3대 핵심 업종(화학 · 고무·플라스틱 · 금속가공) 수 / 전체 공장 수예요.",
  wind:  "분석에 적용한 풍속(m/s)과 바람이 불어오는 방향(°), 대기안정도 등급이에요. 오염물질이 퍼지는 방향을 결정해요.",
  grade: "AAA(최상)부터 F(매우 나쁨)까지 8단계. 소음·악취 점수를 가중 합산해 매겨요.",
};
const ic = (t) => `<span class="info" data-tip="${t}">i</span>`;
const FX = {
  odor: "굴뚝에서 나온 악취가 바람을 타고 퍼질 때의 농도 C예요. 풍하거리 x가 멀수록, 바람 축에서 옆으로(y) 벗어날수록 농도가 급격히 낮아져요. σy·σz는 대기 안정도에 따른 좌우·상하 확산 폭(Martin 계수)이에요.",
  noise: "1m 거리의 소음(SPL₁)이 거리 r₂만큼 멀어지며 줄어드는 양을 구하고(역자승 감쇄), 여러 공장의 소음을 에너지 기준으로 로그 합산해 총 소음을 계산해요.",
};
const CORE_COLOR = { C20:"#dc2626", C22:"#ea580c", C25:"#2563eb" };
const CORE_LABEL = { C20:"화학·석유화학", C22:"고무·플라스틱", C25:"금속가공·기계" };
const DEG = Math.PI / 180;
const COMPASS16 = ["북","북북동","북동","동북동","동","동남동","남동","남남동","남","남남서","남서","서남서","서","서북서","북서","북북서"];
function windDir(deg) { return COMPASS16[Math.round((((+deg % 360) + 360) % 360) / 22.5) % 16]; }

let MAP = null, MAP_TIMERS = [];
function downwind(lat, lon, fromDeg, km = 1.5) {
  const g = ((fromDeg + 180) % 360) * DEG;
  return [lat + (km / 110.54) * Math.cos(g), lon + (km / (111.32 * Math.cos(lat * DEG))) * Math.sin(g)];
}
function drawMap(rep) {
  MAP_TIMERS.forEach(clearTimeout); MAP_TIMERS = [];   // 이전 분석의 지연 타이머 정리
  if (MAP) { MAP.remove(); MAP = null; }
  MAP = L.map("map").setView([rep.aptLat, rep.aptLon], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(MAP);
  const color = GRADE_COLOR[rep.grade] || "#888";
  // 반경 원 — 점선·굵은 테두리로 또렷하게
  const circle = L.circle([rep.aptLat, rep.aptLon], { radius: rep.radiusKm * 1000, color: "#1d4ed8",
    weight: 3, opacity: 0.9, dashArray: "10 8", fillColor: "#3b82f6", fillOpacity: 0.07 }).addTo(MAP);
  L.circleMarker([rep.aptLat, rep.aptLon], { radius: 7, color: "#1d4ed8", weight: 2,
    fillColor: "#fff", fillOpacity: 1 }).addTo(MAP);
  L.marker([rep.aptLat, rep.aptLon]).bindTooltip("검색 아파트", { permanent: false }).addTo(MAP);
  const wp = downwind(rep.aptLat, rep.aptLon, rep.wind.fromDeg);
  L.polyline([[rep.aptLat, rep.aptLon], wp], { color: "#2563eb", weight: 3, opacity: 0.7 }).bindTooltip("바람 방향").addTo(MAP);
  for (const f of rep.nearby) {
    const col = f.core ? CORE_COLOR[f.core] : "#9ca3af", rad = f.core ? 6 : 3;
    L.circleMarker([f.lat, f.lon], { radius: rad, color: col, fillColor: col, fillOpacity: f.core ? 0.85 : 0.5, weight: 1 })
      .bindTooltip(`${f.factory_name} · ${f.industry_name || ""} · ${f.distance_km}km`).addTo(MAP);
  }
  // 핀+반경이 화면의 ~80%로 보이도록 맞춤(중심·반경으로 직접 범위 계산 — 투영 의존 X)
  // 박스 한 변 = 반경×2.5 → 지름(반경×2)이 약 80% 차지. 이후 확대·축소·이동 자유.
  const bounds = L.latLng(rep.aptLat, rep.aptLon).toBounds(rep.radiusKm * 2500);
  const fit = () => { if (!MAP) return; MAP.invalidateSize(); MAP.fitBounds(bounds); };
  MAP_TIMERS.push(setTimeout(fit, 250), setTimeout(fit, 600));
}

function renderResult(rep, targetId) {
  const TGT = targetId || "result";
  const color = GRADE_COLOR[rep.grade] || "#888";
  const chips = (rep.complexes || []).map(c => `<span class="chip">${c.name} · ${c.dist} km</span>`).join(" ");
  const rows = rep.nearby.map(f => `<tr><td>${f.core ? CORE_LABEL[f.core] : "-"}</td><td>${f.factory_name}</td><td>${f.industry_name || ""}</td><td style="text-align:right">${(+f.distance_km).toFixed(2)} km</td></tr>`).join("");
  const detRows = (rep.detail || []).map(d => `<tr><td>${d.name}</td><td>${d.label}</td><td>${d.r2}</td><td>${d.x}</td><td>${d.y}</td><td>${d.sy}</td><td>${d.sz}</td><td>${d.Q}</td><td>${d.C}</td><td>${d.spl2}</td></tr>`).join("");
  const back = TGT === "detail" ? `<a class="back-link" href="#detail" onclick="backToList(event)">← 동네 아파트 목록으로</a>` : "";
  const ng = rep.noiseGrade ? `${rep.noiseGrade} · ` : "";
  const og = rep.odorGrade ? `${rep.odorGrade} · ` : "";

  document.getElementById(TGT).innerHTML = back + `
    <div class="badge" style="--c:${color}">
      <div class="grade">${rep.grade}</div>
      <div class="badge-info">
        <div class="muted">종합 안심 주거 등급 ${ic(TIP.grade)}</div>
        <div class="score">${rep.composite}<span> / 100점</span></div>
        <div class="verdict">${GRADE_VERDICT[rep.grade] || ""}</div>
        <div class="muted small">${rep.address}</div>
      </div>
    </div>
    ${chips ? `<div class="complexes"><b>자동 탐지된 산업단지</b> &nbsp;${chips}</div>` : ""}
    ${rep.note ? `<div class="note" style="background:#fffbeb;color:#92722a;">ℹ️ ${rep.note}</div>` : ""}
    ${rep.aiSummary ? `<div class="ai-box"><div class="ai-head"><span class="ai-badge">AI 요약</span> 왜 ${rep.grade}등급일까요?</div><div class="ai-body">${rep.aiSummary}</div></div>` : ""}
    <div class="metrics">
      <div class="metric"><div class="m-label">누적 소음 ${ic(TIP.noise)}</div><div class="m-val">${rep.noiseDb}<span class="unit">dB</span></div><div class="m-sub">${ng}${rep.noiseScore}점</div></div>
      <div class="metric"><div class="m-label">누적 악취 ${ic(TIP.odor)}</div><div class="m-val">${rep.odorOu}<span class="unit">OU</span></div><div class="m-sub">${og}${rep.odorScore}점</div></div>
      <div class="metric"><div class="m-label">핵심 배출원 / 반경내 ${ic(TIP.core)}</div><div class="m-val">${rep.coreCount} / ${rep.nearby.length}</div><div class="m-sub">3대 핵심 업종</div></div>
      <div class="metric"><div class="m-label">바람 ${ic(TIP.wind)}</div><div class="m-val">${rep.wind.speed}<span class="unit">m/s</span></div><div class="m-sub">${windDir(rep.wind.fromDeg)} ${rep.wind.fromDeg}° / ${rep.wind.stab}등급</div></div>
    </div>
    <div class="two-col">
      <div><div id="map"></div></div>
      <div class="result-right">
        <h3>반경 내 공장 ${rep.nearby.length}개</h3>
        <div class="legend"><span style="color:#dc2626">●</span> 화학 <span style="color:#ea580c">●</span> 플라스틱 <span style="color:#2563eb">●</span> 금속 <span style="color:#9ca3af">●</span> 비배출원</div>
        <div class="table-wrap"><table><thead><tr><th>핵심</th><th>회사명</th><th>업종</th><th style="text-align:right">거리</th></tr></thead><tbody>${rows}</tbody></table></div>
      </div>
    </div>
    <details class="adv"><summary>📚 분석 방법론 · 세부 계산식</summary>
      <p class="adv-p"><b>왜 시뮬레이션인가?</b> 공장의 실시간 배출량은 영업비밀이라 공개되지 않아요. 정부 공인 '배출 원단위 가중치'와 '물리적 소음 표준'을 공인 화공 수식에 대입해요.</p>
      <p class="adv-p"><b>3대 핵심 배출 업종</b> — 화학(C20) Q=100·85dB / 고무·플라스틱(C22) 60·80dB / 금속가공(C25) 15·95dB</p>
      <div class="fxhead"><b>악취 — 2차원 가우스 확산</b> <span class="muted small">· 수식에 마우스를 올리면 설명이 떠요</span></div>
      <div class="fx" data-tip="${FX.odor}">$$C=\\dfrac{Q}{\\pi\\,u\\,\\sigma_y\\,\\sigma_z}\\,\\exp\\!\\left(-\\dfrac{y^2}{2\\sigma_y^2}\\right)\\exp\\!\\left(-\\dfrac{H^2}{2\\sigma_z^2}\\right),\\quad \\sigma_y=a\\,x^{b},\\ \\sigma_z=c\\,x^{d}+f$$</div>
      <p class="adv-p muted small">악취는 그날의 풍향이 아니라 <b>8방위 바람장미 평균</b>(연중 노출)으로 계산하고, 상대농도를 OU 등급밴드에 맞춰 보정해요. σ는 Martin(1976) Table 3 계수(x&lt;1km·≥1km 구간별).</p>
      <div class="fxhead"><b>소음 — 거리 역자승 감쇄 + 로그 합산</b></div>
      <div class="fx" data-tip="${FX.noise}">$$SPL_2=SPL_1-20\\log_{10}(r_2),\\qquad SPL_{total}=10\\log_{10}\\!\\sum_i 10^{\\,SPL_i/10}$$</div>
      <p class="adv-p muted small">근거: 악취방지법, 산업안전보건기준 규칙 제512조, Pasquill(1961), Martin(1976).</p>
      <hr class="adv-sep" />
      <div class="fxhead"><b>이 주소의 세부 변수값</b></div>
      <p class="fixvars muted">고정 변수 — 풍속 u=${rep.wind.speed} m/s · 안정도 ${rep.wind.stab}등급 · 굴뚝높이 H=15 m · 풍향 ${windDir(rep.wind.fromDeg)} ${rep.wind.fromDeg}° · 기준거리 r₁=1 m</p>
      <div class="table-wrap"><table class="small-tbl"><thead><tr><th>회사명</th><th>업종</th><th>r₂(km)</th><th>x(km)</th><th>y(m)</th><th>σy</th><th>σz</th><th>Q</th><th>C(OU)</th><th>SPL₂</th></tr></thead><tbody>${detRows || '<tr><td colspan="10">핵심 배출원 없음</td></tr>'}</tbody></table></div>
    </details>
    <p class="note">본 등급은 정부 공인 배출 원단위·소음 표준과 지역 기상통계를 화공 수식에 적용한 추정치예요. 실제 환경은 그날의 기상·공장 운영 상황에 따라 달라질 수 있어요.</p>
  `;
  document.getElementById("sb-summary").innerHTML = `
    <div class="sb-card" style="--c:${color}">
      <div class="muted small">현재 분석 결과</div>
      <div><span class="sb-grade">${rep.grade}</span> <b>${rep.composite}점</b> · ${GRADE_DESC[rep.grade]}</div>
      <div class="muted small">소음 ${rep.noiseDb} dB · 악취 ${rep.odorOu} OU<br>핵심 배출원 ${rep.coreCount} / ${rep.nearby.length}곳</div>
    </div>`;
  drawMap(rep);
  renderMath(document.getElementById(TGT));
}

function renderMath(el, tries) {
  if (!el) return;
  if (window.renderMathInElement) {
    renderMathInElement(el, {
      delimiters: [{ left: "$$", right: "$$", display: true },
                   { left: "$", right: "$", display: false }],
      throwOnError: false,
    });
  } else if ((tries || 0) < 30) {
    // KaTeX가 아직 로딩 중이면(빠른 분석 시) 잠시 뒤 재시도(최대 6초)
    setTimeout(() => renderMath(el, (tries || 0) + 1), 200);
  }
}

let APTS = [];
const GBADGE = (g) => `<span class="gbadge" style="background:${GRADE_COLOR[g] || '#888'}">${g}</span>`;

// 동네 검색 → 그 동네 아파트들의 등급 + TOP3
async function searchNeighborhood() {
  const q = document.getElementById("addr").value.trim();
  if (!q) return;
  const radius = +document.getElementById("radius").value;
  const isDay = document.querySelector('input[name="period"]:checked').value === "day";
  const wNoise = 1 - +document.getElementById("wnoise").value;  // 왼쪽=소음, 오른쪽=악취
  const live = document.getElementById("live").checked;
  const status = document.getElementById("status");
  const btn = document.getElementById("btn-search");
  document.getElementById("detail").innerHTML = "";
  btn.disabled = true;
  status.innerHTML = `<span class="spin"></span>'${q}' 아파트들의 안심 등급을 계산 중… (첫 조회는 시간이 걸릴 수 있어요)`;
  try {
    const url = `/api/neighborhood?q=${encodeURIComponent(q)}&radius=${radius}&day=${isDay}&wnoise=${wNoise}&live=${live}`;
    const r = await fetch(url);
    const data = await r.json();
    status.textContent = "";
    if (data.error) {
      document.getElementById("result").innerHTML = `<div class="empty-state"><div class="empty-ic">⚠️</div><div class="empty-title">${data.error}</div></div>`;
      return;
    }
    renderNeighborhood(data);
  } catch (e) {
    status.textContent = "⚠️ 오류가 발생했어요: " + e;
  } finally { btn.disabled = false; }
}

function renderNeighborhood(data) {
  const result = document.getElementById("result");
  APTS = data.apartments || [];
  if (!APTS.length) {
    result.innerHTML = `<div class="empty-state"><div class="empty-ic">🏘️</div><div class="empty-title">'${data.neighborhood}'에서 아파트를 찾지 못했어요</div><div class="empty-sub">동네명을 더 구체적으로 입력해 보세요. (예: 울산 남구 야음동)</div></div>`;
    return;
  }
  const chips = (data.complexes || []).map(c => `<span class="chip">${c.name} · ${c.dist} km</span>`).join(" ");
  const top3 = (data.top3 || []).map((a, i) => {
    const idx = APTS.indexOf(a);
    return `<div class="rec-card" data-i="${idx}" style="--c:${GRADE_COLOR[a.grade] || '#888'}">
      <div class="rec-rank">${i + 1}위</div>
      <div class="rec-grade">${a.grade}</div>
      <div class="rec-name">${a.name}</div>
      <div class="rec-meta">종합 ${a.composite}점 · 소음 ${a.noiseDb}dB · 악취 ${a.odorOu}OU</div>
      <div class="rec-go">상세 보기 →</div></div>`;
  }).join("");
  const rows = APTS.map((a, i) => `<tr data-i="${i}">
      <td style="text-align:center">${GBADGE(a.grade)}</td>
      <td><b>${a.name}</b><div class="muted small">${a.addr || ""}</div></td>
      <td style="text-align:right"><b>${a.composite}</b></td>
      <td style="text-align:right">${a.noiseDb} dB</td>
      <td style="text-align:right">${a.odorOu} OU</td>
      <td style="text-align:center">${a.coreCount} / ${a.nearbyCount}</td></tr>`).join("");
  result.innerHTML = `
    <div class="nb-head"><h2>📍 ${data.neighborhood}</h2><span class="muted">아파트 ${data.count}곳 분석 완료</span></div>
    ${chips ? `<div class="complexes"><b>자동 탐지된 산업단지</b> &nbsp;${chips}</div>` : ""}
    <h3 class="rec-title">⭐ 추천 안심 명당 TOP 3</h3>
    <div class="rec-grid">${top3}</div>
    <h3 class="rec-title">전체 아파트 등급 <span class="muted small">· 종합점수 높은 순</span></h3>
    <div class="table-wrap" style="max-height:440px"><table class="apt-table"><thead><tr><th style="text-align:center">등급</th><th>아파트</th><th style="text-align:right">종합</th><th style="text-align:right">소음</th><th style="text-align:right">악취</th><th style="text-align:center">핵심/전체</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted small" style="margin-top:8px">카드나 표의 행을 클릭하면 해당 아파트의 상세 분석과 <b>AI 요약</b>을 볼 수 있어요.</p>`;
  result.querySelectorAll(".rec-card").forEach(el => el.addEventListener("click", () => openDetail(APTS[+el.dataset.i])));
  result.querySelectorAll(".apt-table tbody tr").forEach(el => el.addEventListener("click", () => openDetail(APTS[+el.dataset.i])));
}

// 상세 로딩 애니메이션 — '분석 중' 단계를 순환 표시(렉인지 진행중인지 구분)
let DL_TIMER = null;
function startDetailLoading(detail, name) {
  detail.innerHTML = `<div class="card detail-loading">
    <div class="dl-orbit"></div>
    <div class="dl-title">AI가 «${name}»을(를) 분석하고 있어요</div>
    <div class="dl-step" id="dl-step">주변 공장을 모으는 중</div>
    <div class="dl-bar"><span></span></div></div>`;
  const steps = ["주변 공장을 모으는 중", "소음·악취 농도를 계산하는 중",
                 "대기 확산·바람장미를 적용하는 중", "안심 등급을 산정하는 중",
                 "AI 요약을 작성하는 중"];
  let i = 0;
  clearInterval(DL_TIMER);
  DL_TIMER = setInterval(() => {
    i = (i + 1) % steps.length;
    const el = document.getElementById("dl-step");
    if (el) el.textContent = steps[i];
  }, 720);
}
function stopDetailLoading() { clearInterval(DL_TIMER); DL_TIMER = null; }

// AI 요약 타이핑 효과(글자가 차례로 찍혀 'AI가 작성 중'임을 보여줌)
function typewriter(el, text, speed) {
  if (!el) return;
  el.textContent = "";
  const caret = document.createElement("span");
  caret.className = "tw-cursor"; caret.textContent = "▍";
  el.appendChild(caret);
  let i = 0;
  (function step() {
    if (i < text.length) {
      const ch = text[i++];
      caret.insertAdjacentText("beforebegin", ch);
      const d = /[.!?。…]/.test(ch) ? 170 : /[,·]/.test(ch) ? 80 : speed;
      setTimeout(step, d);
    } else {
      setTimeout(() => caret.remove(), 600);
    }
  })();
}

async function openDetail(apt) {
  if (!apt) return;
  const detail = document.getElementById("detail");
  startDetailLoading(detail, apt.name);
  detail.scrollIntoView({ behavior: "smooth", block: "start" });
  const radius = +document.getElementById("radius").value;
  const isDay = document.querySelector('input[name="period"]:checked').value === "day";
  const wNoise = 1 - +document.getElementById("wnoise").value;
  const live = document.getElementById("live").checked;
  try {
    const url = `/api/analyze?address=${encodeURIComponent(apt.name)}&lat=${apt.lat}&lon=${apt.lon}&radius=${radius}&day=${isDay}&wnoise=${wNoise}&fsrc=saved&live=${live}`;
    const r = await fetch(url);
    const rep = await r.json();
    stopDetailLoading();
    if (rep.error) { detail.innerHTML = `<div class="card">⚠️ ${rep.error}</div>`; return; }
    renderResult(rep, "detail");
    detail.scrollIntoView({ behavior: "smooth", block: "start" });
    // AI 요약을 타이핑 애니메이션으로 다시 출력
    const body = detail.querySelector(".ai-body");
    if (body && body.textContent.trim()) typewriter(body, body.textContent.trim(), 13);
  } catch (e) {
    stopDetailLoading();
    detail.innerHTML = `<div class="card">⚠️ ${e}</div>`;
  }
}

function backToList(e) {
  if (e) e.preventDefault();
  document.getElementById("detail").innerHTML = "";
  document.getElementById("result").scrollIntoView({ behavior: "smooth", block: "start" });
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("radius").addEventListener("input", e => document.getElementById("radius-val").textContent = (+e.target.value).toFixed(1));
  document.getElementById("wnoise").addEventListener("input", e => {
    document.getElementById("wnoise-val").textContent = (1 - e.target.value).toFixed(2);
    document.getElementById("wodor-val").textContent = (+e.target.value).toFixed(2);
  });
  document.getElementById("btn-search").addEventListener("click", searchNeighborhood);
  // 사이드바 접기/펼치기
  document.getElementById("sb-toggle").addEventListener("click", () => {
    document.body.classList.toggle("sb-collapsed");
  });
  // 동네 입력창에서 Enter → 동네 검색
  document.getElementById("addr").addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); searchNeighborhood(); }
  });
});
