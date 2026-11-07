(() => {
  'use strict';

  const T = {
    en: {
      title: 'Where the road feels slippery',
      subtitle: 'Central Sapporo on the winter solstice, 22 Dec 2026. Streets that buildings keep in shadow all day are where the ice stays.',
      legendNone: 'no sun',
      legendNote: 'Minutes of direct sun between sunrise and sunset',
      modeStreet: 'By street',
      modeGrid: '2 m grid',
      about: 'About & notes',
      statText: 'of street surface in this 3 × 3 km square gets no direct sun all day',
      shadows: 'shadows',
      sun: (el, az) => `sun ${el.toFixed(1)}° high, ${compass(az, 'en')}`,
      rise: (t) => `sunrise ${t}`,
      set: (t) => `sunset ${t}`,
      unnamed: 'Unnamed road section',
      sunMin: 'Direct sun (mean)',
      dark: 'Never sunlit',
      area: 'Area',
      play: 'Play', pause: 'Pause',
      places: { odori: 'Odori Park', susukino: 'Susukino', station: 'Sapporo Sta.', nakajima: 'Nakajima Park', tv: 'TV Tower' },
    },
    ja: {
      title: 'つるつるの道は、影の中に',
      subtitle: '冬至（2026年12月22日）の札幌中心部。建物の影で1日中日が当たらない道に、氷は残ります。',
      legendNone: '日が当たらない',
      legendNote: '日の出から日の入りまでに日が当たる時間',
      modeStreet: '道ごと',
      modeGrid: '2m 格子',
      about: 'この地図について・注記',
      statText: 'この3km四方の道路面のうち、1日中日が当たらない部分の割合',
      shadows: '影',
      sun: (el, az) => `太陽の高さ ${el.toFixed(1)}°・${compass(az, 'ja')}`,
      rise: (t) => `日の出 ${t}`,
      set: (t) => `日の入り ${t}`,
      unnamed: '名前のない道路区間',
      sunMin: '日が当たる時間（平均）',
      dark: '1日中日が当たらない部分',
      area: '面積',
      play: '再生', pause: '停止',
      places: { odori: '大通公園', susukino: 'すすきの', station: '札幌駅', nakajima: '中島公園', tv: 'さっぽろテレビ塔' },
    },
  };

  const DIRS = {
    en: ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'],
    ja: ['北', '北東', '東', '南東', '南', '南西', '西', '北西'],
  };
  function compass(az, lang) {
    return DIRS[lang][Math.round(az / 45) % 8] + (lang === 'ja' ? 'から' : '');
  }

  const PLACES = [
    { id: 'odori', lng: 141.3500, lat: 43.0597 },
    { id: 'susukino', lng: 141.3535, lat: 43.0553 },
    { id: 'station', lng: 141.3507, lat: 43.0686 },
    { id: 'nakajima', lng: 141.3545, lat: 43.0465 },
    { id: 'tv', lng: 141.3564, lat: 43.0612 },
  ];

  const SUN_COLOR = [
    'case', ['<=', ['get', 'sun_min'], 0], '#8fe3ff',
    ['interpolate', ['linear'], ['get', 'sun_min'],
      1, '#5c5480', 60, '#925e84', 150, '#d67a68', 300, '#f2aa52', 480, '#ffe08a'],
  ];

  let lang = 'en';
  try {
    const saved = localStorage.getItem('lang');
    if (saved === 'ja' || saved === 'en') lang = saved;
    else if ((navigator.language || '').startsWith('ja')) lang = 'ja';
  } catch (e) { /* storage unavailable */ }

  let summary = null;
  let frameIdx = 0;
  let timer = null;
  const frameCache = new Map();
  const placeMarkers = [];

  const map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: {},
      layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#eef1f4' } }],
    },
    center: [141.3530, 43.0575],
    zoom: 14.2,
    minZoom: 12.5,
    maxZoom: 19,
    attributionControl: false,
    dragRotate: false,
    pitchWithRotate: false,
  });
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
  map.addControl(new maplibregl.AttributionControl({
    compact: true,
    customAttribution: 'PLATEAU (MLIT), processed by the author · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }), 'bottom-left');

  const $ = (id) => document.getElementById(id);

  function applyLang() {
    const t = T[lang];
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const v = t[el.dataset.i18n];
      if (typeof v === 'string') el.textContent = v;
    });
    document.querySelectorAll('[data-lang]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.lang === lang)));
    document.querySelectorAll('[data-lang-block]').forEach((b) => { b.hidden = b.dataset.langBlock !== lang; });
    document.title = lang === 'ja' ? 'つるつるの道は、影の中に — 札幌・冬至' : 'Where the road feels slippery — Sapporo, winter solstice';
    placeMarkers.forEach(({ el, id }) => { el.textContent = t.places[id]; });
    $('play').setAttribute('aria-label', timer ? t.pause : t.play);
    if (summary) {
      $('riseText').textContent = t.rise(summary.sunrise);
      $('setText').textContent = t.set(summary.sunset);
      updateTimeText();
    }
    try { localStorage.setItem('lang', lang); } catch (e) { /* ignore */ }
  }

  document.querySelectorAll('[data-lang]').forEach((b) => b.addEventListener('click', () => { lang = b.dataset.lang; applyLang(); }));

  function setMode(mode) {
    document.querySelectorAll('[data-mode]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
    if (!map.getLayer('roads')) return;
    map.setPaintProperty('roads', 'fill-opacity', mode === 'street' ? 1 : 0);
    map.setLayoutProperty('grid', 'visibility', mode === 'grid' ? 'visible' : 'none');
  }
  document.querySelectorAll('[data-mode]').forEach((b) => b.addEventListener('click', () => setMode(b.dataset.mode)));

  $('aboutBtn').addEventListener('click', () => $('about').showModal());

  function frameTime(label) { return `${label.slice(0, 2)}:${label.slice(2)}`; }

  function updateTimeText() {
    const label = summary.frames[frameIdx];
    const hhmm = frameTime(label);
    $('timeText').textContent = hhmm;
    const s = summary.sun.find((x) => x.t === hhmm);
    $('sunText').textContent = s ? T[lang].sun(s.el, s.az) : '';
  }

  async function loadFrame(label) {
    if (!frameCache.has(label)) {
      frameCache.set(label, fetch(`data/shadows/${label}.geojson`).then((r) => {
        if (!r.ok) throw new Error(`shadow ${label}: ${r.status}`);
        return r.json();
      }));
    }
    return frameCache.get(label);
  }

  async function showFrame(i) {
    frameIdx = i;
    $('slider').value = String(i);
    updateTimeText();
    const label = summary.frames[i];
    const data = await loadFrame(label);
    if (summary.frames[frameIdx] === label) map.getSource('shadow').setData(data);
  }

  $('slider').addEventListener('input', (e) => showFrame(Number(e.target.value)));
  $('showShadow').addEventListener('change', (e) => {
    map.setLayoutProperty('shadow', 'visibility', e.target.checked ? 'visible' : 'none');
  });

  function stop() {
    clearInterval(timer); timer = null;
    $('play').textContent = '▶';
    $('play').setAttribute('aria-label', T[lang].play);
  }
  $('play').addEventListener('click', () => {
    if (timer) { stop(); return; }
    $('play').textContent = '❚❚';
    $('play').setAttribute('aria-label', T[lang].pause);
    timer = setInterval(() => showFrame((frameIdx + 1) % summary.frames.length), 900);
  });

  function fmtMinutes(m) {
    const h = Math.floor(m / 60);
    const mm = Math.round(m % 60);
    if (lang === 'ja') return h ? `${h}時間${mm}分` : `${mm}分`;
    return h ? `${h} h ${mm} min` : `${mm} min`;
  }

  map.on('load', async () => {
    summary = await fetch('data/summary.json').then((r) => r.json());
    $('bigNumber').textContent = `${Math.round(summary.never_sunlit_share * 100)}%`;

    const [w, s, e, n] = summary.bbox;
    map.setMaxBounds([[w - 0.03, s - 0.02], [e + 0.03, n + 0.02]]);

    map.addSource('area', {
      type: 'geojson',
      data: { type: 'Feature', geometry: { type: 'Polygon', coordinates: [[...summary.grid_corners, summary.grid_corners[0]]] } },
    });
    map.addSource('buildings', { type: 'geojson', data: 'data/buildings.geojson' });
    map.addSource('roads', { type: 'geojson', data: 'data/roads.geojson', generateId: true });
    map.addSource('shadow', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addSource('grid', { type: 'image', url: 'data/sun_grid.png', coordinates: summary.grid_corners });

    map.addLayer({ id: 'area-fill', type: 'fill', source: 'area', paint: { 'fill-color': '#f7f8fa' } });
    map.addLayer({
      id: 'roads', type: 'fill', source: 'roads',
      paint: {
        'fill-color': SUN_COLOR,
        'fill-outline-color': ['case', ['boolean', ['feature-state', 'sel'], false], '#1d2733', 'rgba(255,255,255,0.35)'],
      },
    });
    map.addLayer({
      id: 'grid', type: 'raster', source: 'grid',
      layout: { visibility: 'none' },
      paint: { 'raster-resampling': 'nearest', 'raster-fade-duration': 0 },
    });
    map.addLayer({
      id: 'shadow', type: 'fill', source: 'shadow',
      paint: { 'fill-color': '#1b2a44', 'fill-opacity': 0.22 },
    });
    map.addLayer({
      id: 'buildings', type: 'fill', source: 'buildings',
      paint: { 'fill-color': '#d3d7dc', 'fill-outline-color': '#bfc5cc' },
    });
    map.addLayer({
      id: 'road-sel', type: 'line', source: 'roads',
      paint: { 'line-color': '#1d2733', 'line-width': ['case', ['boolean', ['feature-state', 'sel'], false], 2, 0] },
    });
    map.addLayer({
      id: 'area-line', type: 'line', source: 'area',
      paint: { 'line-color': '#8a96a3', 'line-width': 1, 'line-dasharray': [3, 2] },
    });

    PLACES.forEach((p) => {
      const el = document.createElement('div');
      el.className = 'place-label';
      placeMarkers.push({ el, id: p.id });
      new maplibregl.Marker({ element: el }).setLngLat([p.lng, p.lat]).addTo(map);
    });

    const slider = $('slider');
    slider.max = String(summary.frames.length - 1);
    const noon = summary.frames.indexOf('1200');
    applyLang();
    await showFrame(noon >= 0 ? noon : 0);
    summary.frames.forEach((f) => loadFrame(f).catch(() => {}));

    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: '280px' });
    let selected = null;
    map.on('click', 'roads', (ev) => {
      const f = ev.features[0];
      if (selected !== null) map.setFeatureState({ source: 'roads', id: selected }, { sel: false });
      selected = f.id;
      map.setFeatureState({ source: 'roads', id: selected }, { sel: true });
      const p = f.properties;
      const t = T[lang];
      const name = lang === 'en' ? (p.name_en || p.name_ja) : p.name_ja;
      const nameHtml = name
        ? `<div class="pop-name">${escapeHtml(name)}</div>`
        : `<div class="pop-name none">${t.unnamed}</div>`;
      popup.setLngLat(ev.lngLat).setHTML(
        `${nameHtml}
         <div class="pop-row"><span>${t.sunMin}</span><b>${fmtMinutes(p.sun_min)}</b></div>
         <div class="pop-row"><span>${t.dark}</span><b>${Number(p.dark_pct).toFixed(0)}%</b></div>
         <div class="pop-row"><span>${t.area}</span><b>${Number(p.area_m2).toLocaleString()} m²</b></div>`,
      ).addTo(map);
    });
    popup.on('close', () => {
      if (selected !== null) map.setFeatureState({ source: 'roads', id: selected }, { sel: false });
      selected = null;
    });
    map.on('mouseenter', 'roads', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'roads', () => { map.getCanvas().style.cursor = ''; });
  });

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  applyLang();
})();
