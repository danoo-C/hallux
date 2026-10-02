# Throwaway: the three scores of section 5 in the design's integer arithmetic. Peaks and a WAV.
import wave, numpy as np
SR = 44100
SIN = np.round(np.sin(np.arange(65536) * 2 * np.pi / 65536) * 32767).astype(np.int64)
NAMES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
def key(n): return 12 * (int(n[-1]) + 1) + NAMES[n[0]] + (1 if '#' in n else -1 if 'b' in n[1:] else 0)
def sin(x): return SIN[x & 65535]
def noise(x):
    x = (x.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)); x ^= x >> np.uint64(29)
    x *= np.uint64(0xBF58476D1CE4E5B9); x ^= x >> np.uint64(32)
    return (x & np.uint64(65535)).astype(np.int64) - 32768
def decay(x, h): return np.round(65536 * 2.0 ** (-np.maximum(x, 0) / h)).astype(np.int64)
def raw(p): return (p & 65535) - 32768
def saw(x):
    d = np.diff(x, append=2 * x[-1] - x[-2]) / 65536.0
    ph = (x & 65535) / 65536.0; y = 2 * ph - 1
    a = ph < d; u = ph[a] / d[a]; y[a] -= u + u - u * u - 1
    b = ph > 1 - d; u = (ph[b] - 1) / d[b]; y[b] -= u * u + u + u + 1
    return np.round(y * 32767).astype(np.int64)

def render(bpm, notes, steps_total, var_events=(), var_init=None, tail=None):
    sps = SR * 60 / bpm / 8
    at = lambda s: int(round(s * sps))
    tails = tail or {}
    N = at(steps_total) + max(tails.values(), default=0)
    V = {}
    for name, v0 in (var_init or {}).items():
        arr = np.full(N, v0, dtype=np.int64); cur = v0
        for s, d, v in sorted(e[:3] for e in var_events if e[3] == name):
            a, b = at(s), at(s + d)
            if b > a: arr[a:b] = cur + (v - cur) * np.arange(b - a) // (b - a)
            arr[b:] = v; cur = v
        V[name] = arr
    buf = np.zeros(N, dtype=np.int64)
    for s, d, n, inst, vel in notes:
        a = at(s); dur = at(s + d) - a; L = dur + tails.get(inst.__name__, 0)
        k = key(n) if isinstance(n, str) else n
        st = round(440.0 * 2 ** ((k - 69) / 12) * 2**32 / SR)
        t = np.arange(L, dtype=np.int64); p = t * st >> 16
        y = np.clip(inst(t, p, vel, dur, k, {m: arr[a:a + L] for m, arr in V.items()}), -32768, 32767)
        fi, fo = 90, 220
        y[:fi] = y[:fi] * np.arange(fi) // fi; y[-fo:] = y[-fo:] * np.arange(fo, 0, -1) // fo
        buf[a:a + L] += y
    return buf
def place(pattern, start, tr=0, times=1, length=32):
    return [(start + i * length + s, d, key(n) + tr, inst, v) for i in range(times) for s, d, n, inst, v in pattern]
def chord(s, d, names, inst, v): return [(s, d, n, inst, v) for n in names.split()]
def report(name, y):
    pk = int(np.abs(y).max()); print("%-28s %.1f s  peak %.1f%%" % (name, len(y) / SR, pk * 100 / 32767)); return y

# --- score 1, as it is in the doc now (raw saw), and with saw(p)
def pad(t, p, vel, dur, k, V): return sin(p) * vel >> 8
def lead_raw(t, p, vel, dur, k, V): return (raw(p) + sin(p)) * vel >> 9
def lead(t, p, vel, dur, k, V): return (saw(p) + sin(p)) * vel >> 9
def song1(ld, pv, lv):
    major = chord(0, 32, 'C3 E3 G3', pad, pv); minor = chord(0, 32, 'A2 C3 E3', pad, pv)
    riff = [(0, 8, 'C4', ld, lv), (8, 8, 'G4', ld, lv), (16, 16, 'C5', ld, lv)]
    return (place(major, 0) + place(riff, 0) + place(major, 32, -5) + place(riff, 32, -5)
            + place(minor, 64) + place(riff, 64, -3) + place(major, 96, -7) + place(riff, 96, -7))
report("score 1, raw saw", render(100, song1(lead_raw, 60, 140), 128))
s1 = report("score 1, saw(p)", render(100, song1(lead, 60, 140), 128))

# --- score 2
def pad2(t, p, vel, dur, k, V): return sin(p) * vel * V['VOL'] >> 16
def lead2_raw(t, p, vel, dur, k, V): return (raw(p) * V['BRIGHT'] + sin(p) * (255 - V['BRIGHT'])) * vel * V['VOL'] >> 24
def lead2(t, p, vel, dur, k, V): return (saw(p) * V['BRIGHT'] + sin(p) * (255 - V['BRIGHT'])) * vel * V['VOL'] >> 24
ve = [(0, 8, 255, 'VOL'), (112, 16, 0, 'VOL')]
for bar in range(4): ve += [(bar * 32, 24, 255, 'BRIGHT'), (bar * 32 + 24, 8, 0, 'BRIGHT')]
for nm, ld in (("score 2, raw saw", lead2_raw), ("score 2, saw(p)", lead2)):
    s2 = report(nm, render(100, song1(ld, 40, 130), 128, ve, {'VOL': 0, 'BRIGHT': 0}))

# --- score 3, the drum beat of the demo
def kick(t, p, vel, dur, k, V): return sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24
def snare(t, p, vel, dur, k, V):
    body = sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)
    return (noise(t) * decay(t, 2200) + body) * vel >> 25
def hat(t, p, vel, dur, k, V): return (noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25
beat = [(0, 4, 'A1', kick, 255), (4, 4, 'C6', hat, 150), (8, 4, 'G3', snare, 230), (8, 4, 'C6', hat, 90),
        (12, 4, 'C6', hat, 150), (16, 4, 'A1', kick, 255), (20, 4, 'C6', hat, 150), (24, 4, 'G3', snare, 230),
        (24, 4, 'C6', hat, 90), (28, 4, 'C6', hat, 150)]
s3 = report("score 3, drums, 4 bars", render(120, place(beat, 0, 0, 4), 128))
for nm, f, v in (("kick alone", kick, 255), ("snare alone", snare, 230), ("hat alone, 150", hat, 150)):
    report("  " + nm, render(120, [(0, 4, 'A1' if f is kick else 'G3', f, v)], 4))

# --- the pad with a tail
def pad_tail(t, p, vel, dur, k, V):
    env = np.minimum(t, 4000) * decay(t - dur, 6000) >> 12
    return (saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26
s4 = report("pad with a tail, 2 chords", render(100, chord(0, 20, 'C3 E3 G3', pad_tail, 110) + chord(22, 20, 'A2 C3 E3', pad_tail, 110), 42, tail={'pad_tail': 35280}))
print("  tail level at its end: %.1f%% of full" % (decay(np.array([35280]), 6000)[0] * 100 / 65536))

gap = np.zeros(SR // 2, dtype=np.int64)
y = np.concatenate([s1, gap, s2, gap, s3, gap, s4]); pk = np.abs(y).max()
if pk > 32767: y = y * 32767 // pk
if __name__ == "__main__":                   # a test that loads this file gets the arrays only
    w = wave.open(__file__.replace('scores.py', 'section5-scores.wav'), 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(y.astype('<i2').tobytes()); w.close(); print("wav %.1f s" % (len(y) / SR))
