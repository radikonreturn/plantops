import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { typescriptLoader } from './load-ts.mjs';

const i18n = typescriptLoader()('i18n/index.tsx');

const read = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8');
const loginSource = read('components/LoginScreen.tsx');
const barSource = read('components/ControlBar.tsx');

// Run the actual handlers and effects with hook/browser doubles; no extra test dependencies.
function harness({ name = '', saved = false, denied = false, reduced = false } = {}) {
  const values = new Map([['plantops.operatorName', name]]);
  if (saved) values.set('plantops.activeSession', 'saved');
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const listeners = new Set();
  const media = {
    matches: reduced,
    addEventListener: (_, fn) => listeners.add(fn),
    removeEventListener: (_, fn) => listeners.delete(fn),
  };
  const frames = new Map(), arcs = [];
  const ctx = { clearRect() {}, beginPath() {}, fill() {}, arc: (...args) => arcs.push(args) };
  const canvas = { getContext: () => ctx };
  const window = {
    innerWidth: 1000, innerHeight: 800, matchMedia: () => media,
    addEventListener() {}, removeEventListener() {},
    get localStorage() { if (denied) throw Error('denied'); return storage; },
    get sessionStorage() { if (denied) throw Error('denied'); return storage; },
  };
  let slots = [], cursor = 0, effects = [], pending = [], nextFrame = 0;
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
      return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
    },
    useRef: () => ({ current: canvas }),
    useEffect(fn, deps) {
      const index = cursor++;
      if (!effects[index] || deps.some((dep, i) => dep !== effects[index].deps[i])) {
        pending.push(() => {
          effects[index]?.cleanup?.();
          effects[index] = { deps, cleanup: fn() };
        });
      }
    },
  };
  const jsx = (type, props) => ({ type, props });
  function load(source, imports = {}) {
    const exports = {};
    const code = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
    }).outputText;
    runInNewContext(code, {
      exports, window, document: { addEventListener() {}, removeEventListener() {} },
      setInterval: () => 1, clearInterval() {},
      requestAnimationFrame: fn => { frames.set(++nextFrame, fn); return nextFrame; },
      cancelAnimationFrame: id => frames.delete(id),
      require: id => {
        if (id === '../i18n') return { useI18n: () => i18n.createTranslator('en'), LanguageSelector: () => null };
        if (id === 'react') return react;
        if (id === 'react/jsx-runtime') return { jsx, jsxs: jsx };
        if (id.endsWith('.css')) return {};
        if (id in imports) return imports[id];
        throw Error(`Unexpected import: ${id}`);
      },
    });
    return exports;
  }
  const policy = load(read('tutorial/state.ts'));
  const { LoginScreen } = load(loginSource, { '../tutorial/state': policy });
  const calls = [];
  const control = { busy: null, error: null, notice: null,
    newShift: async seed => calls.push(['open', seed]), restoreSession: async () => calls.push(['resume']) };
  let tree;
  const render = () => {
    cursor = 0;
    tree = LoginScreen({ control, replay: () => calls.push(['tutorial']) });
    const work = pending; pending = []; work.forEach(fn => fn());
    return tree;
  };
  function find(predicate, node = tree) {
    if (!node || typeof node !== 'object') return undefined;
    if (predicate(node)) return node;
    for (const child of [node.props?.children].flat(Infinity)) {
      const result = child == null ? undefined : find(predicate, child);
      if (result) return result;
    }
  }
  render();
  return {
    values, arcs, frames, calls, control, render, find,
    input(value) { find(n => n.type === 'input').props.onChange({ target: { value } }); render(); },
    submit: () => find(n => n.type === 'form').props.onSubmit({ preventDefault() {} }),
    mode(label) {
      find(n => n.props.className === 'login-mode-toggle').props.onClick(); render();
      find(n => n.type === 'button' && typeof n.props.children === 'string' && n.props.children.trim() === label).props.onClick(); render();
    },
    motion(value) { media.matches = value; listeners.forEach(fn => fn()); render(); },
    bar() {
      const { ControlBar } = load(barSource, {
        '../tutorial/state': policy, '../format': { clock: String, percent: String }, './Modal': { Modal() {} },
      });
      slots = []; cursor = 0;
      return ControlBar({ control });
    },
    unmount() { effects.forEach(effect => effect?.cleanup?.()); }, listeners,
  };
}

test('particle positions repeat across mounts; no random or direct storage access', () => {
  const first = harness(), second = harness();
  assert.equal(first.arcs.length, 38);
  assert.deepEqual(first.arcs, second.arcs);
  assert.doesNotMatch(loginSource, /Math\.random/);
  for (const source of [loginSource, barSource]) assert.doesNotMatch(source, /\blocalStorage\s*(?:\.|\[)/);
});

test('every entry mode rejects invalid trimmed names without storing or starting', async () => {
  for (const mode of ['Open shift', 'Guided tutorial', 'Resume saved']) {
    for (const name of ['', '   ', ' A ', 'x'.repeat(25)]) {
      const h = harness({ saved: true });
      h.mode(mode); h.input(name); await h.submit(); h.render();
      assert.deepEqual(h.calls, []);
      assert.equal(h.values.get('plantops.operatorName'), '');
      assert.equal(h.find(n => n.type === 'input').props['aria-invalid'], true);
      assert.match(h.find(n => n.props.id === 'operator-name-error').props.children, /2 and 24/);
    }
  }
});

test('boundary names are trimmed and stored for each mode; busy blocks submission', async () => {
  for (const [mode, action] of [['Open shift', 'open'], ['Guided tutorial', 'tutorial'], ['Resume saved', 'resume']]) {
    for (const name of ['Al', 'x'.repeat(24)]) {
      const h = harness({ saved: true });
      h.mode(mode); h.input(`  ${name}  `); await h.submit(); h.render();
      assert.equal(h.values.get('plantops.operatorName'), name);
      assert.equal(h.find(n => n.type === 'input').props.value, name);
      assert.equal(h.calls[0][0], action);
    }
  }
  const h = harness({ name: 'Al' });
  h.control.busy = 'Opening'; h.render(); await h.submit();
  assert.deepEqual(h.calls, []);
});

test('storage denial cannot break login, valid entry, or the control bar', async () => {
  const h = harness({ denied: true });
  h.input('  Ada  '); await h.submit();
  assert.deepEqual(h.calls, [['open', 42]]);
  assert.doesNotThrow(() => h.bar());
});

test('reduced motion stops particles and parallax on mount and live changes', () => {
  const h = harness({ reduced: true });
  const transform = () => h.find(n => n.props.className === 'login-card').props.style.transform;
  const move = () => { h.find(n => n.type === 'main').props.onMouseMove({ clientX: 900, clientY: 700 }); h.render(); };
  assert.equal(h.frames.size, 0);
  assert.equal(h.arcs.length, 0);
  move(); assert.equal(transform(), 'translate3d(0px, 0px, 0)');
  h.motion(false); assert.equal(h.frames.size, 1);
  move(); assert.notEqual(transform(), 'translate3d(0px, 0px, 0)');
  h.motion(true); assert.equal(h.frames.size, 0);
  assert.equal(transform(), 'translate3d(0px, 0px, 0)');
  h.unmount(); assert.equal(h.listeners.size, 0);
  assert.match(read('styles/login.css'), /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{\s*\.login-viewport \*,\s*\.login-viewport \*::before,\s*\.login-viewport \*::after\s*\{\s*animation:\s*none !important;\s*transition:\s*none !important;/);
});
