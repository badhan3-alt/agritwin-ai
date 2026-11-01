(() => {
  'use strict';
  const element = document.getElementById('boundary-map');
  const input = document.getElementById('id_geometry');
  const status = document.getElementById('boundary-status');
  if (!element || !input || !window.L) return;
  const L = window.L;
  let vertices = [];
  let closed = false;
  let layer;
  let map;
  const parse = () => {
    try {
      const value = JSON.parse(input.value);
      const ring = value?.type === 'Polygon' && Array.isArray(value.coordinates) && value.coordinates.length === 1 && value.coordinates[0];
      if (!Array.isArray(ring) || ring.length < 4 || ring.length > 501 || ring.some(p => !Array.isArray(p) || p.length !== 2 || p.some(v => typeof v !== 'number' || !Number.isFinite(v)) || p[0] < 88 || p[0] > 92.8 || p[1] < 20.5 || p[1] > 26.7)) return false;
      if (ring[0][0] !== ring[ring.length - 1][0] || ring[0][1] !== ring[ring.length - 1][1]) return false;
      vertices = ring.slice(0, -1).map(([lon, lat]) => [lat, lon]);
      closed = true;
      return true;
    } catch (_) { return false; }
  };
  const draw = (sync = true) => {
    if (layer) map.removeLayer(layer);
    layer = closed && vertices.length >= 3 ? L.polygon(vertices, {color:'#173d32', fillColor:'#d6eaa2', fillOpacity:.5}).addTo(map) : L.polyline(vertices, {color:'#173d32'}).addTo(map);
    if (sync) {
      const ring = vertices.map(([lat, lon]) => [lon, lat]);
      if (ring.length) ring.push([...ring[0]]);
      input.value = vertices.length ? JSON.stringify({type:'Polygon', coordinates:[ring]}) : '';
    }
    status.textContent = closed ? status.dataset.closed : `${status.dataset.corners}: ${vertices.length}`;
  };
  try {
    element.replaceChildren();
    map = L.map(element, {scrollWheelZoom:false}).setView([Number(element.dataset.lat),Number(element.dataset.lon)], 16);
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,referrerPolicy:'strict-origin-when-cross-origin',attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'});
    tiles.on('tileerror', () => {status.textContent = status.dataset.failed;});
    tiles.addTo(map);
    L.circleMarker([Number(element.dataset.lat),Number(element.dataset.lon)], {radius:4,color:'#815719'}).addTo(map);
    if (parse()) {draw(false); map.fitBounds(layer.getBounds(), {padding:[30,30],maxZoom:18});}
    map.on('click', event => {
      if (closed || vertices.length >= 500) return;
      vertices.push([Number(event.latlng.lat.toFixed(7)),Number(event.latlng.lng.toFixed(7))]);
      draw();
    });
    document.querySelector('.boundary-controls').hidden = false;
    document.querySelectorAll('[data-boundary-action]').forEach(button => button.addEventListener('click', () => {
      const action = button.dataset.boundaryAction;
      if (action === 'close') { if (vertices.length < 3) return; closed = true; }
      if (action === 'undo') { closed = false; vertices.pop(); }
      if (action === 'clear') { closed = false; vertices = []; }
      draw();
    }));
    input.addEventListener('change', () => {
      if (parse()) {
        draw(false);
        map.fitBounds(layer.getBounds(), {padding:[30,30],maxZoom:18});
      } else {
        // Never show a previous valid shape as the current manual input.
        // Keep invalid text intact so server validation can explain the issue.
        vertices = [];
        closed = false;
        draw(false);
      }
    });
  } catch (_) { status.textContent = status.dataset.failed; }
})();
