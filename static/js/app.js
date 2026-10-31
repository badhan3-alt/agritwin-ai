/* Progressive enhancement only: all forms and analysis work without JavaScript. */
(() => {
  'use strict';
  let translations = {};
  try {
    const data = document.getElementById('app-translations');
    translations = data ? JSON.parse(data.textContent) : {};
  } catch (_) { /* Standard form requests remain available. */ }
  const text = (key, fallback) => translations[key] || fallback;
  const bangla = document.documentElement?.lang === 'bn';
  const number = (value, decimals = 1) => new Intl.NumberFormat(bangla ? 'bn-BD' : 'en-US', {maximumFractionDigits: decimals, useGrouping: false}).format(value);
  const menu = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (menu && sidebar) {
    const closeMenu = () => { sidebar.classList.remove('is-open'); menu.setAttribute('aria-expanded', 'false'); };
    const close = sidebar.querySelector('.nav-close');
    if (close) close.addEventListener('click', () => { closeMenu(); menu.focus(); });
    menu.addEventListener('click', () => {
      const open = sidebar.classList.toggle('is-open');
      menu.setAttribute('aria-expanded', String(open));
    });
    document.addEventListener('click', event => {
      if (!sidebar.contains(event.target) && !menu.contains(event.target)) closeMenu();
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') { closeMenu(); menu.focus(); } });
  }

  document.querySelectorAll('[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
  document.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => window.print()));
  const pendingButtons = new Map();
  document.querySelectorAll('[data-loading-form], [data-farm-form], .demo-entry form').forEach(form => form.addEventListener('submit', event => {
    if (event.defaultPrevented) return;
    const button = event.submitter || form.querySelector('button[type="submit"]');
    if (!button || button.disabled) return;
    pendingButtons.set(button, button.innerHTML);
    const spinner = document.createElement('span');
    spinner.className = 'loading-spinner';
    spinner.setAttribute('aria-hidden', 'true');
    const status = document.createElement('span');
    status.className = 'visually-hidden';
    status.setAttribute('role', 'status');
    status.textContent = text('working', 'Working…');
    button.prepend(spinner);
    button.append(status);
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
  }));
  window.addEventListener('pageshow', () => {
    pendingButtons.forEach((markup, button) => {
      button.innerHTML = markup;
      button.disabled = false;
      button.removeAttribute('aria-busy');
    });
    pendingButtons.clear();
  });
  const errors = document.getElementById('farm-form-errors');
  if (errors) errors.focus();
  document.querySelectorAll('[data-range-output]').forEach(output => {
    const input = document.getElementById(output.dataset.rangeOutput);
    if (!input) return;
    const update = () => {
      const value = Number(input.value);
      output.textContent = `${value > 0 ? '+' : ''}${Number.isFinite(value) ? number(value) : input.value}${output.dataset.suffix || ''}`;
    };
    input.addEventListener('input', update);
    update();
  });

  const farmForm = document.querySelector('[data-farm-form]');
  if (farmForm) {
    const latitude = document.getElementById('id_latitude');
    const longitude = document.getElementById('id_longitude');
    const region = document.getElementById('id_region');
    const locationName = document.getElementById('id_location_name');
    const regionData = document.getElementById('regions-data');
    let regions = [];
    try { regions = JSON.parse(regionData ? regionData.textContent : '[]'); } catch (_) { /* manual coordinates remain usable */ }
    if (!Array.isArray(regions)) regions = Object.entries(regions).map(([id, value]) => ({id, ...value}));
    let map;
    let marker;
    const point = () => {
      const lat = Number(latitude && latitude.value);
      const lon = Number(longitude && longitude.value);
      return Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180 ? [lat, lon] : null;
    };
    const updateMap = () => { const coords = point(); if (map && marker && coords) { marker.setLatLng(coords); map.setView(coords, Math.max(map.getZoom(), 8)); } };
    if (region) region.addEventListener('change', () => {
      const selected = regions.find(item => String(item.id) === region.value);
      if (!selected) return;
      if (latitude) latitude.value = selected.lat;
      if (longitude) longitude.value = selected.lon;
      if (locationName) locationName.value = bangla && selected.district_bn && selected.division_bn ? `${selected.district_bn}, ${selected.division_bn} বিভাগ, বাংলাদেশ` : selected.name;
      updateMap();
    });
    [latitude, longitude].filter(Boolean).forEach(input => input.addEventListener('change', () => {
      if (region) region.value = '';
      updateMap();
    }));
    const mapElement = document.getElementById('farm-map');
    if (mapElement && window.L && latitude && longitude) {
      const fallback = mapElement.querySelector('.map-fallback');
      const mapHelp = farmForm.querySelector('.map-help');
      const canvas = document.createElement('div');
      canvas.className = 'map-canvas';
      let startupTimeout;
      let unavailable = false;
      const showFallback = () => {
        if (unavailable) return;
        unavailable = true;
        window.clearTimeout(startupTimeout);
        if (map) map.remove();
        map = null;
        marker = null;
        if (fallback) {
          fallback.setAttribute('role', 'status');
          fallback.querySelector('strong').textContent = text('basemap_unavailable', 'The basemap is unavailable right now.');
          fallback.querySelector('p').textContent = text('basemap_help', 'Choose a region above or enter latitude and longitude. You can save and analyze your farm without the map.');
          mapElement.replaceChildren(fallback);
        }
        if (mapHelp) mapHelp.textContent = text('coordinates_help', 'Your coordinates are preserved. Choose a region or enter coordinates to continue.');
      };
      const initial = point() || [24.3745, 88.6042];
      try {
        mapElement.replaceChildren(canvas);
        map = window.L.map(canvas, { scrollWheelZoom: false }).setView(initial, 9);
        const tiles = window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 18,
          // OSM requires a Referer. Override Django's same-origin policy only
          // for tile images, sending our origin without page paths or queries.
          referrerPolicy: 'strict-origin-when-cross-origin',
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        });
        tiles.on('tileerror', showFallback);
        tiles.on('tileload', () => window.clearTimeout(startupTimeout));
        marker = window.L.marker(initial, { draggable: true }).addTo(map);
        const selectPoint = coords => {
          latitude.value = coords.lat.toFixed(4);
          longitude.value = coords.lng.toFixed(4);
          marker.setLatLng(coords);
          if (region) region.value = '';
        };
        map.on('click', event => selectPoint(event.latlng));
        marker.on('dragend', () => selectPoint(marker.getLatLng()));
        startupTimeout = window.setTimeout(showFallback, 12000);
        tiles.addTo(map);
      } catch (_) {
        showFallback();
      }
    }
  }

  const namespace = 'http://www.w3.org/2000/svg';
  const svgNode = (tag, attributes, text) => {
    const element = document.createElementNS(namespace, tag);
    Object.entries(attributes || {}).forEach(([key, value]) => element.setAttribute(key, value));
    if (text !== undefined) element.textContent = text;
    return element;
  };
  document.querySelectorAll('[data-climate-chart]').forEach(container => {
    const dataNode = document.getElementById(container.dataset.source);
    if (!dataNode) return;
    let data;
    try { data = JSON.parse(dataNode.textContent); } catch (_) { return; }
    if (!Array.isArray(data) || !data.length) return;
    const render = () => {
      const width = Math.max(container.clientWidth || 600, 280);
      const height = container.clientHeight || 270;
      const compact = width < 400;
      const left = compact ? 30 : 37;
      const right = compact ? 24 : 33;
      const top = 27;
      const bottom = 31;
      const plotWidth = width - left - right;
      const plotHeight = height - top - bottom;
      const rainfallMax = Math.max(...data.map(item => Number(item.precip_mm) || 0), 100);
      const rainScale = Math.ceil(rainfallMax / 100) * 100;
      const temperatureMax = Math.max(40, Math.ceil(Math.max(...data.map(item => Number(item.temp_mean_c) || 0)) / 10) * 10);
      const step = plotWidth / data.length;
      const svg = svgNode('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': text('chart_label', 'Monthly precipitation bars and mean temperature line. The full values appear in the data table below.')});
      svg.appendChild(svgNode('title', {}, text('chart_title', 'Monthly rainfall and mean temperature')));
      const textStyle = {fill: '#748568', 'font-family': 'inherit', 'font-size': compact ? '10' : '11'};
      for (let index = 0; index <= 4; index++) {
        const y = top + plotHeight - (plotHeight * index / 4);
        svg.appendChild(svgNode('line', {x1:left, x2:width-right, y1:y, y2:y, stroke:'#e9eedf', 'stroke-width':1, 'stroke-dasharray':index ? '3 4' : ''}));
        svg.appendChild(svgNode('text', {...textStyle, x:left-8, y:y+3, 'text-anchor':'end'}, number(Math.round(rainScale * index / 4), 0)));
        svg.appendChild(svgNode('text', {...textStyle, x:width-right+6, y:y+3}, number(Math.round(temperatureMax * index / 4), 0)));
      }
      svg.appendChild(svgNode('text', {...textStyle, x:left-5, y:12, 'text-anchor':'end'}, text('rain_unit', 'mm')));
      svg.appendChild(svgNode('text', {...textStyle, x:width-right+5, y:12}, text('temp_unit', '°C')));
      const points = [];
      data.forEach((item, index) => {
        const x = left + step * (index + .5);
        const rain = Math.max(0, Number(item.precip_mm) || 0);
        const barHeight = rain / rainScale * plotHeight;
        const bar = svgNode('rect', {x:x-step*.24, y:top+plotHeight-barHeight, width:step*.48, height:barHeight, rx:3, fill:'#b2c48d'});
        const monthName = translations.month_names?.[item.month_code] || item.month_name;
        bar.appendChild(svgNode('title', {}, `${monthName}: ${number(rain)} ${text('rain_unit', 'mm')} ${text('rainfall', 'precipitation')}`));
        svg.appendChild(bar);
        const label = compact && index % 2 ? '' : (translations.months?.[item.month_code] || String(item.month_name || item.month_code).slice(0,3));
        svg.appendChild(svgNode('text', {...textStyle, x, y:height-10, 'text-anchor':'middle'}, label));
        points.push([x, top + plotHeight - ((Number(item.temp_mean_c) || 0) / temperatureMax * plotHeight)]);
      });
      svg.appendChild(svgNode('polyline', {points:points.map(point=>point.join(',')).join(' '), fill:'none', stroke:'#5b7e4e', 'stroke-width':2, 'stroke-linejoin':'round'}));
      points.forEach((point,index) => {
        const circle = svgNode('circle', {cx:point[0], cy:point[1], r:3, fill:'#fdfef8', stroke:'#5b7e4e', 'stroke-width':1.5});
        const monthName = translations.month_names?.[data[index].month_code] || data[index].month_name;
        circle.appendChild(svgNode('title', {}, `${monthName}: ${number(Number(data[index].temp_mean_c))}${text('temp_unit', '°C')} ${text('temperature', 'mean temperature')}`));
        svg.appendChild(circle);
      });
      container.replaceChildren(svg);
    };
    render();
    if ('ResizeObserver' in window) new ResizeObserver(render).observe(container);
    else window.addEventListener('resize', render, {passive:true});
  });
})();
