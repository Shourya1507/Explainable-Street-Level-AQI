/**
 * AQI Delhi — front-end application
 * Tier 1+: calls live /estimate and /stations endpoints from API Gateway.
 * All API calls go through the backend — no AWS credentials in this file.
 */

// ── Config (populated at build/deploy time) ──────────────────────────────────
const CONFIG = {
  // Live API Gateway — deployed 2026-10-10
  API_BASE: window.AQI_API_BASE || "https://6diafyett2.execute-api.ap-south-1.amazonaws.com/dev",

  // Amazon Location Service map config
  MAP_NAME: "aqi-delhi-map",
  MAP_REGION: "ap-south-1",
  // MapLibre tile URL from Location Service (set after Location Service is created)
  MAP_STYLE_URL: window.AQI_MAP_STYLE || null,

  // Feature flags — set true as each tier is deployed
  FEATURES: {
    hindi:     window.AQI_FEAT_HINDI     || false,
    forecast:  window.AQI_FEAT_FORECAST  || false,
    heatmap:   window.AQI_FEAT_HEATMAP   || false,
    route:     window.AQI_FEAT_ROUTE     || false,
    alerts:    window.AQI_FEAT_ALERTS    || false,
    calibrate: window.AQI_FEAT_CALIBRATE || false,
    dashboard: window.AQI_FEAT_DASHBOARD || false,
  },
};

// ── AQI category helpers ─────────────────────────────────────────────────────
const CATEGORY_META = {
  "Good":         { fill: "#3FA45B", tint: "#E8F5EC", text: "#1E6B3A" },
  "Satisfactory": { fill: "#8DBF3F", tint: "#F1F7E3", text: "#4F6B1A" },
  "Moderate":     { fill: "#E8C220", tint: "#FDF6D8", text: "#7A5F00" },
  "Poor":         { fill: "#F08A24", tint: "#FEEFDD", text: "#8A4A06" },
  "Very Poor":    { fill: "#E04F39", tint: "#FDE8E4", text: "#A12A18" },
  "Severe":       { fill: "#9B2257", tint: "#F9E6EE", text: "#7A1744" },
};

function categoryMeta(cat) {
  return CATEGORY_META[cat] || CATEGORY_META["Moderate"];
}

// ── State ────────────────────────────────────────────────────────────────────
const state = {
  selectedLat: null,
  selectedLon: null,
  currentHour: new Date(),  // Date object, rounded to hour
  lang: "en",
  lastResult: null,
  retryFn: null,
  stationsSource: null,     // "live" | "s3_cache" | "mock" | "fallback"
  stationsLoadedAt: null,   // Date when stations were last loaded
};

// Round Date to current hour
function roundToHour(d) {
  const c = new Date(d);
  c.setMinutes(0, 0, 0);
  return c;
}
state.currentHour = roundToHour(new Date());

// ── DOM refs ─────────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const els = {
  panelEmpty:     $("panel-empty"),
  panelLoading:   $("panel-loading"),
  panelResult:    $("panel-result"),
  panelError:     $("panel-error"),
  pm25Value:      $("pm25-value"),
  categoryChip:   $("category-chip"),
  estimateCard:   $("estimate-card"),
  confidenceDots: $("confidence-dots"),
  confidenceLevel:$("confidence-level"),
  confidenceDist: $("confidence-dist"),
  explanationText:$("explanation-text"),
  explanationCard:$("explanation-card"),
  sourceTag:      $("source-tag"),
  driverList:     $("driver-list"),
  adviceText:     $("advice-text"),
  listenBtn:      $("listen-btn"),
  errorMessage:   $("error-message"),
  retryBtn:       $("retry-btn"),
  timeDisplay:    $("time-display"),
  timePrev:       $("time-prev"),
  timeNext:       $("time-next"),
  timeNow:        $("time-now"),
  mapHint:        $("map-hint"),
  accuracyLink:   $("accuracy-link"),
  accuracyOverlay:$("accuracy-overlay"),
  accuracyClose:  $("accuracy-close"),
  evalHeadline:   $("eval-headline"),
  limitsList:     $("limits-list"),
  langEn:         $("lang-en"),
  langHi:         $("lang-hi"),
};

// ── Panel state machine ──────────────────────────────────────────────────────
function showPanel(which) {
  ["panelEmpty", "panelLoading", "panelResult", "panelError"].forEach(k => {
    els[k].hidden = k !== which;
  });
}

