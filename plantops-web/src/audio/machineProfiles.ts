import type { VoiceFactory } from "./audioTypes";

const profiles: Record<string, { frequency: number; filter: number; noise: number; level: number; pulse?: number }> = {
  laser_01: { frequency: 620, filter: 1900, noise: 0.3, level: 0.022 },
  cnc_01: { frequency: 95, filter: 360, noise: 0.12, level: 0.045 },
  wash_01: { frequency: 65, filter: 700, noise: 0.85, level: 0.045 },
  assembly_01: { frequency: 230, filter: 1400, noise: 0.35, level: 0.018, pulse: 0.7 },
  test_01: { frequency: 880, filter: 1100, noise: 0.02, level: 0.009 },
  quality_01: { frequency: 55, filter: 260, noise: 0.9, level: 0.012 },
  conveyor: { frequency: 80, filter: 380, noise: 0.6, level: 0.018 },
};
export function machineNoise(id: string, length: number): Float32Array {
  let seed = 2166136261;
  for (const char of id) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619) >>> 0;
  const data = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    data[i] = seed / 2147483648 - 1;
  }
  return data;
}
export const createMachineVoice: VoiceFactory = (context, destination, id) => {
  const profile = profiles[id] ?? profiles.quality_01;
  const nodes: AudioNode[] = [];
  const sources: AudioScheduledSourceNode[] = [];
  const dispose = () => {
    for (const source of sources) { try { source.stop(); } catch { /* Already stopped. */ } }
    for (const node of nodes) node.disconnect();
  };
  try {
    const gain = context.createGain(); nodes.push(gain); gain.gain.value = 0; gain.connect(destination);
    const volume = context.createGain(); nodes.push(volume); volume.gain.value = profile.level; volume.connect(gain);
    const oscillator = context.createOscillator(); nodes.push(oscillator); sources.push(oscillator);
    oscillator.frequency.value = profile.frequency; oscillator.type = "sine";
    const tone = context.createGain(); nodes.push(tone); tone.gain.value = 1 - profile.noise; oscillator.connect(tone); tone.connect(volume);
    const buffer = context.createBuffer(1, context.sampleRate * 2, context.sampleRate);
    buffer.getChannelData(0).set(machineNoise(id, buffer.length));
    const noise = context.createBufferSource(); nodes.push(noise); sources.push(noise); noise.buffer = buffer; noise.loop = true;
    const filter = context.createBiquadFilter(); nodes.push(filter); filter.type = "lowpass"; filter.frequency.value = profile.filter; filter.Q.value = 0.6;
    const noiseGain = context.createGain(); nodes.push(noiseGain); noiseGain.gain.value = profile.noise;
    noise.connect(filter); filter.connect(noiseGain); noiseGain.connect(volume);
    if (profile.pulse) {
      // Native modulation instead of a JS interval; squared positive envelope gives quiet gaps.
      const lfo = context.createOscillator(); nodes.push(lfo); sources.push(lfo); lfo.frequency.value = profile.pulse;
      const shape = context.createWaveShaper(); nodes.push(shape);
      shape.curve = Float32Array.from({ length: 128 }, (_, i) => Math.pow(Math.max(0, i / 127 * 2 - 1), 8));
      const depth = context.createGain(); nodes.push(depth); depth.gain.value = profile.level;
      volume.gain.value = 0; lfo.connect(shape); shape.connect(depth); depth.connect(volume.gain);
    }
    for (const source of sources) source.start();
    return { gain, dispose };
  } catch (error) { dispose(); throw error; }
};
