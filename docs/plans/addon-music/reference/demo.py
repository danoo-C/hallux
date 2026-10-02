# Throwaway: the proposed additions in the design's own integer arithmetic, to a WAV.
import wave, numpy as np
SR = 44100
SIN = np.round(np.sin(np.arange(65536) * 2 * np.pi / 65536) * 32767).astype(np.int64)
NAMES = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
def key(n):
    k = NAMES[n[0]] + (1 if '#' in n else -1 if 'b' in n[1:] else 0)
    return 12 * (int(n[-1]) + 1) + k
def step(n): return round(440.0 * 2 ** ((key(n) - 69) / 12) * 2**32 / SR)
def sin(x): return SIN[x & 65535]
def noise(x):
    x = (x.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)); x ^= x >> np.uint64(29)
    x *= np.uint64(0xBF58476D1CE4E5B9); x ^= x >> np.uint64(32)
    return (x & np.uint64(65535)).astype(np.int64) - 32768
def decay(x, h): return np.round(65536 * 2.0 ** (-np.maximum(x, 0) / h)).astype(np.int64)
def saw_raw(p): return (p & 65535) - 32768
def saw(x):                                   # band-limited: polyBLEP, increment taken from x itself
    d = np.diff(x, append=2 * x[-1] - x[-2]) / 65536.0
    ph = (x & 65535) / 65536.0; y = 2 * ph - 1
    a = ph < d; u = ph[a] / d[a]; y[a] -= u + u - u * u - 1
    b = ph > 1 - d; u = (ph[b] - 1) / d[b]; y[b] -= u * u + u + u + 1
    return np.round(y * 32767).astype(np.int64)

out = []
def note(n, secs, fn, vel=200, tail=0.0, gap=0.15):
    dur = int(secs * SR); N = dur + int(tail * SR)
    t = np.arange(N, dtype=np.int64); p = t * step(n) >> 16
    y = np.clip(fn(t, p, vel, dur, key(n)), -32768, 32767)
    fi, fo = 90, 220
    y[:fi] = y[:fi] * np.arange(fi) // fi; y[-fo:] = y[-fo:] * np.arange(fo, 0, -1) // fo
    out.append(y); out.append(np.zeros(int(gap * SR), dtype=np.int64)); return y
def mixdown(parts, total):
    buf = np.zeros(int(total * SR), dtype=np.int64)
    for at, y in parts: a = int(at * SR); buf[a:a + len(y)] += y[:len(buf) - a]
    return buf
def silence(s=0.5): out.append(np.zeros(int(s * SR), dtype=np.int64))

# 1. the only envelope today (a straight line), then an exponential one
for n in ('A3', 'E4', 'A4'): note(n, 0.9, lambda t, p, vel, dur, k: sin(p) * (dur - t) // dur * vel >> 8)
silence()
for n in ('A3', 'E4', 'A4'): note(n, 0.9, lambda t, p, vel, dur, k: sin(p) * decay(t, 5000) * vel >> 24)
silence()
# 2. raw saw, then band-limited saw, going up
for f in (saw_raw, saw):
    for n in ('C4', 'C5', 'C6', 'C7', 'G7'): note(n, 0.5, lambda t, p, vel, dur, k, f=f: f(p) * vel >> 9, gap=0.05)
    silence()
# 3. phase modulation, possible today except for decay(): a bell, then an electric piano
bell = lambda t, p, vel, dur, k: sin(p + (sin(p * 7 >> 1) * decay(t, 9000) >> 16)) * decay(t, 14000) * vel >> 24
for n in ('C5', 'G5', 'E5', 'C6'): note(n, 1.2, bell, gap=0.0)
silence()
ep = lambda t, p, vel, dur, k: sin(p + (sin(p) * decay(t, 3000 + (96 - k) * 60) * vel >> 25)) * decay(t, 16000) * vel >> 24
for n, v in (('C3', 120), ('G3', 180), ('E4', 255), ('C5', 255)): note(n, 1.0, ep, vel=v, gap=0.0)
silence()
# 4. vibrato by phase, which section 7 says can't be done
note('A4', 2.0, lambda t, p, vel, dur, k: sin(p + (sin(t * 8) * np.minimum(t, 22050) // 22050 >> 2)) * vel >> 8)
silence()
# 5. drums: a kick with a pitch envelope, a snare, a hat (noise through a difference)
kick = lambda t, p, vel, dur, k: sin(p + (65536 - decay(t, 900)) * 5) * decay(t, 5000) * vel >> 24
snare = lambda t, p, vel, dur, k: (noise(t) * decay(t, 2200) + sin(p + (65536 - decay(t, 500)) * 2) * decay(t, 1500)) * vel >> 25
hat = lambda t, p, vel, dur, k: (noise(t) - noise(t - 1)) * decay(t, 600) * vel >> 25
parts = []; n0 = len(out)
for bar in range(2):
    for b in range(8):
        at = bar * 2.0 + b * 0.25
        parts.append((at, note('A1' if b % 4 == 0 else 'C6', 0.24, kick if b % 4 == 0 else hat, vel=255 if b % 4 == 0 else 90 + 60 * (b % 2))))
        if b % 4 == 2: parts.append((at, note('G3', 0.24, snare, vel=230)))
del out[n0:]; out.append(mixdown(parts, 4.2)); silence()
# 6. three detuned band-limited saws with a release tail after the note's end
def pad(t, p, vel, dur, k):
    env = np.minimum(t, 4000) * 16 * np.where(t < dur, 65536, decay(t - dur, 6000)) >> 16
    return (saw(p) + saw(p + (p >> 8)) + saw(p - (p >> 8))) * env * vel >> 26
parts = []; n0 = len(out)
for at, ch in ((0, ('C3', 'E3', 'G3')), (1.6, ('A2', 'C3', 'E3'))):
    for n in ch: parts.append((at, note(n, 1.5, pad, vel=110, tail=0.8)))
del out[n0:]; out.append(mixdown(parts, 4.2))

y = np.concatenate(out); peak = np.abs(y).max()
if peak > 32767: y = y * 32767 // peak
print("seconds %.1f  peak %d%%" % (len(y) / SR, peak * 100 // 32767))
w = wave.open(__file__.replace('demo.py', 'instruments-demo.wav'), 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
w.writeframes(y.astype('<i2').tobytes()); w.close()

# checks by calculation
t = np.arange(SR, dtype=np.int64); p = t * step('A1') >> 16
ph = (p + (65536 - decay(t, 900)) * 5) / 65536.0; f = np.diff(ph) * SR
print("kick: pitch %.0f Hz at the start, %.0f Hz after 20 ms, %.0f Hz after 100 ms" % (f[0], f[882], f[4410]))
p = t * step('A4') >> 16; ph = (p + (SIN[(t * 8) & 65535] >> 2)) / 65536.0; f = np.diff(ph) * SR
print("vibrato on A4: %.1f to %.1f Hz, %.2f times a second" % (f.min(), f.max(), SR / 8192))
print("detune p + (p >> 8): %.1f cents" % (1200 * np.log2(1 + 1 / 256)))