// ── Time helpers ─────────────────────────────────────────────────────────────
function formatHour(d) {
  const h = d.getHours().toString().padStart(2, "0");
  const day = d.getDate();
  const mon = d.toLocaleString("en-GB", { month: "short" });
  return `${h}:00, ${day} ${mon}`;
}

function updateTimeDisplay() {
  els.timeDisplay.textContent = formatHour(state.currentHour);
  const now = roundToHour(new Date());
  els.timeNext.disabled = state.currentHour >= now;
}

function stepHour(delta) {
  const next = new Date(state.currentHour.getTime() + delta * 3600_000);
  const now = roundToHour(new Date());
  if (next > now) return;
  state.currentHour = next;
  updateTimeDisplay();
  if (state.selectedLat !== null) fetchEstimate();
}

// ── Confidence dots ──────────────────────────────────────────────────────────
function renderConfidenceDots(level) {
  const map = { high: 3, medium: 2, low: 1 };
  const filled = map[level] ?? 2;
  els.confidenceDots.innerHTML = [1, 2, 3].map(i => {
    const cls = i <= filled ? "confidence-dot filled" : "confidence-dot";
    return `<span class="${cls}" aria-hidden="true"></span>`;
  }).join("");
}

// ── Driver bars ──────────────────────────────────────────────────────────────
function renderDrivers(drivers) {
  if (!drivers || !drivers.length) { els.driverList.innerHTML = ""; return; }
  const maxShap = Math.max(...drivers.map(d => Math.abs(d.shap)));
  els.driverList.innerHTML = drivers.map(d => {
    const pct = Math.round((Math.abs(d.shap) / maxShap) * 100);
    const label = d.note || d.feature.replace(/_/g, " ");
    return `
      <div class="driver-item" role="listitem">
        <span class="driver-name" title="${label}">${label}</span>
        <div class="driver-bar-wrap" role="presentation">
          <div class="driver-bar" style="width:${pct}%" aria-label="${pct}%"></div>
        </div>
        <span class="driver-shap">+${Math.round(d.shap)}</span>
      </div>`;
  }).join("");
}

// ── Live data badge ───────────────────────────────────────────────────────────
function updateLiveBadge(source) {
  const badge = document.getElementById("live-badge");
  if (!badge) return;
  const isLive = source && source !== "mock";
  badge.textContent = isLive ? "● LIVE DATA" : "○ MOCK DATA";
  badge.style.color = isLive ? "#3FA45B" : "#F08A24";
  badge.title = isLive
    ? `Station data source: ${source}. Updated at ${state.stationsLoadedAt?.toLocaleTimeString() || "now"}.`
    : "Stations are using mock/hardcoded data. Deploy in real mode for live readings.";
}

// ── Render result ────────────────────────────────────────────────────────────
function renderResult(data) {
  state.lastResult = data;
  const meta = categoryMeta(data.category);

  // Estimate card
  els.pm25Value.textContent = Math.round(data.pm25);
  els.categoryChip.textContent = data.category;
  els.categoryChip.style.background = meta.tint;
  els.categoryChip.style.color = meta.text;
  els.estimateCard.style.background = meta.tint;
  els.estimateCard.classList.toggle("low-confidence", data.confidence === "low");

  // Confidence badge
  renderConfidenceDots(data.confidence);
  els.confidenceLevel.textContent = data.confidence;
  els.confidenceDist.textContent = data.nearest_station_km
    ? `· nearest station ${data.nearest_station_km.toFixed(1)} km`
    : "";

  // Show if result is from real model or mock
  const sourceBadge = document.getElementById("estimate-source-badge");
  if (sourceBadge) {
    const isMock = data.explanation_source === "mock";
    sourceBadge.textContent = isMock ? "MOCK ESTIMATE" : "ML ESTIMATE";
    sourceBadge.style.opacity = isMock ? "1" : "0";
  }

  // Explanation
  const isHindi = state.lang === "hi";
  const explanationText = (isHindi && data.explanation_hi) ? data.explanation_hi : data.explanation;
  const adviceText = (isHindi && data.advice_hi) ? data.advice_hi : data.advice;

  els.explanationText.textContent = explanationText || "Explanation not available.";
  els.explanationCard.setAttribute("lang", isHindi ? "hi" : "en");
  els.sourceTag.hidden = data.explanation_source !== "fallback";

  // Drivers
  renderDrivers(data.drivers);

  // Advice
  els.adviceText.textContent = adviceText || "";
  els.adviceText.setAttribute("lang", isHindi ? "hi" : "en");

  // Listen button (only show in Hindi mode with Tier 4 on)
  els.listenBtn.hidden = !(isHindi && CONFIG.FEATURES.hindi && data.audio_url);

  showPanel("panelResult");
  els.mapHint.classList.add("hidden");
}

