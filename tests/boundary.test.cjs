/* Boundary progressive-enhancement checks, without a browser or packages. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(value = '') {
    this.value = value;
    this.textContent = '';
    this.dataset = {};
    this.hidden = false;
    this.children = [];
    this.listeners = new Map();
  }
  addEventListener(event, handler) {
    if (!this.listeners.has(event)) this.listeners.set(event, []);
    this.listeners.get(event).push(handler);
  }
  dispatch(event) { for (const handler of this.listeners.get(event) || []) handler({target: this}); }
  replaceChildren(...children) { this.children = children; }
}

const square = {type: 'Polygon', coordinates: [[[89, 24], [89.001, 24], [89.001, 24.001], [89, 24.001], [89, 24]]]};
const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'boundary.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));

function runBoundary({value = '', leaflet = true, mounted = true} = {}) {
  const input = new Element(value);
  const element = new Element();
  element.dataset = {lat: '24.3745', lon: '88.6042'};
  const fallback = new Element();
  fallback.textContent = 'Map unavailable? Enter the GeoJSON coordinates below.';
  element.children = [fallback];
  const status = new Element();
  status.dataset = {corners: 'Corners', closed: 'Boundary closed. Save to calculate its area.', failed: 'Tiles unavailable; coordinates still work.'};
  const controls = new Element();
  controls.hidden = true;
  const buttons = new Map(['close', 'undo', 'clear'].map(action => {
    const button = new Element();
    button.dataset.boundaryAction = action;
    return [action, button];
  }));
  const elements = new Map([['boundary-map', mounted ? element : null], ['id_geometry', input], ['boundary-status', status]]);
  const document = {
    getElementById: id => elements.get(id) || null,
    querySelector: selector => selector === '.boundary-controls' ? controls : null,
    querySelectorAll: selector => selector === '[data-boundary-action]' ? [...buttons.values()] : [],
  };
  const mapEvents = new Map();
  const tileEvents = new Map();
  const calls = {views: [], fits: [], layers: [], removed: [], tiles: [], markers: []};
  const map = {
    setView(point, zoom) { calls.views.push({point: plain(point), zoom}); return this; },
    fitBounds(bounds, options) { calls.fits.push({bounds, options}); return this; },
    on(event, handler) { mapEvents.set(event, handler); return this; },
    removeLayer(layer) { calls.removed.push(layer); return this; },
  };
  function shape(kind, points, options) {
    const layer = {
      kind, points: plain(points), options: plain(options),
      addTo(target) { assert.equal(target, map); calls.layers.push(this); return this; },
      getBounds() { return {points: this.points}; },
    };
    return layer;
  }
  const window = {};
  if (leaflet) window.L = {
    map(target, options) { assert.equal(target, element); calls.mapOptions = plain(options); return map; },
    tileLayer(url, options) {
      calls.tiles.push({url, options: plain(options)});
      return {
        on(event, handler) { tileEvents.set(event, handler); return this; },
        addTo(target) { assert.equal(target, map); calls.tileHandlersAtAdd = [...tileEvents.keys()]; return this; },
      };
    },
    circleMarker(point, options) { calls.markers.push({point: plain(point), options: plain(options)}); return {addTo: () => ({})}; },
    polygon: (points, options) => shape('polygon', points, options),
    polyline: (points, options) => shape('polyline', points, options),
  };
  vm.runInNewContext(source, {window, document}, {filename: 'static/js/boundary.js'});
  return {input, element, fallback, status, controls, calls,
    latest: () => calls.layers.at(-1),
    click(lat, lng) { mapEvents.get('click')({latlng: {lat, lng}}); },
    action(action) { buttons.get(action).dispatch('click'); },
    tileError() { tileEvents.get('tileerror')({}); },
    manual(value) { input.value = value; input.dispatch('change'); },
  };
}

test('saved boundary loads longitude-first GeoJSON as a closed map outline without rewriting it', () => {
  const original = JSON.stringify(square, null, 2);
  const state = runBoundary({value: original});
  assert.equal(state.input.value, original);
  assert.equal(state.latest().kind, 'polygon');
  assert.deepEqual(state.latest().points, [[24, 89], [24, 89.001], [24.001, 89.001], [24.001, 89]]);
  assert.equal(state.calls.fits.length, 1);
  assert.equal(state.status.textContent, state.status.dataset.closed);
  assert.equal(state.controls.hidden, false);
});

test('map clicks and Close boundary serialize closed longitude-first coordinates and prevent extra corners', () => {
  const state = runBoundary();
  state.click(24.123456789, 89.123456789);
  state.click(24.123456789, 89.124456789);
  state.click(24.124456789, 89.124456789);
  assert.equal(state.latest().kind, 'polyline');
  assert.equal(state.status.textContent, 'Corners: 3');
  state.action('close');
  assert.equal(state.latest().kind, 'polygon');
  const geometry = JSON.parse(state.input.value);
  assert.deepEqual(geometry.coordinates[0], [[89.1234568, 24.1234568], [89.1244568, 24.1234568], [89.1244568, 24.1244568], [89.1234568, 24.1234568]]);
  const closed = state.input.value;
  state.click(24.5, 89.5);
  assert.equal(state.input.value, closed);
});

test('Close needs at least three corners, Undo reopens the shape, and Clear resets only the drawing', () => {
  const state = runBoundary();
  state.click(24, 89);
  state.click(24, 89.001);
  state.action('close');
  assert.equal(state.latest().kind, 'polyline');
  state.click(24.001, 89.001);
  state.action('close');
  state.action('undo');
  assert.equal(state.latest().kind, 'polyline');
  assert.equal(state.latest().points.length, 2);
  state.click(24.002, 89.002);
  state.action('close');
  assert.equal(JSON.parse(state.input.value).coordinates[0][2][0], 89.002);
  state.action('clear');
  assert.equal(state.input.value, '');
  assert.deepEqual(state.latest().points, []);
  assert.equal(state.status.textContent, 'Corners: 0');
  assert.equal(state.calls.markers.length, 1, 'The farm location reference remains available');
});

test('valid manual GeoJSON updates the outline and invalid text never displays an old saved shape', () => {
  const state = runBoundary({value: JSON.stringify(square)});
  const triangle = {type: 'Polygon', coordinates: [[[90, 25], [90.001, 25], [90, 25.001], [90, 25]]]};
  const manual = JSON.stringify(triangle, null, 2);
  state.manual(manual);
  assert.equal(state.input.value, manual);
  assert.deepEqual(state.latest().points, [[25, 90], [25, 90.001], [25.001, 90]]);
  assert.equal(state.calls.fits.length, 2);
  for (const invalid of ['{invalid', '', JSON.stringify({...square, coordinates: [square.coordinates[0], square.coordinates[0]]}), JSON.stringify({type: 'Polygon', coordinates: [square.coordinates[0].slice(0, -1)]}), JSON.stringify({type: 'Polygon', coordinates: [[[179, 24], [179.1, 24], [179, 24.1], [179, 24]]]})]) {
    state.manual(invalid);
    assert.equal(state.input.value, invalid, 'Keep manual input for server validation');
    assert.deepEqual(state.latest().points, []);
    assert.equal(state.status.textContent, 'Corners: 0');
  }
});

test('missing Leaflet preserves manual input, the fallback message and hidden drawing controls', () => {
  const value = JSON.stringify(square);
  const state = runBoundary({leaflet: false, value});
  assert.equal(state.input.value, value);
  assert.equal(state.element.children[0], state.fallback);
  assert.equal(state.controls.hidden, true);
  assert.equal(state.calls.tiles.length, 0);
  state.manual('{manual coordinates remain editable}');
  assert.equal(state.input.value, '{manual coordinates remain editable}');
  assert.doesNotThrow(() => runBoundary({mounted: false}));
});

test('tile failure preserves the boundary and coordinate editing without changing OSM attribution policy', () => {
  const state = runBoundary({value: JSON.stringify(square)});
  const before = state.input.value;
  state.tileError();
  assert.equal(state.status.textContent, state.status.dataset.failed);
  assert.equal(state.input.value, before);
  assert.equal(state.latest().kind, 'polygon');
  state.action('undo');
  state.click(24.002, 89.002);
  state.action('close');
  assert.notEqual(state.input.value, before);
  assert.equal(state.latest().kind, 'polygon');
  assert.equal(state.calls.tiles[0].url, 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
  assert.equal(state.calls.tiles[0].options.referrerPolicy, 'strict-origin-when-cross-origin');
  assert.match(state.calls.tiles[0].options.attribution, /OpenStreetMap/);
  assert.ok(state.calls.tileHandlersAtAdd.includes('tileerror'));
});

test('drawing stops at the server-supported five hundred corners', () => {
  const state = runBoundary();
  for (let i = 0; i < 502; i++) state.click(24 + i / 100000, 89 + i / 100000);
  assert.equal(state.latest().points.length, 500);
  state.action('close');
  assert.equal(JSON.parse(state.input.value).coordinates[0].length, 501);
});
