import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { typescriptLoader } from './load-ts.mjs';

const load = typescriptLoader();
const core = load('i18n/core.ts');
const { en } = load('i18n/en.ts');
const { tr } = load('i18n/tr.ts');
const { localizeSession, localizeEvent, backendText } = load('i18n/backend.ts');
const { I18nProvider } = load('i18n/index.tsx');
const fixture = JSON.parse(readFileSync(new URL('./fixtures/tutorial-session.json', import.meta.url), 'utf8'));
function storage(locale = null) {
  const data = new Map(locale ? [['plantops.locale', locale]] : []);
  const store = { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) };
  globalThis.window = { localStorage: store, sessionStorage: store, matchMedia: () => ({ matches: true }) };
  return data;
}

test('English is the default; valid Turkish survives reload and unsupported values do not', () => {
  storage(); assert.equal(core.readLocale(), 'en');
  for (const invalid of ['TR', 'fr', 'null', '{broken']) { storage(invalid); assert.equal(core.readLocale(), 'en'); }
  const data = storage(); core.persistLocale('tr');
  assert.equal(data.get('plantops.locale'), 'tr');
  assert.equal(core.readLocale(), 'tr');
  assert.equal(core.translate(core.readLocale(), 'Start your shift'), 'Vardiyanı başlat');
  core.persistLocale('en'); assert.equal(core.readLocale(), 'en');
});

test('denied storage getters and failing reads/writes never block language selection', () => {
  globalThis.window = { get localStorage() { throw Error('SecurityError'); } };
  assert.equal(core.readLocale(), 'en'); assert.doesNotThrow(() => core.persistLocale('tr'));
  globalThis.window = { localStorage: { getItem() { throw Error('denied'); }, setItem() { throw Error('quota'); } } };
  assert.equal(core.readLocale(), 'en'); assert.doesNotThrow(() => core.persistLocale('tr'));
});

test('provider changes existing consumers and document language instantly, even with denied storage', () => {
  storage(); globalThis.document = { documentElement: { lang: 'en' } };
  let state;
  let context;
  const react = { ...React,
    createContext(value) { context = { value, Provider: 'provider' }; return context; },
    useContext: ctx => ctx.value,
    useState(initial) { state ??= typeof initial === 'function' ? initial() : initial; return [state, value => { state = value; }]; },
    useMemo: fn => fn(), useEffect: fn => fn(),
  };
  const local = typescriptLoader({ react });
  const { I18nProvider: Provider, LanguageSelector, useI18n } = local('i18n/index.tsx');
  const render = () => { context.value = Provider({ children: null }).props.value; };
  render(); assert.equal(useI18n().t('Reports'), 'Reports');
  globalThis.window = { get localStorage() { throw Error('denied'); } };
  LanguageSelector().props.onChange({ target: { value: 'tr' } }); render();
  assert.equal(LanguageSelector().props.value, 'tr');
  assert.equal(useI18n().t('Reports'), 'Raporlar');
  assert.equal(useI18n().t('Your name'), 'Adın');
  assert.equal(document.documentElement.lang, 'tr');
  LanguageSelector().props.onChange({ target: { value: 'en' } }); render();
  assert.equal(useI18n().t('Reports'), 'Reports');
  assert.equal(document.documentElement.lang, 'en');
});

test('catalogs have equal key coverage, preserve interpolation and safely fall back', () => {
  assert.deepEqual(Object.keys(tr).sort(), Object.keys(en).sort());
  for (const key of Object.keys(en)) {
    assert.ok(tr[key].length, key);
    const sourceTokens = new Set(en[key].match(/\{\w+\}/g) ?? []);
    const translatedTokens = new Set(tr[key].match(/\{\w+\}/g) ?? []);
    // Turkish does not use English plural suffixes.
    if (key.includes('action{value2}') || key.includes('decision{value2}')) sourceTokens.delete('{value2}');
    assert.deepEqual(translatedTokens, sourceTokens, key);
  }
  assert.equal(core.translate('en', 'Start your shift'), 'Start your shift');
  assert.equal(core.translate('tr', 'Missing runtime key'), 'Missing runtime key');
  assert.equal(core.translate('tr', '__proto__'), '__proto__');
  assert.equal(core.translate('tr', 'Protect {order}', { order: 'ORDER-$&' }), 'ORDER-$& siparişini koru');
  assert.equal(backendText('tr', 'profile.future.title', 'Future English title'), 'Future English title');
  assert.equal(core.knownText('tr', 'Unrecognized English sentence'), 'Unrecognized English sentence');
  assert.equal(core.statusLabel('tr', 'PLANNED_MAINTENANCE'), 'Planlı bakım');
  for (const id of ['LASER-01', 'CNC-01', 'WASH-01', 'ORDER-FIRST', 'laser_01', '/sessions', 'EQUIPMENT_SERVICE_REQUESTED', 'OEE', 'OTIF']) assert.equal(core.statusLabel('tr', id), id);
});

