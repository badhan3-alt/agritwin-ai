/* Each card shows its saved coordinates; maps never change the farm profile. */
(() => {
  'use strict';
  const initialize = container => {
    const fallback = container.querySelector('.farm-map-fallback');
    const canvas = container.querySelector('.farm-map-canvas');
    const lat = Number(container.dataset.lat);
    const lon = Number(container.dataset.lon);
    let map;
    let timeout;
    let loaded = false;
    const unavailable = () => {
      window.clearTimeout(timeout);
      if (loaded) return;
      if (map) { map.remove(); map = null; }
      canvas.hidden = true;
      fallback.hidden = false;
      fallback.setAttribute('role', 'status');
      fallback.querySelector('strong').textContent = container.dataset.unavailable;
      container.dataset.mapState = 'unavailable';
    };
    if (!window.L || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
      unavailable();
      return;
    }
    try {
      canvas.hidden = false;
      map = window.L.map(canvas, {scrollWheelZoom: false, zoomControl: false}).setView([lat, lon], 14);
      window.L.control.zoom({zoomInTitle: container.dataset.zoomIn, zoomOutTitle: container.dataset.zoomOut}).addTo(map);
      window.L.circleMarker([lat, lon], {radius: 9, color: '#173d32', weight: 3, fillColor: '#d6eaa2', fillOpacity: 1, interactive: false}).addTo(map);
      const tiles = window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        referrerPolicy: 'strict-origin-when-cross-origin',
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      });
      tiles.on('tileload', () => {
        // A removed map must not be revived by a late image response.
        if (!map) return;
        loaded = true;
        window.clearTimeout(timeout);
        fallback.hidden = true;
        container.dataset.mapState = 'ready';
      });
      tiles.on('tileerror', unavailable);
      timeout = window.setTimeout(unavailable, 12000);
      tiles.addTo(map);
    } catch (_) { unavailable(); }
  };
  const maps = document.querySelectorAll('[data-farm-map]');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      observer.unobserve(entry.target);
      initialize(entry.target);
    }));
    maps.forEach(map => observer.observe(map));
  } else maps.forEach(initialize);
})();
