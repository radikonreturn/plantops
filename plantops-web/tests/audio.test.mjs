import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';
import { typescriptLoader } from './load-ts.mjs';

const load = typescriptLoader();
const { AudioEngine } = load('audio/AudioEngine.ts');
const { audioFrame, audioTransitions } = load('audio/snapshotAudio.ts');
const { bindAudioInteractions } = load('audio/usePlantAudio.ts');
const { machineNoise } = load('audio/machineProfiles.ts');
const { defaultAudioSettings, readAudioSettings, saveAudioSettings } = load('audio/audioTypes.ts');
const fixture = JSON.parse(readFileSync(new URL('./fixtures/tutorial-session.json', import.meta.url), 'utf8'));
function snapshot() {
  const s = structuredClone(fixture);
  s.paused = false;
  for (const m of Object.values(s.summary.machine_metrics)) m.state = 'RUNNING';
  return s;
}
class Param {
  value = 0;
  values = [];
  setValueAtTime(v) { this.value = v; this.values.push(v); }
  linearRampToValueAtTime(v) { this.value = v; this.values.push(v); }
  exponentialRampToValueAtTime(v) { this.value = v; this.values.push(v); }
  cancelScheduledValues() {}
  cancelAndHoldAtTime() {}
}
class Node {
  gain = new Param(); frequency = new Param(); Q = new Param();
  connections = []; disconnected = false; started = false; stopped = false;
  connect(n) { this.connections.push(n); }
  disconnect() { this.disconnected = true; this.connections = []; }
  start() { this.started = true; }
  stop() { this.stopped = true; }
}
class Context {
  state = 'suspended'; currentTime = 0; sampleRate = 8000;
  destination = new Node(); nodes = []; resumes = 0;
  node() { const n = new Node(); this.nodes.push(n); return n; }
  createGain() { return this.node(); }
  createOscillator() { return this.node(); }
  createBufferSource() { return this.node(); }
  createBiquadFilter() { return this.node(); }
  createWaveShaper() { return this.node(); }
  createBuffer(channels, length) { return { length, getChannelData() { return new Float32Array(length); } }; }
  async resume() { this.resumes++; this.state = 'running'; }
  async close() { this.state = 'closed'; }
}
async function rig(settings = defaultAudioSettings) {
  const context = new Context(); let time = 0;
  const engine = new AudioEngine(settings, () => context, () => time);
  await engine.activate();
  const cues = [];
  const actual = engine.playCue.bind(engine);
  engine.playCue = cue => { const count = context.nodes.length; actual(cue); if (context.nodes.length > count) cues.push(cue); };
  return { engine, context, cues, advance() { time += 40000; } };
}

