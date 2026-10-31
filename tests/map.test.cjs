/* Run with: node --test tests/map.test.cjs. No browser or packages required. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Element {
  constructor(tag = 'div', value = '') {
    this.tagName = tag.toUpperCase();
    this.value = value;
    this.className = '';
    this.textContent = '';
    this.children = [];
    this.attributes = new Map();
    this.listeners = new Map();
    this.style = {};
    this.dataset = {};
    this.classList = {
      add: (...names) => { this.className = [...new Set([...this.className.split(/\s+/).filter(Boolean), ...names])].join(' '); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter(name => !names.includes(name)).join(' '); },
      contains: name => this.className.split(/\s+/).includes(name),
    };
  }
  addEventListener(event, listener) {
    if (!this.listeners.has(event)) this.listeners.set(event, []);
    this.listeners.get(event).push(listener);
  }
  dispatch(event) {
    for (const listener of this.listeners.get(event) || []) listener({target: this});
  }
  setAttribute(name, value) { this.attributes.set(name, value); }
  getAttribute(name) { return this.attributes.get(name); }
  replaceChildren(...children) { this.children = children; }
  appendChild(child) { this.children.push(child); return child; }
  querySelector(selector) {
    for (const child of this.children) {
      if (selector.startsWith('.') ? child.classList.contains(selector.slice(1)) : child.tagName === selector.toUpperCase()) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
}

function runMap({leaflet = true, language = 'en', translations = {}} = {}) {
  const latitude = new Element('input', '24.3745');
  const longitude = new Element('input', '88.6042');
  const region = new Element('select', '');
  const location = new Element('input', 'Rajshahi');
  const regions = new Element('script');
  regions.textContent = JSON.stringify([{id: 'rangpur', name: 'Rangpur', district_bn: 'রংপুর', division_bn: 'রংপুর', lat: 25.7439, lon: 89.2752}]);
  const translated = new Element('script');
  translated.textContent = JSON.stringify(translations);
  const fallback = new Element();
  fallback.className = 'map-fallback';
  const title = new Element('strong');
  title.textContent = 'Your location, your starting point.';
  const explanation = new Element('p');
  explanation.textContent = 'Choose a region or enter coordinates.';
  fallback.replaceChildren(title, explanation);
  const mapElement = new Element();
  mapElement.replaceChildren(fallback);
  const mapHelp = new Element();
  mapHelp.className = 'map-help';
  mapHelp.textContent = 'Click the map to update coordinates.';
  const farmForm = new Element('form');
  farmForm.replaceChildren(mapElement, mapHelp);
  const elements = new Map([
    ['id_latitude', latitude], ['id_longitude', longitude], ['id_region', region],
    ['id_location_name', location], ['regions-data', regions], ['farm-map', mapElement],
    ['app-translations', translated],
  ]);
  const document = {
    documentElement: {lang: language},
    querySelector: selector => selector === '[data-farm-form]' ? farmForm : null,
    querySelectorAll: () => [],
    getElementById: id => elements.get(id) || null,
    createElement: tag => new Element(tag),
  };
  const timers = new Map();
  let timerId = 0;
  const setTimeout = (callback, delay) => { const id = ++timerId; timers.set(id, {callback, delay}); return id; };
  const clearTimeout = id => timers.delete(id);
  const mapEvents = new Map();
  const tileEvents = new Map();
  const markerEvents = new Map();
  const calls = {map: [], tiles: [], layers: [], marker: [], remove: 0, handlersAtAdd: []};
  let markerLocation;
  let removed = false;
  const map = {
    setView(coords, zoom) { assert.equal(removed, false, 'A failed map must not be reused'); calls.map.push({coords: [...coords], zoom}); return this; },
    getZoom() { assert.equal(removed, false); return 9; },
    on(event, handler) { mapEvents.set(event, handler); return this; },
    remove() { calls.remove++; removed = true; },
  };
  const layer = {
    on(event, handler) { tileEvents.set(event, handler); return this; },
    addTo(target) { calls.layers.push(target); calls.handlersAtAdd = [...tileEvents.keys()]; return this; },
  };
  const marker = {
    addTo() { return this; },
    setLatLng(coords) { assert.equal(removed, false, 'A removed marker must not be reused'); markerLocation = Array.isArray(coords) ? {lat: coords[0], lng: coords[1]} : coords; return this; },
    getLatLng() { return markerLocation; },
    on(event, handler) { markerEvents.set(event, handler); return this; },
  };
  const window = {setTimeout, clearTimeout, addEventListener() {}};
  if (leaflet) window.L = {
    map(canvas, options) { calls.mapCanvas = canvas; calls.mapOptions = options; return map; },
    tileLayer(url, options) { calls.tiles.push({url, options}); return layer; },
    marker(coords, options) { markerLocation = {lat: coords[0], lng: coords[1]}; calls.marker.push({coords: [...coords], options}); return marker; },
  };
  const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'app.js'), 'utf8');
  vm.runInNewContext(source, {window, document, setTimeout, clearTimeout}, {filename: 'static/js/app.js'});
  return {latitude, longitude, region, location, fallback, title, explanation, mapElement, mapHelp,
    calls, timers, mapEvents, markerEvents, tileEvents,
    emitTile: event => { const handler = tileEvents.get(event); assert.equal(typeof handler, 'function', `${event} must have a handler`); handler({}); },
  };
}

function checkCoordinateEntryStillWorks(state) {
  state.region.value = 'rangpur';
  state.region.dispatch('change');
  assert.equal(Number(state.latitude.value), 25.7439);
  assert.equal(Number(state.longitude.value), 89.2752);
  assert.equal(state.location.value, 'Rangpur');
  state.latitude.value = '24.9000';
  state.longitude.value = '89.1000';
  state.latitude.dispatch('change');
  state.longitude.dispatch('change');
  assert.equal(state.region.value, '');
  assert.equal(state.latitude.value, '24.9000');
  assert.equal(state.longitude.value, '89.1000');
}

test('map requests canonical OSM tiles with an origin-only cross-site referrer', () => {
  const state = runMap();
  assert.equal(state.calls.tiles.length, 1);
  assert.equal(state.calls.tiles[0].url, 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
  assert.equal(state.calls.tiles[0].options.referrerPolicy, 'strict-origin-when-cross-origin');
  assert.match(state.calls.tiles[0].options.attribution, /OpenStreetMap/);
  assert.equal(state.calls.mapOptions.scrollWheelZoom, false);
  assert.equal(state.calls.mapCanvas.className, 'map-canvas');
  assert.equal(state.mapElement.children[0], state.calls.mapCanvas);
  assert.ok(state.calls.handlersAtAdd.includes('tileerror'));
  assert.ok(state.calls.handlersAtAdd.includes('tileload'));
  state.mapEvents.get('click')({latlng: {lat: 24.5, lng: 88.7}});
  assert.equal(state.latitude.value, '24.5000');
  assert.equal(state.longitude.value, '88.7000');
});

test('tile failure restores a clear fallback and preserves working farm controls', () => {
  const state = runMap();
  state.latitude.value = '24.9876';
  state.longitude.value = '88.4567';
  state.emitTile('tileerror');
  assert.equal(state.calls.remove, 1);
  assert.equal(state.mapElement.children[0], state.fallback);
  assert.equal(state.fallback.getAttribute('role'), 'status');
  assert.match(`${state.title.textContent} ${state.explanation.textContent}`, /unavailable|could not|cannot/i);
  assert.match(state.mapHelp.textContent, /coordinates|region/i);
  assert.equal(state.latitude.value, '24.9876');
  assert.equal(state.longitude.value, '88.4567');
  assert.equal(state.timers.size, 0);
  checkCoordinateEntryStillWorks(state);
});

test('an unresponsive tile service times out without losing the farm location', () => {
  const state = runMap();
  const startupTimer = [...state.timers.values()].find(timer => timer.delay === 12000);
  assert.ok(startupTimer, 'Map startup must be bounded when the network never answers');
  startupTimer.callback();
  assert.equal(state.calls.remove, 1);
  assert.equal(state.mapElement.children[0], state.fallback);
  assert.equal(state.latitude.value, '24.3745');
  assert.equal(state.longitude.value, '88.6042');
  checkCoordinateEntryStillWorks(state);
});

test('a loaded tile cancels startup timeout and keeps the interactive map', () => {
  const state = runMap();
  assert.ok([...state.timers.values()].some(timer => timer.delay === 12000));
  state.emitTile('tileload');
  assert.equal(state.timers.size, 0);
  assert.equal(state.calls.remove, 0);
  assert.equal(state.mapElement.children[0], state.calls.mapCanvas);
  checkCoordinateEntryStillWorks(state);
});

test('missing Leaflet leaves the original fallback and coordinate entry available', () => {
  const state = runMap({leaflet: false});
  assert.equal(state.calls.tiles.length, 0);
  assert.equal(state.mapElement.children[0], state.fallback);
  assert.equal(state.timers.size, 0);
  checkCoordinateEntryStillWorks(state);
});

test('Bangla mode localizes map messages and location input while keeping numeric coordinates', () => {
  const state = runMap({language: 'bn', translations: {
    basemap_unavailable: 'এখন মানচিত্র দেখা যাচ্ছে না।',
    basemap_help: 'জেলা বেছে নিন অথবা অক্ষাংশ ও দ্রাঘিমাংশ লিখুন।',
    coordinates_help: 'আপনার অবস্থানের তথ্য সংরক্ষিত আছে।',
  }});
  state.emitTile('tileerror');
  assert.equal(state.title.textContent, 'এখন মানচিত্র দেখা যাচ্ছে না।');
  assert.equal(state.explanation.textContent, 'জেলা বেছে নিন অথবা অক্ষাংশ ও দ্রাঘিমাংশ লিখুন।');
  assert.equal(state.mapHelp.textContent, 'আপনার অবস্থানের তথ্য সংরক্ষিত আছে।');
  state.region.value = 'rangpur';
  state.region.dispatch('change');
  assert.equal(state.location.value, 'রংপুর, রংপুর বিভাগ, বাংলাদেশ');
  assert.equal(Number(state.latitude.value), 25.7439);
  assert.equal(Number(state.longitude.value), 89.2752);
});
