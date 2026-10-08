// A soft three-note chime made with the Web Audio API (no sound files).
// Browsers only allow audio after a user gesture, so unlockAudio() runs on the "Run agents" click.

let ctx: AudioContext | null = null;

export function unlockAudio(): void {
  ctx ??= new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
}

export function playChime(kind: "done" | "attention" = "done"): void {
  if (!ctx) return;
  const notes = kind === "done" ? [1046.5, 1318.5, 1568.0] : [880, 1174.7]; // C6 E6 G6, or A5 D6
  const start = ctx.currentTime + 0.02;
  notes.forEach((freq, i) => {
    const t = start + i * 0.16;
    const osc = ctx!.createOscillator();
    const overtone = ctx!.createOscillator();
    const gain = ctx!.createGain();
    osc.type = "sine";
    overtone.type = "sine";
    osc.frequency.value = freq;
    overtone.frequency.value = freq * 2.01; // slight detune = bell-like shimmer
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.18, t + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 1.1);
    osc.connect(gain);
    overtone.connect(gain);
    gain.connect(ctx!.destination);
    osc.start(t);
    overtone.start(t);
    osc.stop(t + 1.2);
    overtone.stop(t + 1.2);
  });
}
