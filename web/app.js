/* 프론트엔드 — Flask 백엔드(/api/analyze)를 호출해 실시간 결과를 렌더 */

const GRADE_COLOR = { AAA:"#1a9850", AA:"#66bd63", A:"#a6d96a", B:"#f9d057", C:"#fdae61", D:"#f46d43", E:"#d73027", F:"#a50026" };
const GRADE_DESC = { AAA:"최상 · 매우 안전", AA:"우수", A:"양호", B:"보통", C:"주의", D:"미흡", E:"나쁨", F:"매우 나쁨" };
const CORE_COLOR = { C20:"#dc2626", C22:"#ea580c", C25:"#2563eb" };
const CORE_LABEL = { C20:"화학·석유화학", C22:"고무·플라스틱", C25:"금속가공·기계" };
const DEG = Math.PI / 180;

let MAP = null;
function downwind(lat, lon, fromDeg, km = 1.5) {
  const g = ((fromDeg + 180) % 360) * DEG;
  return [lat + (km / 110.54) * Math.cos(g), lon + (km / (111.32 * Math.cos(lat * DEG))) * Math.sin(g)];
}
function drawMap(rep) {
  if (MAP) { MAP.remove(); MAP = null; }
  MAP = L.map("map").setView([rep.aptLat, rep.aptLon], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(MAP);
  const color = GRADE_COLOR[rep.grade] || "#888";
  // 5km 반경 원 — 점선·굵은 테두리로 또렷하게
  L.circle([rep.aptLat, rep.aptLon], { radius: rep.radiusKm * 1000, color: "#1d4ed8",
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
  setTimeout(() => { MAP.invalidateSize(); MAP.setView([rep.aptLat, rep.aptLon], 13); }, 200);
}

function renderResult(rep) {
  const color = GRADE_COLOR[rep.grade] || "#888";
  const chips = (rep.complexes || []).map(c => `<span class="chip">🏭 ${c.name} (${c.dist}km)</span>`).join(" ");
  const rows = rep.nearby.map(f => `<tr><td>${f.core ? CORE_LABEL[f.core] : "-"}</td><td>${f.factory_name}</td><td>${f.industry_name || ""}</td><td style="text-align:right">${f.distance_km}</td></tr>`).join("");
  const detRows = (rep.detail || []).map(d => `<tr><td>${d.name}</td><td>${d.label}</td><td>${d.r2}</td><td>${d.x}</td><td>${d.y}</td><td>${d.sy}</td><td>${d.sz}</td><td>${d.Q}</td><td>${d.C}</td><td>${d.spl2}</td></tr>`).join("");

  document.getElementById("result").innerHTML = `
    <div class="badge" style="--c:${color}">
      <div class="grade">${rep.grade}</div>
      <div class="badge-info">
        <div class="muted">종합 안심 주거 등급</div>
        <div class="score">${rep.composite}<span> / 100점</span></div>
        <div class="muted small">📍 ${rep.address}</div>
      </div>
    </div>
    ${chips ? `<div class="complexes"><b>자동 탐지된 산업단지</b> &nbsp;${chips}</div>` : ""}
    ${rep.source ? `<div class="muted small" style="margin:-4px 0 8px;">📦 공장 데이터 출처: ${rep.source}</div>` : ""}
    ${rep.note ? `<div class="note" style="background:#fffbeb;color:#92722a;">ℹ️ ${rep.note}</div>` : ""}
    <div class="metrics">
      <div class="metric"><div class="m-label">누적 소음</div><div class="m-val">${rep.noiseDb} dB</div><div class="m-sub">${rep.noiseScore}점</div></div>
      <div class="metric"><div class="m-label">누적 악취</div><div class="m-val">${rep.odorOu} OU</div><div class="m-sub">${rep.odorScore}점</div></div>
      <div class="metric"><div class="m-label">핵심 배출원 / 반경내</div><div class="m-val">${rep.coreCount} / ${rep.nearby.length}</div><div class="m-sub">3대 핵심 업종</div></div>
      <div class="metric"><div class="m-label">바람</div><div class="m-val">${rep.wind.speed} m/s</div><div class="m-sub">${rep.wind.fromDeg}° / ${rep.wind.stab}등급</div></div>
    </div>
    <div class="two-col">
      <div><div id="map"></div></div>
      <div>
        <h3>반경 내 공장 ${rep.nearby.length}개</h3>
        <div class="legend"><span style="color:#dc2626">●</span> 화학 <span style="color:#ea580c">●</span> 플라스틱 <span style="color:#2563eb">●</span> 금속 <span style="color:#9ca3af">●</span> 비배출원</div>
        <div class="table-wrap"><table><thead><tr><th>핵심</th><th>회사명</th><th>업종</th><th>거리(km)</th></tr></thead><tbody>${rows}</tbody></table></div>
      </div>
    </div>
    <details class="adv"><summary>🔬 세부 계산식 · 변수값 (고급)</summary>
      <p class="muted">고정 변수 — 풍속 u=${rep.wind.speed} m/s · 안정도 ${rep.wind.stab}등급 · 굴뚝높이 H=15 m · 풍향 ${rep.wind.fromDeg}° · 기준거리 r₁=1 m</p>
      <p><b>악취 (2차원 가우스 확산)</b></p>
      <p>$$C=\\dfrac{Q}{\\pi\\,u\\,\\sigma_y\\,\\sigma_z}\\,\\exp\\!\\left(-\\dfrac{y^2}{2\\sigma_y^2}\\right)\\exp\\!\\left(-\\dfrac{H^2}{2\\sigma_z^2}\\right),\\quad \\sigma_y=a\\,x^{b},\\ \\sigma_z=c\\,x^{d}$$</p>
      <p><b>소음 (거리 역자승 감쇄 + 로그 합산)</b></p>
      <p>$$SPL_2=SPL_1-20\\log_{10}(r_2),\\qquad SPL_{total}=10\\log_{10}\\!\\sum_i 10^{\\,SPL_i/10}$$</p>
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
  renderMath(document.getElementById("result"));
}

function renderMath(el) {
  if (window.renderMathInElement && el) {
    renderMathInElement(el, {
      delimiters: [{ left: "$$", right: "$$", display: true },
                   { left: "$", right: "$", display: false }],
      throwOnError: false,
    });
  }
}

let CANDIDATES = [], PICKED = null;

async function search() {
  const q = document.getElementById("addr").value.trim();
  if (!q) return;
  const status = document.getElementById("search-status");
  const sel = document.getElementById("candidates");
  status.textContent = "검색 중...";
  PICKED = null; sel.style.display = "none";
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    CANDIDATES = await r.json();
  } catch (e) { CANDIDATES = []; }
  if (!CANDIDATES.length) {
    status.textContent = "검색 결과가 없습니다. 더 구체적으로 입력해 보세요.";
    return;
  }
  status.textContent = "";
  sel.innerHTML = CANDIDATES.map((c, i) => `<option value="${i}">${c.label}</option>`).join("");
  sel.style.display = "block";
  PICKED = CANDIDATES[0];
  sel.onchange = () => { PICKED = CANDIDATES[+sel.value]; };
}

async function analyze() {
  const addr = document.getElementById("addr").value.trim();
  if (!addr && !PICKED) return;
  const radius = +document.getElementById("radius").value;
  const isDay = document.querySelector('input[name="period"]:checked').value === "day";
  const wNoise = +document.getElementById("wnoise").value;
  const complexKm = +document.getElementById("complex_km").value;
  const maxRows = +document.getElementById("max_rows").value;
  const live = document.getElementById("live").checked;
  const fsrc = document.querySelector('input[name="fsrc"]:checked').value;
  const status = document.getElementById("status");
  const btn = document.getElementById("btn-analyze");
  btn.disabled = true;
  status.textContent = fsrc === "live"
    ? "⏳ 산단공 API로 인근 공장을 실시간 조회 중… (1~2분 걸릴 수 있어요)"
    : "⏳ 저장된 공장 데이터로 분석 중…";
  try {
    let url = `/api/analyze?radius=${radius}&day=${isDay}&wnoise=${wNoise}&complex_km=${complexKm}&max_rows=${maxRows}&live=${live}&fsrc=${fsrc}`;
    if (PICKED) {
      url += `&address=${encodeURIComponent(PICKED.label)}&lat=${PICKED.lat}&lon=${PICKED.lon}`;
    } else {
      url += `&address=${encodeURIComponent(addr)}`;
    }
    const r = await fetch(url);
    const rep = await r.json();
    if (rep.error) { status.textContent = "⚠️ " + rep.error; return; }
    status.textContent = "";
    renderResult(rep);
  } catch (e) {
    status.textContent = "⚠️ 분석 중 오류가 발생했어요: " + e;
  } finally {
    btn.disabled = false;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("radius").addEventListener("input", e => document.getElementById("radius-val").textContent = (+e.target.value).toFixed(1));
  document.getElementById("wnoise").addEventListener("input", e => {
    document.getElementById("wnoise-val").textContent = (+e.target.value).toFixed(2);
    document.getElementById("wodor-val").textContent = (1 - e.target.value).toFixed(2);
  });
  document.getElementById("complex_km").addEventListener("input", e => document.getElementById("ckm-val").textContent = e.target.value);
  document.getElementById("max_rows").addEventListener("input", e => document.getElementById("mr-val").textContent = e.target.value);
  document.getElementById("btn-search").addEventListener("click", search);
  document.getElementById("btn-analyze").addEventListener("click", analyze);
  // 방법론 섹션의 수식도 렌더(KaTeX 로드 후)
  setTimeout(() => renderMath(document.querySelector(".methodology")), 300);
});