test('backend translations use profile/event identity and leave the engine snapshot untouched', () => {
  const raw = structuredClone(fixture), before = JSON.stringify(raw);
  raw.scenario_profile.title = 'Changed English wording';
  const changed = JSON.stringify(raw);
  const localized = localizeSession(raw, 'tr');
  assert.equal(localized.scenario_profile.title, 'İlk vardiya: kesim koşulu');
  assert.equal(JSON.stringify(raw), changed);
  assert.equal(localized.summary.good_production, raw.summary.good_production);
  assert.equal(localized.event_digest, raw.event_digest);
  assert.equal(localized.scenario_profile.machines[0].id, raw.scenario_profile.machines[0].id);
  assert.equal(localized.summary.machine_metrics.laser_01.state, raw.summary.machine_metrics.laser_01.state);
  assert.equal(localized.scenario_profile.shift_review.scorecard.find(x => x.id === 'cost').value, '0.00 malzeme, bakım, hızlandırma, işçilik ve kontrol');
  assert.equal(localizeSession(raw, 'en'), raw);
  const event = { id: 'SHIFT-01', kind: 'supplier_delay', title: 'New English wording', detail: 'Original detail', zone: 'receiving', state: 'active' };
  assert.equal(localizeEvent('tr', event).title, 'Tedarikçi taşıma aksaması');
  const unknown = { ...event, kind: 'future_event' };
  assert.deepEqual(localizeEvent('tr', unknown), unknown);
  const future = structuredClone(fixture);
  future.scenario_profile.id = 'future-profile';
  assert.equal(localizeSession(future, 'tr').scenario_profile.title, future.scenario_profile.title);
  assert.equal(JSON.stringify(fixture), before);
});

const noop = () => {};
function controlFor(session) {
  return { session, busy: null, error: null, notice: null, connectionHold: false, newShift: noop, restoreSession: noop, toggle: noop, speed: noop, prioritize: noop, purchase: noop, repair: noop, service: noop, maintain: noop, contain: noop, overtime: noop, expeditePurchase: noop };
}
function renderComponent(path, name, props, locale) {
  storage(locale);
  return renderToStaticMarkup(React.createElement(I18nProvider, null, React.createElement(load(path)[name], props)));
}

test('login, navigation, tutorial and every workspace render the selected language', () => {
  const session = localizeSession(fixture, 'tr'), control = controlFor(session);
  const cases = [
    ['components/LoginScreen.tsx', 'LoginScreen', { control: controlFor(null), replay: noop }, 'Vardiyanı başlat'],
    ['components/ControlBar.tsx', 'ControlBar', { control }, 'Vardiyayı başlat'],
    ['components/LeftRail.tsx', 'LeftRail', { session, view: 'Plant View', navigate: noop }, 'Fabrika Görünümü'],
    ['components/FactoryFloor.tsx', 'FactoryFloor', { session, selected: null, onSelect: noop }, 'HAMMADDE'],
    ['components/OrderBoard.tsx', 'OrderBoard', { session, busy: false, save: noop }, 'Müşteri taahhütleri'],
    ['views/InboxView.tsx', 'InboxView', { session, navigate: noop, replay: noop, onReadHandover: noop, handoverRead: true }, 'Ofis / Gelen Kutusu'],
    ['views/ProductionPlanView.tsx', 'ProductionPlanView', { control }, 'Üretim Planı'],
    ['views/MaintenanceView.tsx', 'MaintenanceView', { control }, 'Bakım'],
    ['views/QualityView.tsx', 'QualityView', { control }, 'Kalite'],
    ['views/InventoryView.tsx', 'InventoryView', { control }, 'Stok'],
    ['views/ReportsView.tsx', 'ReportsView', { session }, 'Raporlar'],
    ['tutorial/Coach.tsx', 'Coach', { control, step: 1, view: 'Office / Inbox', navigate: noop, skip: noop, runFirst: noop, review: noop, replay: noop }, 'Vardiya devir notunu oku'],
  ];
  for (const [path, name, props, expected] of cases) {
    const html = renderComponent(path, name, props, 'tr');
    assert.ok(html.includes(expected), `${name}: ${expected}`);
    assert.doesNotMatch(html, /\[object Object\]|\{value\d+\}/, name);
  }
  for (let step = 2; step <= 7; step++) {
    const html = renderComponent('tutorial/Coach.tsx', 'Coach', { control, step, view: 'Plant View', navigate: noop, skip: noop, runFirst: noop, review: noop, replay: noop }, 'tr');
    assert.match(html, /Rehberli vardiya/);
    assert.doesNotMatch(html, /\[object Object\]|\{value\d+\}/);
  }
  const english = renderComponent('components/LoginScreen.tsx', 'LoginScreen', { control: controlFor(null), replay: noop }, 'en');
  assert.match(english, /Start your shift/);
  assert.match(english, /value="en"[^>]*selected/);
  const turkish = renderComponent('components/LoginScreen.tsx', 'LoginScreen', { control: controlFor(null), replay: noop }, 'tr');
  assert.match(turkish, /value="tr"[^>]*selected/);
});

