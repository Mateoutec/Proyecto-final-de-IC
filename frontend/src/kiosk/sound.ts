let ctx: AudioContext | null = null;

const NOTES = {
  ok: [784, 1175],
  info: [660],
  error: [262, 196],
};

/** Tonos generados con WebAudio (sin archivos ni red). */
export function chime(kind: keyof typeof NOTES) {
  try {
    ctx = ctx ?? new AudioContext();
    void ctx.resume();
    const start = ctx.currentTime + 0.02;
    NOTES[kind].forEach((freq, i) => {
      const t = start + i * 0.14;
      const osc = ctx!.createOscillator();
      const gain = ctx!.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
      osc.connect(gain).connect(ctx!.destination);
      osc.start(t);
      osc.stop(t + 0.18);
    });
  } catch {
    /* sin audio disponible */
  }
}

export function unlockAudio() {
  try {
    ctx = ctx ?? new AudioContext();
    void ctx.resume();
  } catch {
    /* sin audio disponible */
  }
}