// ── API calls ────────────────────────────────────────────────────────────────
async function fetchEstimate() {
  if (state.selectedLat === null) return;
  showPanel("panelLoading");

  const body = {
    lat: state.selectedLat,
    lon: state.selectedLon,
    timestamp: state.currentHour.toISOString(),
    lang: state.lang,
    audio: CONFIG.FEATURES.hindi && state.lang === "hi",
  };

  state.retryFn = fetchEstimate;

  try {
    const resp = await fetch(`${CONFIG.API_BASE}/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.message || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    renderResult(data);
  } catch (err) {
    console.error("Estimate failed:", err);
    els.errorMessage.textContent = err.message || "Could not get an estimate. Try again.";
    showPanel("panelError");
  }
}

let _stationMarkers = [];

async function fetchStations(map, forceRefresh = false) {
  try {
    const url = `${CONFIG.API_BASE}/stations?city=delhi${forceRefresh ? "&refresh=true" : ""}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const stations = data.stations || [];
    state.stationsSource = data.source || "unknown";
    state.stationsLoadedAt = new Date();
    // Remove old markers
    _stationMarkers.forEach(m => m.remove());
    _stationMarkers = [];
    renderStationMarkers(map, stations);
    updateLiveBadge(state.stationsSource);
    console.log(`Stations loaded: ${stations.length} from source=${data.source}`);
  } catch (err) {
    console.warn("Stations fetch failed:", err);
    // Non-fatal — map still usable without markers
    updateLiveBadge("error");
  }
}

// Auto-refresh stations every 30 minutes
function scheduleStationRefresh(map) {
  setInterval(() => {
    console.log("Auto-refreshing station data...");
    fetchStations(map, false);
  }, 30 * 60 * 1000);
}

// ── Map ──────────────────────────────────────────────────────────────────────
let mapInstance = null;
let selectedPin = null;

function initMap() {
  // Fallback style for when Location Service is not yet configured
  const style = CONFIG.MAP_STYLE_URL || {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [{ id: "osm-tiles", type: "raster", source: "osm" }],
  };

  mapInstance = new maplibregl.Map({
    container: "map",
    style,
    center: [77.2090, 28.6139],  // Delhi
    zoom: 11,
  });

  mapInstance.addControl(new maplibregl.NavigationControl(), "top-right");
  mapInstance.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-right");

  mapInstance.on("load", () => {
    fetchStations(mapInstance);
    scheduleStationRefresh(mapInstance);
    // Auto-select Central Delhi (Connaught Place) so Why & Advice sections are active immediately on load
    selectLocation(28.6315, 77.2167, false);
  });

  mapInstance.on("click", e => {
    selectLocation(e.lngLat.lat, e.lngLat.lng, false);
  });
}

function selectLocation(lat, lon, fly = false) {
  state.selectedLat = lat;
  state.selectedLon = lon;

  if (fly && mapInstance) {
    mapInstance.flyTo({ center: [lon, lat], zoom: Math.max(mapInstance.getZoom(), 12) });
  }

  // Move / create pin
  if (selectedPin) {
    selectedPin.setLngLat([lon, lat]);
  } else if (mapInstance) {
    const el = document.createElement("div");
    el.style.cssText = `
      width:20px;height:20px;border-radius:50%;
      background:var(--accent);border:3px solid #fff;
      box-shadow:0 0 0 3px var(--accent-tint), var(--shadow-float);
    `;
    selectedPin = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(mapInstance);
  }

  fetchEstimate();
}

function formatUpdated(isoStr) {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMin = Math.round((now - d) / 60000);
    if (diffMin < 2)  return "just now";
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffH = Math.round(diffMin / 60);
    if (diffH < 24)   return `${diffH}h ago`;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch { return isoStr.slice(0, 16); }
}

function renderStationMarkers(map, stations) {
  stations.forEach(st => {
    const meta = categoryMeta(st.category || "Moderate");
    const el = document.createElement("div");
    el.className = "station-marker";
    el.style.background = meta.tint;
    el.style.borderColor = meta.fill;
    // Show PM2.5 value inside the marker dot
    el.textContent = st.pm25 ? Math.round(st.pm25) : "?";
    el.style.color = meta.text;
    el.style.fontSize = "9px";
    el.style.fontWeight = "700";
    el.style.display = "flex";
    el.style.alignItems = "center";
    el.style.cursor = "pointer";
    el.title = `${st.name}: ${st.pm25 ? st.pm25.toFixed(0) + " µg/m³" : "no data"} (Click to inspect street-level estimate)`;
    el.setAttribute("role", "button");
    el.setAttribute("aria-label", `${st.name} station, ${st.category || "unknown"} air quality`);

    el.addEventListener("click", () => {
      selectLocation(st.lat, st.lon, false);
    });

    const isLive = st.source && st.source !== "mock";
    const popup = new maplibregl.Popup({ offset: 14 }).setHTML(`
      <strong style="font-size:13px">${st.name}</strong><br>
      <span style="font-size:18px;font-weight:700;color:${meta.fill}">${st.pm25 ? st.pm25.toFixed(0) : "—"} µg/m³</span><br>
      <span style="background:${meta.tint};color:${meta.text};padding:2px 6px;border-radius:4px;font-size:11px">${st.category || "Unknown"}</span>
      <br><small style="color:#5B6675">Updated: ${formatUpdated(st.updated)}
      ${isLive ? " · <span style='color:#3FA45B'>●&nbsp;live</span>" : ""}</small>
    `);

    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([st.lon, st.lat])
      .setPopup(popup)
      .addTo(map);
    _stationMarkers.push(marker);
  });
}

// ── Accuracy modal: Tier 2 real eval data ────────────────────────────────────
const MODELS_BASE = "https://aqi-models-991166714312.s3.ap-south-1.amazonaws.com/nowcast";

const FEAT_LABELS = {
  temperature:     "Temperature",
  humidity:        "Humidity",
  wind_speed:      "Wind speed",
  wind_direction:  "Wind direction",
  surface_pressure:"Surface pressure",
  boundary_layer:  "Boundary layer height",
  road_density:    "Road density",
  hour_of_day:     "Hour of day",
  day_of_week:     "Day of week",
  month:           "Month",
  is_weekend:      "Weekend",
  is_morning_peak: "Morning peak",
  is_evening_peak: "Evening peak",
};

let _evalCache = null;
let _featCache = null;
let _windowCache = null;

async function loadAccuracyData() {
  if (_evalCache && _featCache && _windowCache) return;
  try {
    const [ev, fi, dw] = await Promise.all([
      fetch(`${MODELS_BASE}/eval_results.json`).then(r => r.json()),
      fetch(`${MODELS_BASE}/feature_importance.json`).then(r => r.json()),
      fetch(`${MODELS_BASE}/data_window.json`).then(r => r.json()),
    ]);
    _evalCache = ev;
    _featCache = fi;
    _windowCache = dw;
  } catch (err) {
    console.warn("Could not load eval data from S3:", err);
  }
}

function renderAccuracyModal() {
  const ev = _evalCache;
  const fi = _featCache;
  const dw = _windowCache;

  if (dw) {
    const startD = dw.start ? dw.start.slice(0, 10) : "—";
    const endD   = dw.end   ? dw.end.slice(0, 10)   : "—";
    const sc   = document.getElementById("station-count");
    const dwin = document.getElementById("data-window");
    if (sc)   sc.textContent   = dw.station_count ?? "1";
    if (dwin) dwin.textContent = `${startD} → ${endD}`;
  }

  if (!ev || !ev.overall) {
    els.evalHeadline.textContent = "Evaluation data unavailable. Run train_nowcast.py to generate.";
    return;
  }

  const o = ev.overall;
  const method = ev.method === "time_split_80_20" ? "80/20 time-split" : "leave-one-station-out CV";
  els.evalHeadline.textContent =
    `Evaluated on ${o.n_predictions ?? "—"} held-out hours via ${method}. ` +
    `XGBoost RMSE: ${o.model_rmse} µg/m³ vs persistence baseline ${o.nn_rmse} µg/m³.`;

  document.getElementById("eval-model-rmse").textContent = o.model_rmse ?? "—";
  document.getElementById("eval-nn-rmse").textContent    = o.nn_rmse    ?? "—";
  document.getElementById("eval-model-mae").textContent  = o.model_mae  ?? "—";

  const maxRmse = Math.max(o.model_rmse || 0, o.nn_rmse || 0, o.idw_rmse || 0, 1);
  requestAnimationFrame(() => {
    const setBar = (barId, lblId, val) => {
      const b = document.getElementById(barId);
      const l = document.getElementById(lblId);
      if (b) b.style.width = `${Math.round(((val||0) / maxRmse) * 100)}%`;
      if (l) l.textContent = val ?? "—";
    };
    setBar("bar-model", "bar-model-val", o.model_rmse);
    setBar("bar-nn",    "bar-nn-val",    o.nn_rmse);
    setBar("bar-idw",   "bar-idw-val",   o.idw_rmse);
  });

  if (fi) {
    const sorted = Object.entries(fi).sort(([,a],[,b]) => b - a).slice(0, 7);
    const maxFi = sorted[0]?.[1] || 1;
    const featList = document.getElementById("feat-imp-list");
    if (featList) {
      featList.innerHTML = sorted.map(([feat, val]) => {
        const pct = Math.round((val / maxFi) * 100);
        const label = FEAT_LABELS[feat] || feat.replace(/_/g, " ");
        return `<div class="feat-imp-row">
          <span class="feat-imp-label" title="${label}">${label}</span>
          <div class="feat-imp-track"><div class="feat-imp-bar" style="width:${pct}%"></div></div>
          <span class="feat-imp-pct">${Math.round(val * 100)}%</span>
        </div>`;
      }).join("");
    }
  }
}

async function openAccuracyModal() {
  els.accuracyOverlay.hidden = false;
  els.accuracyClose.focus();
  els.evalHeadline.textContent = "Loading evaluation data…";
  await loadAccuracyData();
  renderAccuracyModal();
}

function closeAccuracyModal() {
  els.accuracyOverlay.hidden = true;
}

// ── Language toggle ──────────────────────────────────────────────────────────
function setLang(lang) {
  state.lang = lang;
  els.langEn.classList.toggle("active", lang === "en");
  els.langHi.classList.toggle("active", lang === "hi");
  document.documentElement.setAttribute("lang", lang);
  // Re-render current result with new language
  if (state.lastResult) renderResult(state.lastResult);
}

// ── Audio ─────────────────────────────────────────────────────────────────────
let audioEl = null;
function playAudio(url) {
  if (!url) return;
  if (audioEl) { audioEl.pause(); audioEl = null; }
  audioEl = new Audio(url);
  els.listenBtn.textContent = "Playing…";
  audioEl.play();
  audioEl.onended = () => {
    els.listenBtn.innerHTML = `<svg class="icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.75"><polygon points="6,4 16,10 6,16"/></svg> Listen`;
  };
}

// ── Event listeners ──────────────────────────────────────────────────────────
els.timePrev.addEventListener("click", () => stepHour(-1));
els.timeNext.addEventListener("click", () => stepHour(+1));
els.timeNow.addEventListener("click", () => {
  state.currentHour = roundToHour(new Date());
  updateTimeDisplay();
  if (state.selectedLat !== null) fetchEstimate();
});

els.accuracyLink.addEventListener("click", openAccuracyModal);
els.accuracyClose.addEventListener("click", closeAccuracyModal);
els.accuracyOverlay.addEventListener("click", e => {
  if (e.target === els.accuracyOverlay) closeAccuracyModal();
});

els.retryBtn.addEventListener("click", () => {
  if (state.retryFn) state.retryFn();
});

els.langEn.addEventListener("click", () => setLang("en"));
els.langHi.addEventListener("click", () => setLang("hi"));

els.listenBtn.addEventListener("click", () => {
  if (state.lastResult?.audio_url) playAudio(state.lastResult.audio_url);
});

// Keyboard: Escape closes modal
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !els.accuracyOverlay.hidden) closeAccuracyModal();
});

// ── Init ──────────────────────────────────────────────────────────────────────
updateTimeDisplay();
initMap();
showPanel("panelEmpty");

// Hide controls for disabled features
if (!CONFIG.FEATURES.hindi) {
  els.langHi.style.display = "none";
  els.listenBtn.hidden = true;
}

// Initialize the live badge (will update when stations load)
updateLiveBadge(null);

console.log("AQI Delhi — Live mode running. API:", CONFIG.API_BASE);