test('stored notices and connection failures translate when locale changes without replaying requests', async () => {
  const state = [], refs = [];
  let cursor = 0, refCursor = 0, locale = 'en', requests = 0;
  const mockReact = { ...React,
    useState(initial) { const i = cursor++; if (!(i in state)) state[i] = typeof initial === 'function' ? initial() : initial; return [state[i], value => { state[i] = value; }]; },
    useRef(value) { const i = refCursor++; return refs[i] ??= { current: value }; },
    useEffect() {}, useCallback: fn => fn, useMemo: fn => fn(),
  };
  class ConnectionError extends Error { constructor() { super('network'); this.method = 'POST'; this.path = '/sessions'; } }
  const api = { API_BASE_URL: 'http://127.0.0.1:8010', PlantOpsConnectionError: ConnectionError, PlantOpsApiError: class extends Error {}, createSession: async () => { requests++; throw new ConnectionError(); } };
  const hook = typescriptLoader({ react: mockReact, '../i18n': { useI18n: () => ({ locale }) }, '../api/plantops': api })('hooks/usePlantSession.ts').usePlantSession;
  const render = () => { cursor = 0; refCursor = 0; return hook(); };
  storage(); let control = render(); assert.equal(control.notice, 'Choose a shift to begin.');
  locale = 'tr'; control = render(); assert.equal(control.notice, 'Başlamak için bir vardiya seçin.');
  await control.newShift(-1); control = render(); assert.match(control.error, /tam sayı/);
  await control.newShift(42); control = render(); assert.match(control.error, /ulaşılamıyor/); assert.match(control.error, /POST \/sessions/);
  locale = 'en'; control = render(); assert.match(control.error, /Cannot reach PlantOps/);
  assert.equal(requests, 1);
  state[0] = fixture;
  locale = 'tr'; control = render();
  assert.equal(control.session.scenario_profile.title, 'İlk vardiya: kesim koşulu');
  locale = 'en'; control = render();
  assert.equal(control.session, fixture);
  assert.equal(requests, 1);
});

test('frontend source forbids direct localStorage access and untranslated UI text', () => {
  function files(directory) { return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? files(new URL(`${entry.name}/`, directory)) : [new URL(entry.name, directory)]); }
  for (const file of files(new URL('../src/', import.meta.url)).filter(f => /\.tsx?$/.test(f.pathname))) {
    const source = readFileSync(file, 'utf8');
    assert.doesNotMatch(source, /\blocalStorage\s*(?:\.|\[)|\[\s*["']localStorage["']\s*\]/, file.pathname);
    if (file.pathname.includes('/i18n/')) continue;
    const ast = ts.createSourceFile(file.pathname, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    function visit(node) {
      if (ts.isJsxText(node) && /[A-Za-z]/.test(node.text)) assert.ok(['PlantOps', 'Artemis Manufacturing', 'OEE', 'OTIF', 'PO'].includes(node.text.trim()), `${file.pathname}: ${node.text}`);
      if (ts.isJsxAttribute(node) && ['className', 'style', 'data-workspace', 'data-action'].includes(node.name.text)) assert.doesNotMatch(node.getText(ast), /\b(?:t|label)\(/, 'Never translate technical attributes');
      ts.forEachChild(node, visit);
    }
    visit(ast);
  }
});