test('missing AudioContext and rejected resume do not throw or block snapshot processing', async () => {
  globalThis.window = {};
  const engine = new AudioEngine();
  engine.process(snapshot()); assert.equal(await engine.activate(), false); engine.dispose();
  const context = new Context(); context.resume = async () => { throw Error('autoplay denied'); };
  const rejected = new AudioEngine(defaultAudioSettings, () => context);
  assert.equal(await rejected.activate(), false); assert.equal(context.state, 'closed');
  assert.doesNotThrow(() => rejected.process(snapshot())); rejected.dispose();
});
test('render/snapshots/settings create no context before interaction; first activation uses one context', async () => {
  let creations = 0; const context = new Context();
  const engine = new AudioEngine(defaultAudioSettings, () => { creations++; return context; });
  engine.process(snapshot()); engine.setSettings(defaultAudioSettings);
  assert.equal(creations, 0); assert.equal(context.nodes.length, 0);
  assert.equal(await engine.activate(), true); assert.equal(creations, 1);
  const nodes = context.nodes.length;
  await engine.activate(); engine.process(snapshot());
  assert.equal(creations, 1); assert.equal(context.nodes.length, nodes);
  engine.dispose();
});
test('trusted button click activates; typing, disabled buttons and synthetic events do not; keyboard click is not doubled', async () => {
  const listeners = new Map(); const target = { hidden: false, addEventListener: (k, f) => listeners.set(k, f), removeEventListener: k => listeners.delete(k) };
  globalThis.Element = class { constructor(kind) { this.kind = kind; this.disabled = kind === 'disabled'; } closest(selector) { if (selector === 'button') return this.kind === 'button' || this.disabled ? this : null; if (selector.includes('input')) return this.kind === 'input' ? this : null; return null; } getAttribute() { return null; } };
  let activations = 0, clicks = 0, updated = 0;
  const unbind = bindAudioInteractions({ activate: async () => { activations++; return true; }, playCue: () => clicks++, setHidden() {} }, target, () => updated++);
  const event = (kind, extra = {}) => ({ isTrusted: true, type: 'click', target: new Element(kind), ...extra });
  listeners.get('click')(event('button', { isTrusted: false }));
  listeners.get('click')(event('disabled')); listeners.get('click')(event('input'));
  listeners.get('keydown')(event('input', { type: 'keydown', key: 'a' }));
  assert.equal(activations, 0);
  listeners.get('keydown')(event('button', { type: 'keydown', key: 'Enter' }));
  listeners.get('click')(event('button')); await Promise.resolve();
  assert.equal(clicks, 1); assert.equal(updated, 2); unbind(); assert.equal(listeners.size, 0);
});
test('identical or relocalized snapshot does not repeat RUNNING → DOWN failure', async () => {
  const { engine, cues, advance } = await rig(); const s = snapshot();
  engine.process(s); s.summary.machine_metrics.laser_01.state = 'DOWN';
  engine.process(s); advance(); engine.process(structuredClone(s));
  s.scenario_profile.title = 'Türkçe'; engine.process(s);
  assert.deepEqual(cues, ['failure']); engine.dispose();
});
test('received material increases emit delivery once even with simultaneous raw stock consumption', async () => {
  const { engine, cues, advance } = await rig(); const s = snapshot(); engine.process(s);
  s.summary.supply_summary.received_units += 40; s.summary.raw_material_remaining = 0;
  engine.process(s); advance(); engine.process(s);
  assert.deepEqual(cues, ['delivery']); engine.dispose();
});
test('due threshold and lateness produce distinct events', async () => {
  const { engine, cues, advance } = await rig(); const s = snapshot();
  s.summary.order_summary.orders = [{ id: 'ORDER', due_minute: 100, release_minute: 0, remaining_quantity: 10, status: 'ACTIVE' }];
  s.summary.simulated_minutes = 60; engine.process(s);
  s.summary.simulated_minutes = 75; engine.process(s); advance();
  s.summary.simulated_minutes = 101; engine.process(s);
  assert.deepEqual(cues, ['due', 'late']); engine.dispose();
});
test('mute gates every new voice at master and suppresses one shots, including activation', async () => {
  const { engine, context, cues } = await rig({ ...defaultAudioSettings, muted: true });
  engine.process(snapshot()); engine.playCue('failure');
  assert.equal(context.nodes[0].gain.value, 0); assert.deepEqual(cues, []);
  assert.ok(context.nodes.filter(n => n.started).length > 0);
  engine.setSettings(defaultAudioSettings); engine.playCue('delivery'); assert.deepEqual(cues, ['delivery']);
  engine.setSettings({ ...defaultAudioSettings, muted: true }); assert.equal(context.nodes[0].gain.value, 0);
  engine.dispose();
});
test('safe storage persists validated preferences and tolerates denied/corrupt storage', () => {
  const data = new Map(); globalThis.window = { localStorage: { getItem: k => data.get(k), setItem: (k, v) => data.set(k, v) } };
  const settings = { master: 0.2, ambience: 0.1, alerts: 0.5, muted: true };
  saveAudioSettings(settings); assert.deepEqual(readAudioSettings(), settings);
  data.set('plantops.audio.v1', '{invalid'); assert.deepEqual(readAudioSettings(), defaultAudioSettings);
  data.set('plantops.audio.v1', '{"master":99,"alerts":"loud"}'); assert.equal(readAudioSettings().master, 1); assert.equal(readAudioSettings().alerts, 0.65);
  globalThis.window = { get localStorage() { throw Error('denied'); } };
  assert.doesNotThrow(() => saveAudioSettings(settings)); assert.deepEqual(readAudioSettings(), defaultAudioSettings);
});
test('audio translations match in English and Turkish', () => {
  const { en } = load('i18n/en.ts'); const { tr } = load('i18n/tr.ts');
  assert.deepEqual(Object.keys(en).sort(), Object.keys(tr).sort());
  for (const key of ['Sound', 'Mute', 'Unmute', 'Master volume', 'Ambience', 'Alerts', 'Sound starts after your first interaction']) { assert.ok(en[key]); assert.ok(tr[key]); }
});
test('procedural noise is independent, deterministic and has no random/network/timer calls', () => {
  assert.deepEqual(machineNoise('laser_01', 100), machineNoise('laser_01', 100));
  assert.notDeepEqual(machineNoise('laser_01', 100), machineNoise('cnc_01', 100));
  const dir = new URL('../src/audio/', import.meta.url);
  for (const name of readdirSync(dir)) assert.doesNotMatch(readFileSync(new URL(name, dir), 'utf8'), /Math\.random\s*\(|setInterval\s*\(|fetch\s*\(/, name);
});
test('audio processing never mutates a deeply frozen session or event_digest', async () => {
  function freeze(o) { if (o && typeof o === 'object') { Object.values(o).forEach(freeze); Object.freeze(o); } return o; }
  const s = freeze(snapshot()); const before = JSON.stringify(s); const { engine } = await rig();
  engine.process(s); engine.process(s); engine.setHidden(true); engine.setHidden(false);
  assert.equal(JSON.stringify(s), before); engine.dispose();
});
test('priority, cooldown and production rate limit discard crowded/rapid notifications', async () => {
  const { engine, cues, advance } = await rig(); const s = snapshot(); engine.process(s);
  s.summary.machine_metrics.laser_01.state = 'DOWN'; s.summary.supply_summary.received_units++; s.summary.good_production++;
  engine.process(s); assert.deepEqual(cues, ['failure']);
  s.summary.good_production++; engine.process(s); assert.deepEqual(cues, ['failure']);
  advance(); s.summary.good_production++; engine.process(s);
  s.summary.good_production++; engine.process(s); assert.deepEqual(cues, ['failure', 'production']); engine.dispose();
});
test('maintenance completion and shift end trigger once; new sessions reset the baseline', async () => {
  const { engine, cues, advance } = await rig(); const s = snapshot(); s.summary.order_summary.orders = []; engine.process(s);
  s.summary.machine_metrics.laser_01.state = 'PLANNED_MAINTENANCE'; engine.process(s); advance();
  s.summary.machine_metrics.laser_01.state = 'IDLE'; engine.process(s); advance();
  s.summary.simulated_minutes = s.summary.shift_minutes; engine.process(s); advance(); engine.process(s);
  assert.deepEqual(cues, ['maintenanceStart', 'maintenanceEnd', 'shiftEnd']);
  s.session_id = 'new'; s.summary.machine_metrics.laser_01.state = 'DOWN'; engine.process(s);
  assert.equal(cues.length, 3); engine.dispose();
});
test('hidden snapshots and first visible refresh consume events without replay; disposal releases all nodes', async () => {
  const { engine, context, cues } = await rig(); const s = snapshot(); engine.process(s);
  engine.setHidden(true); s.summary.machine_metrics.laser_01.state = 'DOWN'; engine.process(s);
  engine.setHidden(false); s.summary.supply_summary.received_units++; engine.process(s);
  assert.deepEqual(cues, []);
  engine.dispose(); assert.equal(context.state, 'closed');
  assert.ok(context.nodes.every(n => n.disconnected)); assert.ok(context.nodes.filter(n => n.started).every(n => n.stopped));
  assert.equal(await engine.activate(), false);
});
test('loop levels fade for machine states, speed does not affect pitch, paused and disconnected sessions stop voices', async () => {
  const { engine, context } = await rig(); const s = snapshot(); engine.process(s);
  const frequencies = context.nodes.map(n => n.frequency.value); const count = context.nodes.length;
  s.speed = 4; engine.process(s); assert.equal(context.nodes.length, count); assert.deepEqual(context.nodes.map(n => n.frequency.value), frequencies);
  s.paused = true; engine.process(s); assert.ok(context.nodes.filter(n => n.started).every(n => n.stopped));
  engine.process(null); engine.dispose();
});
test('transition detector uses detached baseline and reports reduced-flow warnings', () => {
  const s = snapshot(); const before = audioFrame(s); s.summary.machine_metrics.cnc_01.state = 'BLOCKED';
  assert.equal(before.machines.cnc_01.state, 'RUNNING'); assert.deepEqual(audioTransitions(before, audioFrame(s)), ['flowWarning']);
});
